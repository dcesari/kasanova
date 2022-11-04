#!/usr/bin/micropython

#states = [
#    "at1_man1_osf1", "at0_man1_osf1", "at1_man0_osf1", "at0_man0_osf1",
#    "at1_man1_osf0", "at0_man1_osf0", "at1_man0_osf0", "at0_man0_osf0",
#    "at1_man1_ost1", "at0_man1_ost1", "at1_man0_ost1", "at0_man0_ost1",
#    "at1_man1_ost0", "at0_man1_ost0", "at1_man0_ost0", "at0_man0_ost0"
#          ]

# events = setman, setnoman, onman, offman, autotrigrise, autotrigdrop,
#  ontimer, ontimerend, offtimer, offtimerend

import math
import micropython
import machine
import time

def KnovaDispatcher(conf):
    typ = conf.get("type", "")
    if conf["type"] == "onoffbutton":
        return KnovaOnOffButton(conf)
    if conf["type"] == "pushbutton":
        return KnovaPushButton(conf)
    if conf["type"] == "onoffswitch":
        return KnovaOnOffSwitch(conf)
    if conf["type"] == "toggleswitch":
        return KnovaToggleSwitch(conf)
    if conf["type"] == "timedswitch":
        return KnovaTimedSwitch(conf)
    if conf["type"] == "digitalout":
        return KnovaDigitalOut(conf)
    return None


class KnovaTool:
    unitlist = {}

    def __init__(self, conf):
        self.name = conf["name"]
        self.typ = conf["type"]
        self.id = len(KnovaTool.unitlist) # unique progressive id
        self.connectedto = conf.get("connectedto",[])
        self.ins = []
        self.outs = []
        self.filterms = conf.get("filterms", -1) # >0 to enable debounce filter
        if self.filterms > 0:
            self.filters = math.ceil(self.filterms/1000) # for wrap check
            self.lastevent = time.ticks_ms()
            self.lasteventnw = time.time()
        self.web = conf.get("web", False)
        KnovaTool.unitlist[self.name] = self

    def connect(self, origin=None):
        # detect upstream units
        if origin is not None:
            self.ins.append(origin)
        # detect downstream units and call their connect method in cascade
        for u in self.connectedto:
            self.outs.append(KnovaTool.unitlist[u])
            KnovaTool.unitlist[u].connect(self)

    def propagate(self):
        for out in self.outs:
            out.propagate()

    def noisefilter(self):
        if self.filterms > 0:
            now = time.ticks_ms()
            nownw = time.time() # wrap check
            if time.ticks_diff(now - self.lastevent) < self.filterms and \
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
        self.pin = machine.Pin(conf["pin"], mode=machine.Pin.IN) #...
        self.initdelay = conf.get("initdelay", 0)

        self.state = bytearray(1)
        self.state[0] = 0


    def connect(self, origin=None):
        super().connect(origin) # call base connect method
        if self.web: # connect to web server
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)
            KnovaTool.unitlist["web"].register((self.name,"set","pushrelease"), self.push)
        # schedule self.initdelay activate or activate suddendly?


    def activate(self):
        cond = (self.pushtype == "push") != self.invert
        if cond:
            self.pin.irq(handler=self.push, trigger=machine.Pin.IRQ_RISING)
        else:
            self.pin.irq(handler=self.push, trigger=machine.Pin.IRQ_FALLING)


    def propagate(self):
        if self.noisefilter(): return
        super().propagate

    def push(self, pin):
        self.state[0] = 1 # will never change after first pushrelease?!
        micropython.schedule(self.propagate, 0)


