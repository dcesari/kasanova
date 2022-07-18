#!/usr/bin/env python2

import os
import glob
import datetime
import json

class tvTimer:
    def __init__(self, timerdir, cmd="/media/hdd/backup/iptv/rec.sh"):
        self.timerdir = timerdir # os.path.join(os.environ["HOME"],"config","systemd","user")
        self.cmd = cmd
        self.defdurationm = 60
        self.defdelaym = 15

class tvTimerSystemd(tvTimer):
    sdwd = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    comstr = "# tvTimer: "
    timertmpl = """
[Unit]
Description=Delayed recording from a tv channel archive
# do not change next line
# tvTimer: %s

[Timer]
OnCalendar=%s
AccuracySec=5
Unit=%s.service
"""
    unittmpl = """
[Unit]
Description=Delayed recording from a tv channel archive

[Service]
Type=oneshot
%sExecStart=/bin/true
%sExecStart=%s %s %s %d %s
#scriptdir/rec.sh channel startts durmin name
"""

    def _timerfile(self, name):
        return os.path.join(self.timerdir, "tv-"+name+".timer")

    def _timername(self, timerfile):
        timerfile = timerfile.replace(os.path.join(self.timerdir, "tv-"),"")
        timerfile = timerfile.replace(".timer","") # use removeprefix in p3
        return timerfile

    def _unitfile(self, name):
        return os.path.join(self.timerdir, "tv-"+name+".service")
        
    def list(self):
        timerlist = glob.glob(self._timerfile("*"))
        cleanlist = []
        for t in timerlist:
            cleanlist.append(self._timername(t))
        return cleanlist

    def remove(self, name):
        try:
            os.unlink(self._timerfile(name))
            os.unlink(self._unitfile(name))
        except:
            pass
#        if os.path.isfile(filename):

    def add(self, timdef):
        try:
            lname = timdef.get("name")
            lchannel = timdef.get("channel")
            lenabled = timdef.get("enabled", True)
            repeat = timdef.get("repeat", [])
            lrepeat = ""
            if len(repeat) > 0:
                for d in repeat:
                    try:
                        lrepeat = lrepeat + self.sdwd[d] + ","
                    except:
                        pass

            ldate = datetime.datetime.strptime(timdef.get("date"), "%Y-%m-%d %H:%M")
            ldurationm = timdef.get("duration", self.defdurationm)
            ldelay = timdef.get("delay", self.defdelaym)
            ldatesched = ldate + datetime.timedelta(minutes=ldurationm + ldelay)

            if len(lrepeat) > 0:
                ldt = lrepeat[:-1] + " *-*-* " + ldatesched.strftime("%H:%M")
            else:
                ldt = ldatesched.strftime("%Y-%m-%d %H:%M")

        except:
            return 1 # error in definition, timer not defined or updated

        try:
            fd = open(self._timerfile(lname), "w")
            fd.write(self.timertmpl % (json.dumps(timdef), ldt, lname))
            fd.close()

            if lenabled:
                dc = "#"; ec = ""
            else:
                dc = ""; ec = "#"
            fd = open(self._unitfile(lname), "w")
            fd.write(self.unittmpl % (dc, ec, self.cmd, lchannel, ldate.strftime("%H%M"), ldurationm, lname))
            fd.close()
        except:
            try:
                os.unlink(self._timerfile(lname))
                os.unlink(self._unitfile(lname))
            except:
                pass
            return 2 # error in writing, timer removed
        return 0 # ok

    def get(self, name):
        timdef = {}
        timerlist = glob.glob(self._timerfile(name))
        try:
            if len(timerlist) == 1:
                fd = open(timerlist[0])
                for l in fd.readlines():
                    if l.startswith(self.comstr):
                        timdef = json.loads(l[len(self.comstr):])
                fd.close()
        except:
            pass # improve
        return timdef

    
if __name__ == "__main__":
    try:
        os.mkdir("testtvtimer")
    except:
        pass
    testtv = tvTimerSystemd(os.path.join(os.getcwd(), "testtvtimer"))
    print(testtv.list())
    r = testtv.add({"name": "provatv", "channel": "grande", "date": "2022-03-05 08:40", "duration": 5})
    print(r)
    r = testtv.add({"name": "chespasso", "channel": "giudecca", "date": "2022-03-12 21:30", "duration": 10})
    print(r)
    r = testtv.add({"name": "piuspesso", "channel": "cannaregio", "date": "2022-03-15 16:00", "duration": 20, "repeat": [1,2,3,4,5]})
    print(r)
    print(testtv.list())
    for e in testtv.list():
        print(testtv.get(e))
    testtv.remove("chespasso")
    print(testtv.list())
               
                     
