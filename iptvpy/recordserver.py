#!/usr/bin/env python2
 
import BaseHTTPServer
#import CGIHTTPServer
#import cgitb; cgitb.enable()  ## This line enables CGI error reporting
import cgi
import os
import ssl
import base64
import json

key = base64.b64encode('ciccio:vero')
noauthpath = '/open/'
apipath = '/api/'
channelist = ['rtr-planeta', 'rossiya-24']

# /api
# GET
#     /channelist
#     /timerlist
# POST
#     /settimer
#     /removetimer
#     /instanttimer
#     /download

# timer {'date': datetime|None, 'weekday': [0,1,...]|None, 'channel': ''.
# 'enabled': True/False, 'duration': sec}

#class AuthHandler(CGIHTTPServer.CGIHTTPRequestHandler): #SimpleHTTPRequestHandler):
class AuthHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    ''' Main class to present webpages and authentication. '''
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_AUTHHEAD(self):
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm=\"Test\"')
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

    def do_GET(self):
        global key, noauthpath
        print self.path
        # authentication zone
        if self.headers.getheader('Authorization') == None:
            self.do_AUTHHEAD()
            self.wfile.write('no auth header received')
        elif self.headers.getheader('Authorization') == 'Basic '+key:
            if self.path.startswith(apipath):
                self.do_apiget()
            else:
                self.do_apiresp(404, "text/plain", "not found")
                # BaseHTTPServer.BaseHTTPRequestHandler.do_GET(self)
        else:
            self.do_AUTHHEAD()
            self.wfile.write(self.headers.getheader('Authorization'))
            self.wfile.write('not authenticated')


    def do_apiget(self):
        path = self.path.split("/")
        if len(path) >= 3:
            if path[2] == "channelist":
                self.do_apiresp(200, "application/json")
                self.wfile.write(json.dumps(channelist))
            if path[2] == "timerlist":
                timerlist = self.timer.list()
                self.do_apiresp(200, "application/json")
                self.wfile.write(json.dumps(timerlist))
        else:
            self.do_apiresp(404, "text/plain", "not found")
                
    def do_apipost(self):
        path = self.path.split("/")
        if len(path) >= 3:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD':'POST',
                         'CONTENT_TYPE':self.headers['Content-Type']}
            )
            if path[2] == "download":
                dest = form.getfirst("dest")
                url = form.getfirst("url")
                if os.path.isdir(dest) and len(url) > 0:
                    threading.Thread(group=None, target=do_download, args=(dest,url))
                    self.do_apiresp(200, "text/plain", "Download started")
                else:
                    self.do_apiresp(400, "text/plain", "Bad request")
            
            if path[2] == "settimer":
                pass

    def do_apiresp(self, status, contentype, content=None):
        self.send_response(status)
#        self.send_header("Server", "LiveProxy")
        self.send_header("Content-type", contentype)
        self.end_headers()
        if content is not None:
            self.wfile.write(content)
        


    def list_directory(self, path):
        """Helper to produce a directory listing (absent index.html).

        Return value is either a file object, or None (indicating an
        error).  In either case, the headers are sent, making the
        interface the same as for send_head().

        """
        self.send_error(403, "No permission to list directory")
        return None

            
os.chdir('documentroot')
 
server_address = ("", 8000)
#handler = CGIHTTPServer.CGIHTTPRequestHandler
handler = AuthHandler
#handler.cgi_directories = ["/cgi"]
handler.have_fork = False
handler.timer = tvTimer(".local")

httpd = BaseHTTPServer.HTTPServer(server_address, handler)
httpd.socket = ssl.wrap_socket(httpd.socket, keyfile='../key.pem', certfile='../cert.pem', server_side=True)
httpd.serve_forever()