class KnovaOnOffButton(KnovaTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.invert = conf.get("invert", False)
        self.pin = machine.Pin(conf["pin"], mode=machine.Pin.IN) #...
        self.defaultstate = conf.get("defaultstate", 0)
        self.initdelay = conf.get("initdelay", 0)

        self.state = bytearray(1)
        self.state[0] = self.defaultstate


    def connect(self, origin=None):
        super().connect(origin) # call base connect method
        if self.web: # connect to web server
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)
#            KnovaTool.unitlist["web"].register((self.name,"set","on"), self.on)
#            KnovaTool.unitlist["web"].register((self.name,"set","off"), self.off)
        # schedule self.initdelay activate or activate suddendly?

    def activate(self):
        self.propagate() # required?
        if self.invert:
            self.pin.irq(handler=self.on, trigger=machine.Pin.IRQ_FALLING)
            #, priority=1, wake=None, hard=False)
            self.pin.irq(handler=self.off, trigger=machine.Pin.IRQ_RISING)
        else:
            self.pin.irq(handler=self.on, trigger=machine.Pin.IRQ_RISING)
            self.pin.irq(handler=self.off, trigger=machine.Pin.IRQ_FALLING)
        

    def propagate(self):
        if self.noisefilter(): return
        # schedule a state refresh after self.filterms???
        self.state[0] = self.pin.value() != self.invert
        super().propagate

    def on(self, pin):
#        self.state[0] = 1
        micropython.schedule(self.propagate, 0)

    def off(self, pin):
#        self.state[0] = 0
        micropython.schedule(self.propagate, 0)


class KnovaDigitalOut(KnovaTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.invert = conf.get("invert", False)
        self.pin = machine.Pin(conf["pin"], mode=machine.Pin.OUT) #...
        self.defaultstate = conf.get("defaultstate", 0)

        self.state = bytearray(1)
        self.state[0] = self.defaultstate


    def connect(self, origin=None):
        super().connect(origin)
        if self.web:
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)


    def propagate(self):
        for inp in self.ins:
            self.state[0] = inp.state[0] != self.invert
        # machine.Pin(self.pin, self.state[0])~

            
class KnovaToggleSwitch(KnovaTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.timerdeflen = conf.get("timerdeflen", 60)
        self.defaultstate = conf.get("defaultstate", 0)
        self.state = bytearray(4) # out, man, out timer, auto out
        self.state[2] = 0 # output by timer off
        self.state[0] = self.defaultstate
        self.state[3] = self.defaultstate


    def connect(self, origin=None): #, unitlist):
        KnovaTool.connect(origin) # call base connect method
        if len(ins) > 0: self.state[1] = 0 # automatic
        else: self.state[1] = 1 # manual
        if self.web: # connect to web server
            KnovaTool.unitlist["web"].register((self.name,"set","on"), self.onman)
            KnovaTool.unitlist["web"].register((self.name,"set","ontimer"), self.ontimer)
            KnovaTool.unitlist["web"].register((self.name,"set","off"), self.offman)
            KnovaTool.unitlist["web"].register((self.name,"set","offtimer"), self.offtimer)
            KnovaTool.unitlist["web"].register((self.name,"set","toggle"), self.toggleman)
            KnovaTool.unitlist["web"].register((self.name,"set","auto"), self.noman)
            KnovaTool.unitlist["web"].register((self.name,"set","man"), self.man)
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)
            

    def setman(self, req, qs):
        self.state[1] = 1
        return 0

    def setnoman(self, req, qs):
        self.state[1] = 0
        self.state[2] = 0
        # self.state[0] = self.state[3] # better keep last manual state
        self.state[3] = self.state[0]
        self.setoutput()
        return 0

    def onman(self, req, qs):
        self.state[2] = 0
        self.state[0] = 1
        self.setoutput()
        return 0

    def offman(self, req, qs):
        self.state[2] = 0
        self.state[0] = 0
        self.setoutput()
        return 0

    def toggleman(self, req, qs):
        self.state[2] = 0
        self.state[0] = 1 - self.state[0]
        self.setoutput()
        return 0

    def propagate(self): # consider adding a second argument to disable toggle
        if self.state[1] == 1: return # do not update and propagate in manual state
        for inp in self.ins:
            if inp.state[0] == 1:
                self.state[3] = 1 - self.state[3]
                self.state[0] = self.state[3]
                super().propagate
                return


