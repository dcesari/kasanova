#!/usr/bin/micropython

states = [
    "at1_man1_osf1", "at0_man1_osf1", "at1_man0_osf1", "at0_man0_osf1",
    "at1_man1_osf0", "at0_man1_osf0", "at1_man0_osf0", "at0_man0_osf0",
    "at1_man1_ost1", "at0_man1_ost1", "at1_man0_ost1", "at0_man0_ost1",
    "at1_man1_ost0", "at0_man1_ost0", "at1_man0_ost0", "at0_man0_ost0"
          ]

# events = setman, setnoman, onman, offman, autotrigrise, autotrigdrop,
#  ontimer, ontimerend, offtimer, offtimerend

class KnovaTool:
    unitlist = {}

    def registertool(self)):
        KnovaTool.unitlist[self.name] = self

    def connect(self, origin=None):
        if origin is not None:
            self.ins.append(origin)

        self.outs = []
        # detect connected units and call their connect method in cascade
        for u in self.connectedto:
#            if isinstance(KnovaTool.unitlist[u], Switch):
            self.outs.append(KnovaTool.unitlist[u])
            KnovaTool.unitlist[u].connect(self)

    def getstate(self, req, qs):
        state = {}
        i = 0
        for n in self.state:
            state[i] = n
            i = i + 1
        return state


class DigitalIn(KnovaTool):
    def __init__(self, conf):
        self.name = conf["name"]
        self.buttontype = conf.get("buttontype", "onoff") # onoff or push
        self.pushtype = conf.get("pushtype", "push") # push or release
        self.invert = conf.get("invert", False)
        self.web = conf.get("web", False)

        self.pin = machine.pin(conf["pin"], mode=machine.pin.IN) #...
        self.connectedto = conf.get("connectedto",[])
#        self.defaultstate = conf.get("defaultstate", 0)
        self.initdelay = conf.get("initdelay", 0)

        self.state = bytearr(0)
        self.state[0] = self.defaultstate
        self.registertool()

    def connect(self, origin=None):
        # call base connect method
        KnovaTool.connect(origin)
        # connect to web server
        if self.web:
            KnovaTool.unitlist["web"].register((self.name,"get"), self.getstate)
            if self.buttontype == "onoff":
                KnovaTool.unitlist["web"].register((self.name,"set","on"), self.on)
                KnovaTool.unitlist["web"].register((self.name,"set","off"), self.off)
            else:
                KnovaTool.unitlist["web"].register((self.name,"set","push"), self.push)
        # schedule self.initdelay activate or activate suddendly?

    def activate(self):
        self.signalchange() # required?
        # implement self.invert!
        if self.buttontype == "onoff":
            self.pin.irq(handler=self.on, trigger=machine.Pin.IRQ_HIGH_LEVEL)
            #, priority=1, wake=None, hard=False)
            self.pin.irq(handler=self.off, trigger=machine.Pin.IRQ_LOW_LEVEL)
        else:
            if self.pushtype == "push":
                self.pin.irq(handler=self.push, trigger=machine.Pin.IRQ_RISING)
            else:
                self.pin.irq(handler=self.push, trigger=machine.Pin.IRQ_FALLING)
        

    def signalchange(self):
        for trig in self.outs:
            trig.autotrigchange()

    def on(pin):
        pin.ref.state[0] = 1
        pin.ref.signalchange()

    def off(self):
        self.state[0] = 0
        self.signalchange()

    def push(self):
        self.state[0] = 1
        self.signalchange()


class DigitalOut(KnovaTool):
    def __init__(self, conf):
        self.name = conf["name"]
        self.invert = conf.get("invert", False)
        self.ins = []
        self.web = conf.get("web", False)
        self.pin = conf["pin"]
        self.defaultstate = conf.get(conf["defaultstate"], 0)

        self.state = bytearr(1)
        self.state[0] = self.defaultstate
        self.registertool()

    def connect(self, unitlist):
        if self.web:
            unitlist["web"].register((self.name,"get"), self.getstate)
        self.setoutput()

    def setoutput(self, state=None):
        if state is not None:
            if self.invert: self.state[0] = 1 - state
            else: self.state[0] = state
        # machine.pin(self.pin, self.state[0])~

            
class Switch:
    def __init__(self, conf):
        self.name = conf["name"]
        self.inputop = conf.get("inputop", "or")
        self.connectedto = conf.get("connectedto",[])
        self.ins = []
        self.web = conf.get("web", False)
        self.timerdeflen = conf.get("timerdeflen", 60)
        self.defaultstate = conf.get(conf["defaultstate"], 0)

        if not self.web and len(inputs) == 0:
            raise "no inputs"

        self.state = byterray(4) # auto trig, man, out timer, out
        if len(inputs) > 0: self.state[1] = 0 # automatic
        else: self.state[1] = 1 # manual
        self.state[2] = 0 # output by timer off
        self.state[3] = self.defaultstate # output off
        self.setinput() # call autotrigchange?
        self.registertool()

    def connect(self, origin=None): #, unitlist):

        # call base connect method
        KnovaTool.connect(origin)

        if self.web:
            unitlist["web"].register((self.name,"set","on"), self.onman)
            unitlist["web"].register((self.name,"set","ontimer"), self.ontimer)
            unitlist["web"].register((self.name,"set","off"), self.offman)
            unitlist["web"].register((self.name,"set","offtimer"), self.offtimer)
            unitlist["web"].register((self.name,"set","auto"), self.noman)
            unitlist["web"].register((self.name,"set","man"), self.man)
            unitlist["web"].register((self.name,"get"), self.getstate)
            

    def setinput(self):
        if self.inputop == "and":
            self.state[0] = 1
            for inp in self.ins:
                self.state[0] = self.state[0] and inp.state[0]
        else:
            self.state[0] = 0
            for inp in self.ins:
                self.state[0] = self.state[0] or inp.state[0]

    def setoutput(self):
        self.output.setoutput(self.state[3])
                
    def setman(self, req, qs):
        self.state[1] = 1
        return 0

    def setnoman(self, req, qs):
        self.state[1] = 0
        self.state[2] = 0
        self.state[3] = self.state[0]
        self.setoutput()
        return 0

    def onman(self, req, qs):
        self.state[2] = 0
        self.state[3] = 1
        self.setoutput()
        return 0

    def offman(self, req, qs):
        self.state[2] = 0
        self.state[3] = 0
        self.setoutput()
        return 0

    def autotrigchange(self):
        self.setinput() # set self.state[0]
        if self.state[1] == 0:
            self.state[3] = self.state[0]
            self.setoutput()

    # def autotrigdrop(self):
    #     self.state[0] = 0
    #     if self.state[1] == 0:
    #         self.state[3] = 0

    def ontimer(self, req, qs):
        self.state[2] = 1
        self.state[3] = 1
        self.setoutput()
        return 0

    def ontimerend(self):
        self.state[2] = 0
        if self.state[1] == 0:
            self.state[3] = self.state[0]
        else:
            self.state[3] = 0
        self.setoutput()

    def offtimer(self, req, qs):
        self.state[2] = 1
        self.state[3] = 0
        self.setoutput()
        return 0

    def offtimerend(self):
        self.state[2] = 0
        if self.state[1] == 0:
            self.state[3] = self.state[0]
        else:
            self.state[3] = 1
        self.setoutput()

