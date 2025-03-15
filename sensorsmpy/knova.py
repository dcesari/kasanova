#!/usr/bin/micropython

import math
import micropython
#import sched as micropython
import machine
import time
import ujson
import network
import ntptime
import socket
import select


# tentative main loop, cb must return after a reasonable time
def KnovaMain(jsonconf, cb):
    confs = ujson.loads(jsonconf)
    # json configuration should be an iterable of single-tool configurations
    while(True):
        for conf in confs:
            KnovaDispatcher(conf)
        KnovaTool.connectall()
        actres = 0
        while (type(actres) is int):
            if actres != 0: time.sleep(10) # wait and repeat download
            actres = KnovaTool.activateall()
        if type(actres) is str: # new conf obtained, download it
            confs = ujson.loads(actres)
        else:
            break
    while(True):
        cb()
        KnovaTool.lptimer.checktimer()


def KnovaDispatcher(conf):
    typ = conf.get("type", "")
    if conf["type"] == "wifinetwork":
        return KnovaWiFiNetwork(conf)
    if conf["type"] == "webserver":
        return KnovaWebServer(conf)
    if conf["type"] == "pushbutton":
        return KnovaPushButton(conf)
    if conf["type"] == "onoffbutton":
        return KnovaOnOffButton(conf)
    if conf["type"] == "toggleswitch":
        return KnovaToggleSwitch(conf)
    if conf["type"] == "timedswitch":
        return KnovaTimedSwitch(conf)
    if conf["type"] == "onoffswitch":
        return KnovaOnOffSwitch(conf)
    if conf["type"] == "digitalout":
        return KnovaDigitalOut(conf)
    print("unknown tool type: "+conf["type"])
    return None


class KnovaLPTimer:
    rtlist = []
    ptlist = []
    prec = 1
    timerid: int = 0
    nonetimer: int = -1

    def __init__(self):
        self.rtlist = []
        self.ptlist = []
        self.prec = 1
        self.timerid: int = 0
    
    def addtimer(self, delta, cb=None, period=0):
        if cb is None: return self.nonetimer
        abstime = time.time() + delta # or we receive abs time?
        n = 0
        for n in range(len(self.rtlist)):
            if abstime < self.rtlist[n][0]: break
        # should we conserve timerid for periodic timers?
        self.rtlist.insert(n, (abstime, cb, period, self.timerid))
        ret = self.timerid
        self.timerid += 1
        if self.timerid == self.nonetimer: self.timerid += 1
        return ret

    def addperiodictimer(self, period, cb):
        self.ptlist.append((0, cb, period)) # useful?
        self.addtimer(period, cb, period)

    def checktimer(self):
        now = time.time()
        while(True):
            if len(self.rtlist) <= 0: return
            if self.rtlist[0][0] - now < self.prec:
                self.consumetimer()
                now = time.time() # time may have passed in callback
            else:
                return

    def consumetimer(self):
        rt = self.rtlist[0]
        del self.rtlist[0] # rt is not deleted here (empirically)
        # if periodic, schedule next event
        if rt[2] > 0: self.addtimer(rt[0], rt[1], rt[2])
        rt[1]() # call after-timer callback

    def canceltimer(self, timerid):
        if timerid == self.nonetimer: return
        for n in range(len(self.rtlist)):
            if self.rtlist[n][3] == timerid:
                del self.rtlist[n]
                return

class KnovaTimerInstance:
    def __init__(self, engine, delta, cb=None, period=0):
        self.engine = engine
        self.id = engine.addtimer(delta, cb, period)

    def cancel(self):
        self.engine.canceltimer(self.id)