class KnovaOnOffSwitch(KnovaTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.inputop = conf.get("inputop", "or")
        self.timerdeflen = conf.get("timerdeflen", 60)
        self.defaultstate = conf.get("defaultstate", 0)
        self.state = bytearray(4) # out, man, out timer, auto out
        self.state[2] = 0 # output by timer off
        self.state[0] = self.defaultstate
        self.state[3] = self.defaultstate
        self.timer = None


    def connect(self, origin=None): #, unitlist):
        KnovaTool.connect(origin) # call base connect method
        if len(ins) > 0: self.state[1] = 0 # automatic
        else: self.state[1] = 1 # manual
        if self.web: # connect to web server
            KnovaTool.unitlist["web"].register((self.name,"set","on"), self.onman)
            KnovaTool.unitlist["web"].register((self.name,"set","ontimer"), self.ontimer)
            KnovaTool.unitlist["web"].register((self.name,"set","off"), self.offman)
            KnovaTool.unitlist["web"].register((self.name,"set","offtimer"), self.offtimer)
            KnovaTool.unitlist["web"].register((self.name,"set","toggle"), self.toggleman)
            KnovaTool.unitlist["web"].register((self.name,"set","auto"), self.noman)
            KnovaTool.unitlist["web"].register((self.name,"set","man"), self.man)
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)
            

    def setman(self, req, qs):
        if self.timer is not None:
            self.timer.deinit()
            self.timer = None
        self.state[1] = 1
        return 0

    def setnoman(self, req, qs):
        if self.timer is not None:
            self.timer.deinit()
            self.timer = None
        self.state[1] = 0
        self.state[2] = 0
        self.state[3] = self.state[0]
        self.setoutput()
        return 0

    def onman(self, req, qs): # does this make sense without setting state[1] == 1?
        if self.timer is not None:
            self.timer.deinit()
            self.timer = None
        self.state[2] = 0
        self.state[0] = 1
        self.setoutput()
        return 0

    def offman(self, req, qs):
        if self.timer is not None:
            self.timer.deinit()
            self.timer = None
        self.state[2] = 0
        self.state[0] = 0
        self.setoutput()
        return 0

    def toggleman(self, req, qs):
        if self.timer is not None:
            self.timer.deinit()
            self.timer = None
        self.state[2] = 0
        self.state[0] = 1 - self.state[0]
        self.setoutput()
        return 0

    def propagate(self):
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
        super().propagate


    def ontimer(self, req, qs):
        if self.timer is not None:
            self.timer.deinit()
        self.state[2] = 1
        self.state[0] = 1
        self.setoutput()
        # get period from qs
        self.timer = machine.Timer(self.id, mode=machine.Timer.ONE_SHOT,
                                   period=10000, callback=self.ontimerend)
        return 0

    def ontimerend(self, timer):
        self.timer = None
        self.state[2] = 0
        if self.state[1] == 0: # auto
            self.state[0] = self.state[3]
        else: # man
            self.state[0] = 0
        micropython.schedule(self.setoutput()) # schedule to stay on button side

    def offtimer(self, req, qs):
        if self.timer is not None:
            self.timer.deinit()
        self.state[2] = 1
        self.state[0] = 0
        self.setoutput()
        # get period from qs
        self.timer = machine.Timer(self.id, mode=machine.Timer.ONE_SHOT,
                                   period=10000, callback=self.offtimerend)
        return 0

    def offtimerend(self):
        self.timer = None
        self.state[2] = 0
        if self.state[1] == 0: # auto
            self.state[0] = self.state[3]
        else:# man
            self.state[0] = 1
        micropython.schedule(self.setoutput()) # schedule to stay on button side


