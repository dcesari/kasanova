#!/usr/bin/micropython

import math
import micropython
import machine
import time

def KnovaDispatcher(conf):
    typ = conf.get("type", "")
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
    return None


class KnovaLPTimer:
    rtlist = []
    ptlist = []
    prec = 1
    int timerid = 0

    def __init__(self):
        self.rtlist = []
        self.ptlist = []
        self.prec = 1
        int self.timerid = 0
    
    def addsingletimer(self, delta, cb, period=0):
        abstime = time.time() + delta # or we receive abs time?
        n = 0
        for n in range(len(self.rtlist)):
            if abstime < self.rtlist[n][0]: break
        # should we conserve timerid for periodic timers?
        self.rtlist.insert(n, (abstime, cb, period, self.timerid))
        ret = self.timerid
        self.timerid += 1
        if self.timerid == -1: self.timerid += 1
        return ret

    def addperiodictimer(self, period, cb):
        self.ptlist.append((0, cb, period)) # useful?
        self.addsingletimer(period, cb, period)

    def checktimer(self):
        now = time.time()
        do while (True):
            if len(self.rtlist) <= 0 return
            if abs(self.rtlist[0][0] - now) < self.prec:
                self.consumetimer()
                now = time.time() # time may have passed in callback
            else:
                return

    def consumetimer(self):
        rt = self.rtlist[0]
        del self.rtlist[0] # rt is not deleted here (empirically)
        # if periodic, schedule next event
        if rt[2] > 0: self.addsingletimer(rt[0], rt[1], rt[2])
        rt[1]() # call after-timer callback

    def canceltimer(self, timerid):
        if timerid == -1: return
        for n in range(len(self.rtlist)):
            if self.rtlist[n][4] == timerid:
                del self.rtlist[n]
                return

class KnovaTimerInstance:
    def __init__(self, engine, delta, cb, period=0):
        self.engine = engine
        self.id = engine.addtimer(delta, cb, period)

    def __delete__(self):
        engine.canceltimer(self.id)

class KnovaTool:
    unitlist = {}
    timercount = 1 # reserve timer n.0 for main loop
    lptimer = KnovaLPTimer()

    def __init__(self, conf):
        self.name = conf["name"]
        self.typ = conf["type"]
        self.id = len(KnovaTool.unitlist) # unique progressive id
        self.upstreamconn = conf.get("upstreamconn",[])
        self.ins = []
        self.outs = []
        self.filterms = conf.get("filterms", 400) # >0 to enable debounce filter
        if self.filterms > 0:
            self.filters = math.ceil(self.filterms/1000) # for wrap check
            self.lastevent = time.ticks_ms()
            self.lasteventnw = time.time()
        self.web = conf.get("web", False)
        self.timer = -1 # KnovaTool.lptimer

        KnovaTool.unitlist[self.name] = self
        


    def connect(self):
        # store upstream unit instances and notify them of the connection
        for u in self.upstreamconn:
            self.ins.append(KnovaTool.unitlist[u])
            KnovaTool.unitlist[u].notifyconnect(self)

    def notifyconnect(self, downstream):
        # store downstream unit instances
        self.outs.append(downstream)

    def connectall():
        # class method for connecting all configured instances
        for u in KnovaTool.unitlist:
            KnovaTool.unitlist[u].connect()


    def activate(self):
        # init timers, must be done if overridden
        self.updateperiod = conf.get("updateperiod", 0)
        if self.updateperiod > 0: # is it acceptable to start timers here?
            KnovaTool.lptimer.addperiodictimer(self.updateperiod, self.periodicupdate)
        return

    def activateall():
        # class method for activating all configured instances
        for u in KnovaTool.unitlist:
            KnovaTool.unitlist[u].activate()


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

    def getstate(self, req, qs):
        state = {}
        i = 0
        for n in self.state:
            state[i] = n
            i = i + 1
        return state


    def gettimer():
        # class method for getting an available global timer
        if KnovaTool.timercount > 3:
            raise
        t = machine.Timer(KnovaTool.timercount)
        KnovaTool.timercount += 1 # check not to exceed (max 3)
        return t

class KnovaPushButton(KnovaTool):
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


