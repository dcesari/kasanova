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


class KnovaTool:
    unitlist = {}

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
        # do nothing if not overridden
        return

    def activateall():
        # class method for activating all configured instances
        for u in KnovaTool.unitlist:
            KnovaTool.unitlist[u].activate()


    def propagate(self, origin):
        for out in self.outs:
            out.propagate(self)

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
#        self.propagate() # required?
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
        self.timer = machine.Timer(-1)
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
        self.state[2] = 1
        super().propagate(origin)
        # schedule timer after setting the state, to avoid
        # self.timerend being called before end of propagate
        if self.timermode == "restart":
            if self.timer is not None:
                self.timer.deinit()
                self.timer.init(mode=machine.Timer.ONE_SHOT,
                                period=self.timerduration*1000,
                                callback=self.timerend)
        elif self.timermode == "ignore":
            if self.timer is not None:
                return
            self.timer.init(mode=machine.Timer.ONE_SHOT,
                            period=self.timerduration*1000,
                            callback=self.timerend)
        elif self.timermode == "increment":
            if self.timer is not None:
                self.timer.deinit()
            self.timerincr +=1
            self.timer.init(mode=machine.Timer.ONE_SHOT,
                            period=self.timerduration*1000*self.timerincr,
                            callback=self.timerend)


    def timerend(self, timer):
        micropython.schedule(self.mptimerend, 0)

    def mptimerend(self, state):
        self.timeroff()
        self.state[3] = 0
        self.state[0] = 0
        super().propagate(None)


    def timeroff(self):
        if self.timer is not None:
            self.timer.deinit()
        self.timer = None
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
        self.timer = None


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
        # get period from qs
        self.timer = machine.Timer(self.id, mode=machine.Timer.ONE_SHOT,
                                   period=self.timerduration,
                                   callback=self.ontimerend)
        return 0

    def ontimerend(self, timer):
        micropython.schedule(self.mptimerend, 1)

    def offtimer(self, req, qs):
        self.timeroff()
        self.state[0] = 0
        super().propagate(None)
        # get period from qs
        self.timer = machine.Timer(self.id, mode=machine.Timer.ONE_SHOT,
                                   period=self.timerduration,
                                   callback=self.offtimerend)
        return 0

    def offtimerend(self):
        micropython.schedule(self.mptimerend, 0)

    def mptimerend(self, state):
        self.timeroff()
        if self.state[1] == 0: # auto
            self.state[0] = self.state[3]
        else:# man
            self.state[0] = state
        super().propagate(None)


    def timeroff(self):
        if self.timer is not None:
            self.timer.deinit()
        self.timer = None
        self.timerincr = 0
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
                             'upstreamconn':['but1']})
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