class KnovaTimedSwitch(KnovaTool):
    def __init__(self, conf):
        super().__init__(conf)
        self.timerdeflen = conf.get("timerdeflen", 60)
        self.defaultstate = conf.get("defaultstate", 0)
        self.state = bytearray(4) # out, man, out timer, auto out
        self.state[2] = 0 # output by timer off
        self.state[0] = self.defaultstate
        self.state[3] = self.defaultstate
        self.timer = None
        self.timerincr = 0


    def connect(self, origin=None): #, unitlist):
        KnovaTool.connect(origin) # call base connect method
        if len(ins) > 0: self.state[1] = 0 # automatic
        else: self.state[1] = 1 # manual
        if self.web: # connect to web server
            KnovaTool.unitlist["web"].register((self.name,"set","on"), self.onman)
            KnovaTool.unitlist["web"].register((self.name,"set","ontimer"), self.ontimer)
            KnovaTool.unitlist["web"].register((self.name,"set","off"), self.offman)
            KnovaTool.unitlist["web"].register((self.name,"set","offtimer"), self.offtimer)
            KnovaTool.unitlist["web"].register((self.name,"set","toggle"), self.toggleman)
            KnovaTool.unitlist["web"].register((self.name,"set","auto"), self.noman)
            KnovaTool.unitlist["web"].register((self.name,"set","man"), self.man)
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)
            

    def setman(self, req, qs):
        if self.timer is not None:
            self.timer.deinit()
        self.state[1] = 1
        return 0

    def setnoman(self, req, qs):
        if self.timer is not None:
            self.timer.deinit()
        self.state[1] = 0
        self.state[2] = 0
        self.state[3] = self.defaultstate
        self.state[0] = self.defaultstate
        self.setoutput()
        return 0

    def onman(self, req, qs):
        if self.timer is not None:
            self.timer.deinit()
        self.state[2] = 0
        self.state[0] = 1
        self.setoutput()
        return 0

    def offman(self, req, qs):
        if self.timer is not None:
            self.timer.deinit()
        self.state[2] = 0
        self.state[0] = 0
        self.setoutput()
        return 0

    def toggleman(self, req, qs):
        if self.timer is not None:
            self.timer.deinit()
        self.state[2] = 0
        self.state[0] = 1 - self.state[0]
        self.setoutput()
        return 0

    def propagate(self):
        if self.state[1] == 1: return # do not update and propagate in manual state
        # add check on ins.state
        if self.timermode == "restart":
            if self.timer is not None:
                self.timer.deinit()
            self.timer= machine.Timer(self.id, mode=machine.Timer.ONE_SHOT,
                                      period=self.timerdeflen*1000,
                                      callback=self.timerend)
        elif self.timermode == "ignore":
            if self.timer is not None:
                return
            self.timer= machine.Timer(self.id, mode=machine.Timer.ONE_SHOT,
                                      period=self.timerdeflen*1000,
                                      callback=self.timerend)
        elif self.timermode == "increment":
            if self.timer is not None:
                self.timer.deinit()
            self.timerincr +=1
            self.timer= machine.Timer(self.id, mode=machine.Timer.ONE_SHOT,
                                      period=self.timerdeflen*1000*self.timerincr,
                                      callback=self.timerend)
            
        self.state[0] = 1
        super().propagate


    def timerend(self, timer):
        self.timer = None
        self.timerincr = 0
        self.state[0] = 0
        super().propagate

if __name__ == '__main__':
    but1 =  KnovaDispatcher({'name':'but1', 'type':'pushbutton','pin':4,
    'connectto':['sw1']})
    but2 =  KnovaDispatcher({'name':'but2', 'type':'pushbutton','pin':5,
    'connectto':['sw2']})
    but3 =  KnovaDispatcher({'name':'but3', 'type':'onoffbutton','pin':19,
    'connectto':['sw3']})
    sw1 = KnovaToggleSwitch({'name':'sw1', 'type':'timedswitch','pin':19,
    'connectto':['l1']})
    sw2 = KnovaToggleSwitch({'name':'sw2', 'type':'togglewitch','pin':19,
    'connectto':['l2']})
    sw3 = KnovaToggleSwitch({'name':'sw3', 'type':'onoffswitch','pin':19,
    'connectto':['l2']})
    l1 = KnovaDigitalOut({'name':'l1', 'type':'digitalout','pin':12})
    l1 = KnovaDigitalOut({'name':'l2', 'type':'digitalout','pin':27})

    but1.connect()
    but2.connect()
    but3.connect()

    but1.activate()
    but2.activate()
    but3.activate()
    time.sleep(10000)