class KnovaOnOffButton(KnovaTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.invert = conf.get("invert", False)
        self.pin = machine.Pin(conf["pin"], mode=machine.Pin.IN, pull=machine.Pin.PULL_UP) #...
        self.defaultstate = conf.get("defaultstate", 0)
        self.initdelay = conf.get("initdelay", 0)

        self.state = bytearray(1)
        self.state[0] = self.defaultstate


    def connect(self):
        super().connect() # call base connect method
        if self.web: # connect to web server
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)


    def activate(self):
        super().activate()
        if self.invert:
            self.pin.irq(handler=self.on, trigger=machine.Pin.IRQ_FALLING)
            #, priority=1, wake=None, hard=False)
            self.pin.irq(handler=self.off, trigger=machine.Pin.IRQ_RISING)
        else:
            self.pin.irq(handler=self.on, trigger=machine.Pin.IRQ_RISING)
            self.pin.irq(handler=self.off, trigger=machine.Pin.IRQ_FALLING)
        

    def startpropagate(self, state):
        # self.pin.value() is ignored due to noise filter, trust sign of irq service
        # schedule a state refresh after self.filterms???
        self.state[0] = state != self.invert
        super().propagate(None)

    def on(self, pin):
        if self.noisefilter(): return
        micropython.schedule(self.startpropagate, 1)

    def off(self, pin):
        if self.noisefilter(): return
        micropython.schedule(self.startpropagate, 0)


