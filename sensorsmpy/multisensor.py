#!/usr/bin/micropython

import socket
import select

pins={1:'on', 2:'on', 3:'off'}
html = """<!DOCTYPE html>
<html>
    <head> <title>ESP32 Pins</title> </head>
    <body> <h1>ESP32 Pins</h1>
        <table border="1"> <tr><th>Pin</th><th>Value</th></tr> %s </table>
    </body>
</html>
"""

htmle = """<!DOCTYPE html>
<html>
    <head> <title>ESP32 Pins</title> </head>
    <body> <h1>Error</h1>
        Code %s
    </body>
</html>
"""

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
        self.sock.bind(addr)
        self.sock.listen(1)
        print('listening on', addr)
        self.httpoll = select.poll()
        self.httpoll.register(self.sock, select.POLLIN)

    def register(self, req, callback):
        self.webhooks.append((req, callback))

    def req_decode(self, reqfull):
        resource = []
        querystring = None
        try:
            req = str(reqfull).split(" ")[1]
            rq = req.split("?")
            resource = rq[0].split("/")
            if len(rq) > 1:
                querystring = rq[1].split("&")
        except:
            pass
        return resource, querystring

    def http_ready(self):
        cl, addr = self.sock.accept()
        #    print('client connected from', addr)
        ip = socket.inet_ntop(socket.AF_INET,addr[4:8]) # indovinato
        print("request from "+ip)
        cl_file = cl.makefile('rwb', 0)
        req = cl_file.readline(1024)
        res, qs = self.req_decode(req)
        print(res)
        print(qs)
        auth = False
        if self.allowip is not None:
            for i in self.allowip:
                print(i)
                print(ip)
                if ip == i:
                    auth = True
        else:
            auth = True

        while True:
            line = cl_file.readline()
            if not line or line == b'\r\n':
                break
        if auth:
            rows = ['<tr><td>%s</td><td>%s</td></tr>' % (str(p), pins[p]) for p in pins]
            response = html % '\n'.join(rows)
            htcode = '200'
        else:
            htcode = '400'
            response = htmle % (htcode,)
            print(response)
        cl.send(b'HTTP/1.0 '+htcode+' OK\r\nContent-type: text/html\r\nConnection: close\r\n\r\n')
        r = bytes(response,"ascii")
        print(r)
        cl.send(r)
#        cl.send(bytes(response,"ascii"))
        cl.close()

    def poll_loop(self):
        ready = self.httpoll.poll(1000)
        # handle errors in select here
        if len(ready) > 0:
            self.http_ready()
            return 1
        return 0


if __name__ == '__main__':
#    ws = KNovaWebServer({"allowip":('127.0.0.1',)})
    ws = KNovaWebServer({"allowip":'127.0.0.1'})
    ws.connect(None)
    while True:
        ws.poll_loop()
        print("idle loop")
