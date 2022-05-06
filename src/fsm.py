#!/usr/bin/micropython

state = byterray(4) # auto trig, man, out timer, out

states = [
    "at1_man1_osf1", "at0_man1_osf1", "at1_man0_osf1", "at0_man0_osf1",
    "at1_man1_osf0", "at0_man1_osf0", "at1_man0_osf0", "at0_man0_osf0",
    "at1_man1_ost1", "at0_man1_ost1", "at1_man0_ost1", "at0_man0_ost1",
    "at1_man1_ost0", "at0_man1_ost0", "at1_man0_ost0", "at0_man0_ost0"
          ]

# events = setman, setnoman, onman, offman, autotrigrise, autotrigdrop,
#  ontimer, ontimerend, offtimer, offtimerend

def setman(self):
    self.state[1] = 1

def setnoman(self):
    self.state[1] = 0
    self.state[2] = 0
    self.state[3] = self.state[0]

def onman(self):
    self.state[2] = 0
    self.state[3] = 1

def offman(self):
    self.state[2] = 0
    self.state[3] = 0

def autotrigrise(self):
    self.state[0] = 1
    if self.state[1] == 0:
        self.state[3] = 1

def autotrigdrop(self):
    self.state[0] = 0
    if self.state[1] == 0:
        self.state[3] = 0

def ontimer(self):
    self.state[2] = 1
    self.state[3] = 1

def ontimerend(self):
    self.state[2] = 0
    if self.state[1] == 0:
        self.state[3] = self.state[0]
    else:
        self.state[3] = 0

def offtimer(self):
    self.state[2] = 1
    self.state[3] = 0

def offtimerend(self):
    self.state[2] = 0
    if self.state[1] == 0:
        self.state[3] = self.state[0]
    else:
        self.state[3] = 1