class KnovaOwBus(KnovaTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.pin = machine.Pin(conf["pin"], mode=machine.Pin.IN, pull=machine.Pin.PULL_UP) #...
        self.initdelay = conf.get("initdelay", 0)
        self.updateperiod = conf.get("updateperiod", 600)

        self.ow = onewire.OneWire(self.pin) # create a OneWire bus
        # ow.scan() # return a list of devices on the bus
        self.ow.reset() # reset the bus


    def activate(self):
        super().activate()
        self.thermo = None
        for out in self.outs:
            if isinstance(out, KnovaOwThermometer):
                self.thermo = ds18x20.DS18X20(self.ow)
                # roms = ds.scan()
                break
        # (updateperiod)...

    def periodicupdate(self):
        if self.thermo is not None:
            self.thermo.convert_temp()
            time.sleep_ms(750)
        super().propagate(None)


class KnovaOwThermometer(KnovaTool):
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


class KnovaToggleSwitch(KnovaTool):
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


    def setman(self, req, qs):
        self.state[1] = 1
        return 0

    def setauto(self, req, qs):
        self.state[1] = 0
        # self.state[0] = self.state[3] # better keep last manual state
        self.state[3] = self.state[0]
        # super().propagate(self) # do not propagate if no change occurs
        return 0

    def onman(self, req, qs):
        self.state[0] = 1
        super().propagate(None)
        return 0

    def offman(self, req, qs):
        self.state[0] = 0
        super().propagate(None)
        return 0

    def toggleman(self, req, qs):
        self.state[0] = 1 - self.state[0]
        super().propagate(None)
        return 0

    def propagate(self, origin):
        if self.state[1] == 1: return # do not update neither propagate in manual state
        # if inp.state[0] == 1:
        self.state[3] = 1 - self.state[3]
        self.state[0] = self.state[3]
        super().propagate(origin)


class KnovaTimedSwitch(KnovaTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.timerduration = conf.get("timerduration", 60)
        self.timermode = "restart"
        self.defaultstate = 0 # conf.get("defaultstate", 0)
        self.state = bytearray(4) # out, man, out timer, auto out
        self.state[2] = 0 # output by timer off
        self.state[0] = self.defaultstate
        self.state[3] = self.defaultstate
#        self.timer = KnovaTool.gettimer()
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
            

    def setman(self, req, qs):
        self.timeroff()
        self.state[1] = 1
        return 0

    def setauto(self, req, qs):
        self.timeroff()
        self.state[1] = 0
        self.state[3] = self.defaultstate
        self.state[0] = self.defaultstate
        super().propagate(None)
        return 0

    def onman(self, req, qs):
        self.timeroff()
        self.state[0] = 1
        super().propagate(None)
        return 0

    def offman(self, req, qs):
        self.timeroff()
        self.state[0] = 0
        super().propagate(None)
        return 0

    def toggleman(self, req, qs):
        self.timeroff()
        self.state[0] = 1 - self.state[0]
        super().propagate(None)
        return 0


    def propagate(self, origin):
        if self.state[1] == 1: return # do not update neither propagate in manual state
        self.state[3] = 1
        self.state[0] = 1
        super().propagate(origin)
        # schedule timer after setting the state, to avoid
        # self.timerend being called before end of propagate
        if self.timermode == "restart":
            
            KnovaTool.lptimer.canceltimer(self.timer) # self.timer.deinit()
            self.timer = -1
            self.state[2] = 1
#            self.timer.init(mode=machine.Timer.ONE_SHOT,
#                            period=self.timerduration*1000,
#                            callback=self.timerend)
            self.timer = KnovaTool.lptimer.addsingletimer(self.timerduration,
                                                          self.timerend)
        elif self.timermode == "ignore":
            if self.state[2] == 1:
                return
            self.state[2] = 1
#            self.timer.init(mode=machine.Timer.ONE_SHOT,
#                            period=self.timerduration*1000,
#                            callback=self.timerend)
            self.timer = KnovaTool.lptimer.addsingletimer(self.timerduration,
                                                          self.timerend)
        elif self.timermode == "increment":
            KnovaTool.lptimer.canceltimer(self.timer) # self.timer.deinit()
            self.timer = -1
#            self.timer.deinit()
            self.timerincr +=1
            self.state[2] = 1
#            self.timer.init(mode=machine.Timer.ONE_SHOT,
#                            period=self.timerduration*1000*self.timerincr,
#                            callback=self.timerend)
            self.timer = KnovaTool.lptimer.addsingletimer(
                self.timerduration*self.timerincr, self.timerend)


    def timerend(self):
        self.timer = -1
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
        KnovaTool.lptimer.canceltimer(self.timer)
        self.timer = -1
#        self.timer.deinit()
        self.timerincr = 0
        self.state[2] = 0


class KnovaOnOffSwitch(KnovaTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.inputop = conf.get("inputop", "or")
        self.timerduration = conf.get("timerduration", 60)
        self.defaultstate = conf.get("defaultstate", 0)
        self.state = bytearray(4) # out, man, out timer, auto out
        self.state[2] = 0 # output by timer off
        self.state[0] = self.defaultstate
        self.state[3] = self.defaultstate
        self.timer = KnovaTool.gettimer()


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
            

    def setman(self, req, qs):
        self.timeroff()
        self.state[1] = 1
        return 0

    def setauto(self, req, qs):
        self.timeroff()
        self.state[1] = 0
        self.state[0] = self.state[3] # set state to automatic state which was updated in background
        super().propagate(None)
        return 0

    def onman(self, req, qs): # does this make sense without setting state[1] == 1?
        self.timeroff()
        self.state[0] = 1
        super().propagate(None)
        return 0

    def offman(self, req, qs):
        self.timeroff()
        self.state[0] = 0
        super().propagate(None)
        return 0

    def toggleman(self, req, qs):
        self.timeroff()
        self.state[0] = 1 - self.state[0]
        super().propagate(None)
        return 0


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


    def ontimer(self, req, qs):
        self.timeroff()
        self.state[0] = 1
        super().propagate(None)
        self.state[2] = 1
        # get period from qs
        self.timer.init(mode=machine.Timer.ONE_SHOT,
                        period=self.timerduration*1000,
                        callback=self.ontimerend)
        return 0

    def ontimerend(self, timer):
        self.state[2] = 0
        if self.state[1] == 0: # auto
            self.state[0] = self.state[3]
        else: # man
            self.state[0] = 0
        micropython.schedule(self.mptimerend, 0)

    def offtimer(self, req, qs):
        self.timeroff()
        self.state[0] = 0
        super().propagate(None)
        self.state[2] = 1
        # get period from qs
        self.timer.init(mode=machine.Timer.ONE_SHOT,
                        period=self.timerduration*1000,
                        callback=self.offtimerend)
        return 0

    def offtimerend(self):
        self.state[2] = 0
        if self.state[1] == 0: # auto
            self.state[0] = self.state[3]
        else:# man
            self.state[0] = 1
        micropython.schedule(self.mptimerend, 1)

    def mptimerend(self, state):
        super().propagate(None)


    def timeroff(self):
        self.timer.deinit()
        self.state[2] = 0

 
class KnovaDigitalOut(KnovaTool):
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
#        for inp in self.ins:
#            self.state[0] = inp.state[0] != self.invert
#            self.pin.value(self.state[0])
        self.state[0] = origin.state[0] != self.invert
        self.pin.value(self.state[0])


if __name__ == '__main__':
    but1 =  KnovaDispatcher({'name':'but1', 'type':'pushbutton','pin':4})
    but2 =  KnovaDispatcher({'name':'but2', 'type':'pushbutton','pin':5})
    but3 =  KnovaDispatcher({'name':'but3', 'type':'onoffbutton','pin':19,
                             'invert':True})
    sw1 = KnovaTimedSwitch({'name':'sw1', 'type':'timedswitch',
                             'timerduration':5, 'upstreamconn':['but1']})
    sw2 = KnovaToggleSwitch({'name':'sw2', 'type':'togglewitch',
                             'upstreamconn':['but2']})
    sw3 = KnovaOnOffSwitch({'name':'sw3', 'type':'onoffswitch',
                             'upstreamconn':['but3']})
    l1 = KnovaDigitalOut({'name':'l1', 'type':'digitalout','pin':12,
                          'upstreamconn':['sw1']})
    l2 = KnovaDigitalOut({'name':'l2', 'type':'digitalout','pin':14,
                          'upstreamconn':['sw2']})
    l2 = KnovaDigitalOut({'name':'l3', 'type':'digitalout','pin':27,
                          'upstreamconn':['sw3']})


    KnovaTool.connectall()
    KnovaTool.activateall()

    time.sleep(10000)
