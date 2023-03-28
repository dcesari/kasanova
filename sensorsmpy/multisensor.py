#!/usr/bin/micropython

import socket
import select


htmle = """<!DOCTYPE html>
<html>
    <head> <title>Knova</title> </head>
    <body> <h1>Error</h1>
        Code %s
    </body>
</html>
"""

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


class KNovaWebServer:
    def __init__(self, conf):
        self.webhooks = []
        self.allowip = conf.get("allowip", None)
        if type(self.allowip) == str:
            self.allowip = [conf["allowip"]]
        self.listenaddr = conf.get("listenaddr", "0.0.0.0")
        self.port = conf.get("port", 8081)

    def connect(self, unitlist):
        addr = socket.getaddrinfo(self.listenaddr, self.port)[0][-1]
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(addr)
        self.sock.listen(5)
        print('listening on', addr)
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
        print("request from "+ip)
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


    def poll_loop(self):
        ready = self.httpoll.poll(1000)
        # handle errors in select here
        if len(ready) > 0:
            self.http_ready()
            return 1
        return 0


if __name__ == '__main__':
    def webcb(req):
        req.sendresponse("text/json", '{"ciao": 88}')

    ws = KNovaWebServer({"allowip":'127.0.0.1'})
    ws.register(["a","b"], webcb)
    ws.connect(None)
    while True:
        ws.poll_loop()
        print("idle loop")
