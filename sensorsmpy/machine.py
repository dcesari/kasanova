# dummy machine module for unix port

import _thread

class Pin:
    IN = 1
    OUT = 2
    OPEN_DRAIN = 3
    ALT_OPEN_DRAIN = 4
    ANALOG = 5
    PULL_UP = 1
    PULL_DOWN = 2
    PULL_HOLD = 3
    IRQ_FALLING = 1
    IRQ_RISING = 2
    IRQ_LOW_LEVEL = 4
    IRQ_HIGH_LEVEL = 8
    thread = None
    threadstarted = False
    lock = None
    pinlist = {}
    modestr = (None, "IN", "OUT", "OPEN DRAIN", "ALT OPEN DRAIN")


    def __init__(self, pinid, mode=-1, pull=-1, value=None, drive=0, alt=-1):
        self.pinid = str(pinid)
        if mode != -1: self.mode = mode
        if pull != -1: self.pull = pull
        if self.mode == Pin.OUT or self.mode == Pin.OPEN_DRAIN:
            if value is not None:
                self.ovalue = value
        if not hasattr(self, "ovalue"):
            if value is not None:
                self.ovalue = value
            else:
                self.ovalue = 0

        if not hasattr(self, "handler"):
            self.handler = None
            self.trigger = 0

        self.obuf = 0
        self.handler = None

        if Pin.lock is not None: Pin.lock.acquire()
        Pin.pinlist[self.pinid] = self
        if Pin.lock is not None: Pin.lock.release()

        if not Pin.threadstarted:
            Pin.thread =_thread.start_new_thread(Pin.pinteract,(0,))
            Pin.threadstarted = True
            Pin.lock = _thread.allocate_lock()

    def init(self, mode=-1, pull=-1, value=None, drive=0, alt=-1):
        self.__init__(self.pinid, mode, pull, value, drive, alt)


    def value(self, x=None):
        if x is not None:
            if self.mode == Pin.IN:
                self.obuf = x
            elif self.mode == Pin.OUT:
                Pin.lock.acquire()
                self.ovalue = x
                Pin.lock.release()
            elif self.mode == Pin.OPEN_DRAIN:
                self.state = x
        else:
            if self.mode == Pin.IN or self.mode == Pin.OUT:
                return self.ovalue
            elif self.mode == Pin.OPEN_DRAIN:
                if self.state == 1:
                    return self.ovalue


    def __call__(self, x=None):
        return self.value(x)


    def irq(self, handler=None, trigger=0, priority=1, wake=None, hard=False):
        self.handler = handler
        self.trigger = trigger


    def pinteract(arg):
        while (True):
            Pin.lock.acquire()
            for mode in (Pin.IN, Pin.OUT, Pin.OPEN_DRAIN, Pin.ALT_OPEN_DRAIN):
                head = True
                for pin in Pin.pinlist:
                    if Pin.pinlist[pin].mode == mode:
                        if head:
                            print(f"pins {Pin.modestr[mode]}")
                            head = False
                        print(f"{pin} ==> {Pin.pinlist[pin].value()}")
            Pin.lock.release()
            op = input("for changing a value: <pinid> <value> ")
            ops = op.split(" ")
            if len(ops) == 2:
                try:
                    pin = Pin.pinlist[ops[0]]
                    new = int(ops[1])
                except:
                    print("wrong input")
                    continue
                Pin.lock.acquire()
                if pin.mode == Pin.IN:
                    cur = pin.value()
                    pin.ovalue = new
                elif pin.mode == Pin.OUT:
                    cur = pin.obuf
                    pin.obuf = new
                Pin.lock.release()
                if pin.handler is not None:
                    if (new > cur and pin.trigger & Pin.IRQ_RISING) or \
                       (new < cur and pin.trigger & Pin.IRQ_FALLING):
                        print("calling irq", pin.handler)
                        pin.handler(pin)


                        


if __name__ == '__main__':
    import time

    def event(pin):
        print("Event happened ", pin.value())
    
    pi = Pin(8, Pin.IN, pull=Pin.PULL_UP)
    po = Pin(9, Pin.OUT, pull=None, value=1)
    pi.irq(event, Pin.IRQ_RISING)
    po.value(0)
    time.sleep(120)