# generic tool
class KnovaTool:
    unitlist = {}
    timercount = 1 # reserve timer n.0 for main loop
    lptimer = KnovaLPTimer()

    def __init__(self, conf):
        self.name = conf["name"]
        self.typ = conf["type"]
        if self.name in KnovaTool.unitlist:
            raise # duplicated tool
        self.id = len(KnovaTool.unitlist) # unique progressive id
        KnovaTool.unitlist[self.name] = self
        # improve management of default values in inheritance
        self.web = conf.get("web", False)
        self.timer = KnovaTimerInstance(KnovaTool.lptimer, 0)
        self.updateperiod = conf.get("updateperiod", 0)


    def connect(self):
        # do nothing if not overridden
        return


    def connectall():
        # class method for connecting all configured instances
        for u in KnovaTool.unitlist:
            KnovaTool.unitlist[u].connect()


    def activate(self):
        # init timers, must be done if overridden
        if self.updateperiod > 0: # is it acceptable to start timers here?
            self.timer = KnovaTimerInstance(KnovaTool.lptimer,
                                            self.updateperiod,
                                            self.periodicupdate,
                                            self.updateperiod)

    def activateall():
        # class method for activating all configured instances
        newconf = None
        for u in KnovaTool.unitlist:
            res = KnovaTool.unitlist[u].activate()
            if res is not None: newconf = res
        return newconf


    def propagate(self, origin):
        for out in self.outs:
            out.propagate(self)

    def periodicupdate(self):
        # do nothing if not overridden
        return


    def getstate(self, req):
        state = {}
        i = 0
        for n in self.state:
            state[i] = n
            i = i + 1
        req.sendresponse("application/json", ujson.dumps(state))


    def gettimer():
        # class method for getting an available global timer
        if KnovaTool.timercount > 3:
            raise
        t = machine.Timer(KnovaTool.timercount)
        KnovaTool.timercount += 1 # check not to exceed (max 3)
        return t


# network tools
class KnovaWiFiNetwork(KnovaTool):
    def __init__(self, conf):
        import network
        import ntptime
        conf["name"] = "wifinetwork"
        super().__init__(conf)
        self.ssid = conf["ssid"]
        self.password = conf["password"]
        self.updateperiod = conf.get("updateperiod", 0)
        self.blocking = conf.get("blocking", False)
        self.ntp = conf.get("ntp", False)
        self.ntphost = conf.get("ntphost", None)
        self.ntpready = False
        self.getconf = conf.get("getconf", None)
        KnovaTool.unitlist[self.name] = self
        self.nic = network.WLAN(network.STA_IF)
        self.nic.active(True)
        if self.ntp:
            if self.ntphost is not None:
                ntptime.host = self.ntphost


    def connect(self):
        if not self.nic.isconnected():
            self.nic.connect(self.ssid, self.password)


    def activate(self):
        super().activate()
        if self.blocking or self.getconf is not None or self.ntp:
            while not self.nic.isconnected():
                time.sleep(1)
            if self.ntp and not self.ntpready:
                try:
                    ntptime.settime()
                    self.ntpready = True
                except:
                    pass
            if self.getconf is not None:
                import binascii
                self.getconf.replace("%M", binascii.hexlify(sta_if.config('mac', ':')))
                self.getconf.replace("%I", sta_if.ifconfig()[0])
                # sta_if.config('mac') => b'$\n\xc4\x00\x01\x10' array len=6
                # sta_if.ifconfig()[0] => '0.0.0.0'
                try:
                    r = request("GET", self.getconf, timeout=10000)
                    newconf = r.text
                    r.close()
                    # download conf by http and return it
                    self.getconf = None
                except:
                    newconf = None
                return newconf


    def periodicupdate(self): # can i do something to stimulate connection?
        if self.nic.isconnected() and self.ntp:
            ntptime.settime()


