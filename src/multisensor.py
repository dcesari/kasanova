#!/usr/bin/micropython

import socket
import select

pins={1:'on', 2:'on', 3:'off'}
html = """<!DOCTYPE html>
<html>
    <head> <title>ESP8266 Pins</title> </head>
    <body> <h1>ESP8266 Pins</h1>
        <table border="1"> <tr><th>Pin</th><th>Value</th></tr> %s </table>
    </body>
</html>
"""

def req_decode(reqfull):
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

def http_loop(s):
    cl, addr = s.accept()
#    print('client connected from', addr)
    ip = socket.inet_ntop(socket.AF_INET,addr[4:8]) # indovinato
    print("request from "+ip)
    cl_file = cl.makefile('rwb', 0)
    req = cl_file.readline(1024)
    res, qs = req_decode(req)
    print(res)
    print(qs)
    while True:
        line = cl_file.readline()
        if not line or line == b'\r\n':
            break
    rows = ['<tr><td>%s</td><td>%s</td></tr>' % (str(p), pins[p]) for p in pins]
    response = html % '\n'.join(rows)
    cl.send(b'HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
    cl.send(bytes(response,"ascii"))
    cl.close()


def idle_loop():
    print("idle loop")

addr = socket.getaddrinfo('0.0.0.0', 8081)[0][-1]
s = socket.socket()
s.bind(addr)
s.listen(1)
print('listening on', addr)

httpoll = select.poll()
httpoll.register(s, select.POLLIN)

while True:
    ready = []
    while len(ready) == 0:
        idle_loop()
        ready = httpoll.poll(1000)
    # handle errors in select here
    http_loop(s)

    