class KnovaWebRequest:
    def __init__(self, method, resource, querydict, fp):
        self.method = method
        self.resource = resource
        self.querydict = querydict
        self.fp = fp


    def senderror(self, code):
        htcode = str(code)
        try:
            self.fp.send(b'HTTP/1.0 '+htcode+' OK\r\nContent-type: text/html\r\nConnection: close\r\n\r\n')
            r = bytes(htmle % (htcode,),"ascii")
            self.fp.send(r)
            self.fp.close()
        except:
            pass


    def sendresponse(self, ctype, cbody):
        try:
            self.fp.send(b'HTTP/1.0 200 OK\r\nContent-type: '+ctype+'\r\nConnection: close\r\n\r\n')
            self.fp.send(bytes(cbody, "ascii"))
            self.fp.close()
        except:
            pass


    def sendemptyresponse(self): # correct?
        try:
            self.fp.send(b'HTTP/1.0 200 OK\r\nConnection: close\r\n\r\n')
            self.fp.close()
        except:
            pass


class KNovaWebServer(KnovaTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.webhooks = []
        self.allowip = conf.get("allowip", None)
        if type(self.allowip) == str:
            self.allowip = [conf["allowip"]]
        self.listenaddr = conf.get("listenaddr", "0.0.0.0")
        self.port = conf.get("port", 8081)

    def connect(self):
        addr = socket.getaddrinfo(self.listenaddr, self.port)[0][-1]
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(addr)
        self.sock.listen(5)
#        print('listening on', addr)
        self.httpoll = select.poll()
        self.httpoll.register(self.sock, select.POLLIN)

    def register(self, req, callback):
        self.webhooks.append((req, callback))

    def qs_to_dict(self, qs):
        querydict = {}
        try:
            for el in qs.split("&"):
                try:
                    k, v = el.split("=", 1)
                    querydict[k] = v
                except:
                    querydict[el] = None
        except:
            pass
        return querydict


    def req_decode(self, reqfull):
        meth = None
        resource = []
        querystring = None
        querydict = {}
        rq = None
        try:
            meth, req, proto = reqfull.decode().split(" ")
            rq = req.split("?")
            resource = rq[0].lstrip("/").rstrip("/").split("/")
            if len(rq) > 1:
                querystring = rq[1].split("&")
        except:
            pass
        if rq is not None:
            if len(rq) > 1:
                querydict = self.qs_to_dict(rq[1])

        return meth, resource, querydict

    def http_ready(self):
        cl, addr = self.sock.accept()
        ip = socket.inet_ntop(socket.AF_INET,addr[4:8]) # indovinato
#        print("request from "+ip)
        cl_file = cl.makefile('rwb', 0)
        req = cl_file.readline(1024)
        meth, res, qs = self.req_decode(req)
        auth = False
        length = None
        # authorisation
        if self.allowip is not None:
            for i in self.allowip:
                if ip == i:
                    auth = True
        else:
            auth = True
        # read headers
        while True:
            line = cl_file.readline(1024)
            if not line or line == b"\r\n":
                break
            try:
                k, v = line.rstrip(b"\r\n").split(b" ")
                if k == b"Content-Length:":
                    length = int(v)
            except:
                pass
        # read post data
        if meth == "POST":
            if length is not None:
                postdata = cl_file.read(min(length,2048))
                qs.update(self.qs_to_dict(postdata))

        request = KnovaWebRequest(meth, res, qs, cl)
        # unauthorised
        if not auth:
            request.senderror(400)
            return
        for h in self.webhooks:
            if res == h[0]:
                # here OK, call callback
                h[1](request)
                return
        # not found
        request.senderror(404)


    def periodicupdate(self): # improve
        ready = self.httpoll.poll(1000)
        # handle errors in select here
        if len(ready) > 0:
            self.http_ready()
            return 1
        return 0


# sensor/buttons tools
class KnovaMultiTool(KnovaTool):
    unitlist = {}
    timercount = 1 # reserve timer n.0 for main loop
    lptimer = KnovaLPTimer()

    def __init__(self, conf):
        super().__init__(conf)
        self.upstreamconn = conf.get("upstreamconn",[])
        self.ins = []
        self.outs = []
        # improve management of default values in inheritance
        self.filterms = conf.get("filterms", 400) # >0 to enable debounce filter
        if self.filterms > 0:
            self.filters = math.ceil(self.filterms/1000) # for wrap check
            self.lastevent = time.ticks_ms()
            self.lasteventnw = time.time()
        self.filterreps = conf.get("filterreps", 300) # >0 to enable anti-repetiotion filter
        if self.filterreps > 0:
            self.lastevent = time.time()


    def connect(self):
        # store upstream unit instances and notify them of the connection
        for u in self.upstreamconn:
            self.ins.append(KnovaTool.unitlist[u])
            KnovaTool.unitlist[u].notifyconnect(self)

    def notifyconnect(self, downstream):
        # store downstream unit instances
        self.outs.append(downstream)


    def propagate(self, origin):
        for out in self.outs:
            out.propagate(self)

    def periodicupdate(self):
        # do nothing if not overridden
        return


    def noisefilter(self):
        if self.filterms > 0:
            now = time.ticks_ms()
            nownw = time.time() # wrap check
            if time.ticks_diff(now, self.lastevent) < self.filterms and \
               nownw - self.lasteventnw < self.filters: return True # too early, do nothing
            self.lastevent = now
            self.lasteventnw = nownw
        return False

    def repetitionfilter(self):
        if self.filtersrep > 0:
            now = time.time()
            if now - self.lastevent < self.filtersrep: return True # too early, do nothing
            self.lastevent = now
        return False


class KnovaPushButton(KnovaMultiTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.pushtype = conf.get("pushtype", "push") # push or release
        self.invert = conf.get("invert", False)
        self.pin = machine.Pin(conf["pin"], mode=machine.Pin.IN, pull=machine.Pin.PULL_UP) #...
        self.initdelay = conf.get("initdelay", 0)

        self.state = bytearray(2)
        self.state[0] = 0
        self.state[1] = 1 # start enabled


    def connect(self):
        super().connect() # call base connect method
        if self.web: # connect to web server
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)
            KnovaTool.unitlist["web"].register((self.name,"set","pushrelease"), self.pushweb)
            KnovaTool.unitlist["web"].register((self.name,"set","enable"), self.enable)
            KnovaTool.unitlist["web"].register((self.name,"set","disable"), self.disable)


    def activate(self):
        super().activate()
        cond = (self.pushtype == "push") != self.invert
        if cond:
            self.pin.irq(handler=self.push, trigger=machine.Pin.IRQ_RISING)
        else:
            self.pin.irq(handler=self.push, trigger=machine.Pin.IRQ_FALLING)


    def startpropagate(self, state):
        super().propagate(None)

    def push(self, pin):
        if self.state[1] == 1:
            self.state[0] = 1 # will never change after first pushrelease?!
            if self.noisefilter(): return
            micropython.schedule(self.startpropagate, 1)


    def pushweb(self):
        if self.state[1] == 1:
            super().propagate(None)
        return 0

    def enable(self):
        self.state[1] = 1
        return 0

    def disable(self):
        self.state[1] = 0
        return 0


class KnovaOnOffButton(KnovaMultiTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.invert = conf.get("invert", False)
        self.pin = machine.Pin(conf["pin"], mode=machine.Pin.IN, pull=machine.Pin.PULL_UP) #...
        self.defaultstate = conf.get("defaultstate", 0)
        self.initdelay = conf.get("initdelay", 0)
        self.updateperiod = conf.get("updateperiod", 5)

        self.state = bytearray(1)
        self.state[0] = self.defaultstate


    def connect(self):
        super().connect() # call base connect method
        if self.web: # connect to web server
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)


    def activate(self):
        super().activate()
        self.pin.irq(handler=self.onoff,
                     trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING)


    def startpropagate(self, state):
        # here it may be too early to trust pin value
        # schedule a state refresh after self.filterms???
        self.state[0] = self.pin.value() != self.invert
        super().propagate(None)


    def periodicupdate(self):
        self.startpropagate(1)


    def onoff(self, pin):
        if self.noisefilter(): return
        micropython.schedule(self.startpropagate, 1)


class KnovaOwBus(KnovaMultiTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.pin = machine.Pin(conf["pin"], mode=machine.Pin.IN, pull=machine.Pin.PULL_UP) #...
        self.initdelay = conf.get("initdelay", 0)
        self.updateperiod = conf.get("updateperiod", 600)

        self.ow = onewire.OneWire(self.pin) # create a OneWire bus
        # ow.scan() # return a list of devices on the bus
        self.ow.reset() # reset the bus


    def activate(self):
        self.thermo = None
        for out in self.outs:
            if isinstance(out, KnovaOwThermometer):
                self.thermo = ds18x20.DS18X20(self.ow)
                break
        if self.thermo is not None:
            self.roms = ds.scan()
            super().activate() # schedule timer

    def periodicupdate(self):
        if self.thermo is not None:
            self.thermo.convert_temp()
            time.sleep_ms(750)
            super().propagate(None)


class KnovaOwThermometer(KnovaMultiTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.romid = conf["romid"]
        self.state = array.array("f",(-10000.,))
        # self.state[0] = 0
        # self.state[1] = 1 # start enabled

    def connect(self):
        super().connect() # call base connect method


    def propagate(self, origin):
        self.state[0] = origin.thermo.read_temp(self.romid)
        self.lastevent = time.time()
        super().propagate(origin)


class KnovaToggleSwitch(KnovaMultiTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.timerduration = conf.get("timerduration", 60)
        self.defaultstate = conf.get("defaultstate", 0)
        self.state = bytearray(4) # out, man, out timer, auto out
        self.state[2] = 0 # output by timer off
        self.state[0] = self.defaultstate
        self.state[3] = self.defaultstate


    def connect(self):
        super().connect() # call base connect method
        if self.web: # connect to web server
            KnovaTool.unitlist["web"].register((self.name,"set","on"), self.onman)
#            KnovaTool.unitlist["web"].register((self.name,"set","ontimer"), self.ontimer)
            KnovaTool.unitlist["web"].register((self.name,"set","off"), self.offman)
#            KnovaTool.unitlist["web"].register((self.name,"set","offtimer"), self.offtimer)
            KnovaTool.unitlist["web"].register((self.name,"set","toggle"), self.toggleman)
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)
        if len(self.ins) > 0:
            self.state[1] = 0 # automatic
            if self.web:
                KnovaTool.unitlist["web"].register((self.name,"set","auto"), self.setauto)
                KnovaTool.unitlist["web"].register((self.name,"set","man"), self.setman)

        else:
            self.state[1] = 1 # manual


    def setman(self, req):
        self.state[1] = 1
        req.sendemptyresponse()

    def setauto(self, req):
        self.state[1] = 0
        # self.state[0] = self.state[3] # better keep last manual state
        self.state[3] = self.state[0]
        # super().propagate(self) # do not propagate if no change occurs
        req.sendemptyresponse()

    def onman(self, req):
        self.state[0] = 1
        super().propagate(None)
        req.sendemptyresponse()

    def offman(self, req):
        self.state[0] = 0
        super().propagate(None)
        req.sendemptyresponse()

    def toggleman(self, req):
        self.state[0] = 1 - self.state[0]
        super().propagate(None)
        req.sendemptyresponse()


    def propagate(self, origin):
        if self.state[1] == 1: return # do not update neither propagate in manual state
        # if inp.state[0] == 1:
        self.state[3] = 1 - self.state[3]
        self.state[0] = self.state[3]
        super().propagate(origin) # should it be None or origin?


class KnovaTimedSwitch(KnovaMultiTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.timerduration = conf.get("timerduration", 60)
        self.timermode = "restart"
        self.defaultstate = 0 # conf.get("defaultstate", 0)
        self.state = bytearray(4) # out, man, out timer, auto out
        self.state[2] = 0 # output by timer off
        self.state[0] = self.defaultstate
        self.state[3] = self.defaultstate
        self.timerincr = 0


    def connect(self):
        super().connect() # call base connect method
        if self.web: # connect to web server
            KnovaTool.unitlist["web"].register((self.name,"set","on"), self.onman)
#            KnovaTool.unitlist["web"].register((self.name,"set","ontimer"), self.ontimer)
            KnovaTool.unitlist["web"].register((self.name,"set","off"), self.offman)
#            KnovaTool.unitlist["web"].register((self.name,"set","offtimer"), self.offtimer)
            KnovaTool.unitlist["web"].register((self.name,"set","toggle"), self.toggleman)
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)
        if len(self.ins) > 0:
            self.state[1] = 0 # automatic
            if self.web:
                KnovaTool.unitlist["web"].register((self.name,"set","auto"), self.setauto)
                KnovaTool.unitlist["web"].register((self.name,"set","man"), self.setman)
        else:
            self.state[1] = 1 # manual
            

    def setman(self, req):
        self.timeroff()
        self.state[1] = 1
        req.sendemptyresponse()

    def setauto(self, req):
        self.timeroff()
        self.state[1] = 0
        self.state[3] = self.defaultstate
        self.state[0] = self.defaultstate
        super().propagate(None)
        req.sendemptyresponse()

    def onman(self, req):
        self.timeroff()
        self.state[0] = 1
        super().propagate(None)
        req.sendemptyresponse()

    def offman(self, req):
        self.timeroff()
        self.state[0] = 0
        super().propagate(None)
        req.sendemptyresponse()

    def toggleman(self, req):
        self.timeroff()
        self.state[0] = 1 - self.state[0]
        super().propagate(None)
        req.sendemptyresponse()


    def propagate(self, origin):
        if self.state[1] == 1: return # do not update neither propagate in manual state
        self.state[3] = 1
        self.state[0] = 1
        super().propagate(origin)
        # schedule timer after setting the state, to avoid
        # self.timerend being called before end of propagate
        if self.timermode == "restart":
#            if self.timer is not None: self.timer.cancel()
            self.timer.cancel()
            self.state[2] = 1
#            self.timer.init(mode=machine.Timer.ONE_SHOT,
#                            period=self.timerduration*1000,
#                            callback=self.timerend)
            self.timer = KnovaTimerInstance(KnovaTool.lptimer,
                                            self.timerduration,
                                            self.timerend)
        elif self.timermode == "ignore":
            if self.state[2] == 1:
                return
            self.state[2] = 1
#            self.timer.init(mode=machine.Timer.ONE_SHOT,
#                            period=self.timerduration*1000,
#                            callback=self.timerend)
            self.timer = KnovaTimerInstance(KnovaTool.lptimer,
                                            self.timerduration,
                                            self.timerend)
        elif self.timermode == "increment":
            self.timer.cancel()
            self.timerincr +=1
            self.state[2] = 1
#            self.timer.init(mode=machine.Timer.ONE_SHOT,
#                            period=self.timerduration*1000*self.timerincr,
#                            callback=self.timerend)
            self.timer = KnovaTimerInstance(KnovaTool.lptimer,
                                            self.timerduration*self.timerincr,
                                            self.timerend)

    def timerend(self):
        self.timer.cancel()
        self.timerincr = 0
        self.state[0] = 0
        self.state[2] = 0
        self.state[3] = 0
        super().propagate(None)

#    def timerend(self, timer):
#        self.timerincr = 0
#        self.state[0] = 0
#        self.state[2] = 0
#        self.state[3] = 0
#        micropython.schedule(self.mptimerend, 0)

#    def mptimerend(self, state):
#        super().propagate(None)

    def timeroff(self):
        self.timer.cancel()
        self.timerincr = 0
        self.state[2] = 0


class KnovaOnOffSwitch(KnovaMultiTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.inputop = conf.get("inputop", "or")
        self.timerduration = conf.get("timerduration", 60)
        self.defaultstate = conf.get("defaultstate", 0)
        self.state = bytearray(4) # out, man, out timer, auto out
        self.state[2] = 0 # output by timer off
        self.state[0] = self.defaultstate
        self.state[3] = self.defaultstate
#        self.timer = KnovaTool.gettimer()


    def connect(self):
        super().connect() # call base connect method
        if self.web: # connect to web server
            KnovaTool.unitlist["web"].register((self.name,"set","on"), self.onman)
            KnovaTool.unitlist["web"].register((self.name,"set","ontimer"), self.ontimer)
            KnovaTool.unitlist["web"].register((self.name,"set","off"), self.offman)
            KnovaTool.unitlist["web"].register((self.name,"set","offtimer"), self.offtimer)
            KnovaTool.unitlist["web"].register((self.name,"set","toggle"), self.toggleman)
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)
        if len(self.ins) > 0:
            self.state[1] = 0 # automatic
            if self.web:
                KnovaTool.unitlist["web"].register((self.name,"set","auto"), self.setauto)
                KnovaTool.unitlist["web"].register((self.name,"set","man"), self.setman)
        else:
            self.state[1] = 1 # manual
            

    def setman(self, req):
        self.timeroff()
        self.state[1] = 1
        req.sendemptyresponse()

    def setauto(self, req):
        self.timeroff()
        self.state[1] = 0
        self.state[0] = self.state[3] # set state to automatic state which was updated in background
        super().propagate(None)
        req.sendemptyresponse()

    def onman(self, req): # does this make sense without setting state[1] == 1?
        self.timeroff()
        self.state[0] = 1
        super().propagate(None)
        req.sendemptyresponse()

    def offman(self, req):
        self.timeroff()
        self.state[0] = 0
        super().propagate(None)
        req.sendemptyresponse()

    def toggleman(self, req):
        self.timeroff()
        self.state[0] = 1 - self.state[0]
        super().propagate(None)
        req.sendemptyresponse()


    def propagate(self, origin):
        if self.inputop == "and":
            self.state[3] = 1
            for inp in self.ins:
                self.state[3] = self.state[3] and inp.state[0]
        elif self.inputop == "or":
            self.state[3] = 0
            for inp in self.ins:
                self.state[3] = self.state[3] or inp.state[0]
        else: # xor
            self.state[3] = 0
            for inp in self.ins:
                self.state[3] = self.state[3] != inp.state[0]
        if self.state[1] == 0:
            self.state[0] = self.state[3]
        super().propagate(origin)


    def ontimer(self, req):
        self.timeroff()
        self.state[0] = 1
        super().propagate(None)
        self.state[2] = 1
        # get period from qs
#        self.timer.init(mode=machine.Timer.ONE_SHOT,
#                        period=self.timerduration*1000,
#                        callback=self.ontimerend)
        self.timer = KnovaTimerInstance(KnovaTool.lptimer,
                                        self.timerduration,
                                        self.ontimerend)
        req.sendemptyresponse()

    def ontimerend(self): #, timer):
        self.state[2] = 0
        if self.state[1] == 0: # auto
            self.state[0] = self.state[3]
        else: # man
            self.state[0] = 0
        super().propagate(None) # micropython.schedule(self.mptimerend, 0)

    def offtimer(self, req):
        self.timeroff()
        self.state[0] = 0
        super().propagate(None)
        self.state[2] = 1
        # get period from qs
#        self.timer.init(mode=machine.Timer.ONE_SHOT,
#                        period=self.timerduration*1000,
#                        callback=self.offtimerend)
        self.timer = KnovaTimerInstance(KnovaTool.lptimer,
                                        self.timerduration,
                                        self.offtimerend)
        req.sendemptyresponse()

    def offtimerend(self):
        self.state[2] = 0
        if self.state[1] == 0: # auto
            self.state[0] = self.state[3]
        else:# man
            self.state[0] = 1
        super().propagate(None) # micropython.schedule(self.mptimerend, 1)

#    def mptimerend(self, state):
#        super().propagate(None)


    def timeroff(self):
        self.timer.deinit()
        self.state[2] = 0


class KnovaRegulator(KnovaMultiTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.invert = conf.get("invert", False)
        self.ttype = conf.get("ttype", "float")
        if self.ttype == "int":
            self.thresh = int(conf["thresh"])
        else:
            self.thresh = float(conf["thresh"])
        self.deltaplus = conf.get("deltaplus", 0)
        self.deltaminus = conf.get("deltaminus", 0)
        self.initdelay = conf.get("initdelay", 0)
        self.inputop = conf.get("inputop", "first")
        self.val = None
        self.state = bytearray(1)
        self.state[0] = 2
        if isinstance(self.thresh, float):
            self.extr = (-1.e308, 0., 1.e308)
        else:
            self.extr = (-65535, 0, 65535)


    def connect(self):
        super().connect() # call base connect method
        if self.web: # connect to web server
            KnovaTool.unitlist["web"].register((self.name,"set","thresh"), self.setthresh)
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)
        # add manual regime

    def setthresh(self, req):
        try:
            if isinstance(self.thresh, float): # avoid thresh?
                thresh = float(req.querydict["value"])
            else:
                thresh = int(req.querydict["value"])
            self.thresh = thresh # plausibility check needed here
        except:
            req.senderror(400)
        else:
            req.sendemptyresponse()


    def propagate(self, origin):
        if self.inputop == "first":
            newval = self.ins[0].state[0] # define missing
        elif self.inputop == "avg":
            newval = self.extr[1]
            for inp in self.ins:
                newval = newval + inp.state[0] # define missing
            newval = newval/len(self.ins)
        elif self.inputop == "max":
            newval = self.extr[0]
            for inp in self.ins:
                newval = max(newval, inp.state[0]) # define missing
        elif self.inputop == "min":
            newval = self.extr[2]
            for inp in self.ins:
                newval = min(newval, inp.state[0]) # define missing
        if self.val is None: # first time, simplified approach
            self.val = newval
            state[0] = int(newval > self.thresh == self.invert)
            super().propagate(origin)
        else:
            self.val = newval # old val not needed actually
            if self.repetitionfilter(): return
            if newval > self.thresh - self.deltaminus and \
               newval < self.thresh + self.deltaplus: # no transition here
                return
            newstate = int(
                ((newval >= self.thresh + self.deltaplus) == self.invert) or
                ((newval <= self.thresh - self.deltaminus) != self.invert))
            if newstate != state[0]:
                state[0] = newstate
                super().propagate(origin)


class KnovaDigitalOut(KnovaMultiTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.invert = conf.get("invert", False)
        self.pin = machine.Pin(conf["pin"], mode=machine.Pin.OUT) #...
        self.defaultstate = conf.get("defaultstate", 0)

        self.state = bytearray(1)
        self.state[0] = self.defaultstate


    def connect(self):
        super().connect() # call base connect method
        if self.web: # connect to web server
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)


    def propagate(self, origin):
        self.state[0] = origin.state[0] != self.invert
        self.pin.value(self.state[0])


def trivialcb():
    time.sleep(2)


if __name__ == '__main__':
    conf = '''[
{"type":"wifinetwork", "ssid":"Wokwi-GUEST", "password":"", "getconf":"https://raw.githubusercontent.com/dcesari/kasanova/main/sensorsmpy/testconf.json"}
]'''

    localconf = '''[
{"name":"but1", "type":"pushbutton","pin":4},
{"name":"but2", "type":"pushbutton","pin":5},
{"name":"but3", "type":"onoffbutton","pin":19,"invert":true},
{"name":"sw1", "type":"timedswitch","timerduration":5, "upstreamconn":["but1"]},
{"name":"sw2", "type":"toggleswitch","upstreamconn":["but2"]},
{"name":"sw3", "type":"onoffswitch","upstreamconn":["but3"]},
{"name":"l1", "type":"digitalout","pin":12,"upstreamconn":["sw1"]},
{"name":"l2", "type":"digitalout","pin":14,"upstreamconn":["sw2"]},
{"name":"l3", "type":"digitalout","pin":27,"upstreamconn":["sw3"]}
]'''

    KnovaMain(conf, trivialcb)
