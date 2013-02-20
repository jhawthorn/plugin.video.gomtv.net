#!/usr/bin/env python2
import asyncore, asynchat
import re, urllib, ConfigParser
import socket
from urlparse import urlparse,parse_qsl
from gomutil import *

try:
  import xbmc
  import xbmcaddon
  IN_XBMC=True
  addon = xbmcaddon.Addon(id='plugin.video.gomtv.net')
except (ImportError):
  IN_XBMC=False

def log(msg):
  if IN_XBMC:
    xbmc.log("gomtv proxy: " + msg)
  else:
    print msg

START_PORT=38234

class HTTPRequest:
  def __init__(self,verb,path,query,headers):
    self.verb = verb
    self.path = path
    self.query = query
    self.headers = headers

  @property
  def resource(self):
    query = urllib.urlencode(self.query)

    if len(query) > 0:
      query = '?' + query
    return self.path + query

  @property
  def url(self):
    return "http://%s%s" % (self.host, self.resource)

  def http_format(self):
    return("%s %s HTTP/1.1\r\n%s\r\n" % (self.verb, self.resource, self.headers))

  @property
  def host(self):
    re.search(r'(?:^|\r\n)Host: (.*)',self.headers)

  @host.setter
  def host(self,new_host):
    self.headers = re.sub(r'(^|\r\n)Host: .*', '\1Host: '+new_host,self.headers)

  @staticmethod
  def parse(request):
    getmatch = re.match(r'([A-Z]+) (.+?) HTTP/1\..\r\n(.*)',request, re.DOTALL)
    if getmatch == None:
      return None
    else:
      url = urlparse(getmatch.group(2))
      return HTTPRequest(verb=getmatch.group(1) \
          ,path=url.path \
          ,query=dict(parse_qsl(url.query)) \
          ,headers=getmatch.group(3))

class gom_proxy(asynchat.async_chat):
    def __init__(self, sink, request):
        self.sink = sink
        self.set_terminator(None)

        self.source = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.source.connect((request.host, 80))
        self.source.send(request.http_format())
        asynchat.async_chat.__init__(self, sock=self.source)

    def collect_incoming_data(self, data):
        self.sink.push(data)

def translate_request(request):
    if request.verb != 'GET':
        return False

    remote_ip = request.query.pop('remote_ip')
    payload = request.query.pop('payload')
    drange = re.match(r'Range: bytes=(\d+)-',request.headers)

    request.host = remote_ip
    request.query['key'] = gom_stream_key(request.host, payload)
    if drange != None:
        request.query['startpos='] = drange.group(1)

class http_request_handler(asynchat.async_chat):
    def __init__(self, sock):
        asynchat.async_chat.__init__(self, sock=sock)
        self.ibuffer = []
        self.set_terminator("\r\n\r\n")

    def collect_incoming_data(self, data):
        self.ibuffer.append(data)

    def found_terminator(self):
        self.set_terminator(None)
        headers = "".join(self.ibuffer) + "\r\n\r\n"
        request = HTTPRequest.parse(headers)
        translate_request(request)
        gom_proxy(self, request)

class ProxyServer(asyncore.dispatcher):
  def __init__(self):
    asyncore.dispatcher.__init__(self)
    self.create_socket( socket.AF_INET, socket.SOCK_STREAM )
    self.set_reuse_addr()

    for port in xrange(START_PORT, START_PORT+100):
      try:
        log("Trying port %d" % port)
        self.bind(( 'localhost', port ))
        self.listen(5)
        self.port = port
        break
      except (socket.gaierror, socket.error):
        port += 1
    else:
      raise

    log("Bound to port %d" % self.port)

  def handle_accept(self):
    newsock, address = self.accept()
    http_request_handler(newsock)

def url(dest, payload):
  if IN_XBMC:
    port_path = xbmc.translatePath('special://temp/gomtv_proxy.txt')
    config = ConfigParser.SafeConfigParser()
    config.read(port_path)
    port = config.get("network","port")
  else:
    port = START_PORT

  remote_ip = re.search(r'//([0-9.]+)/', dest).group(1)
  dest = dest.replace(remote_ip, 'localhost:%s' % port)
  dest += '&remote_ip=%s&payload=%s' % (remote_ip, payload)

  return dest

if __name__=="__main__":
  try:
    server = ProxyServer()

    if IN_XBMC:
      port_path = xbmc.translatePath('special://temp/gomtv_proxy.txt')
      config = ConfigParser.SafeConfigParser()
      config.add_section("network")
      config.set("network","port","%d" % server.port)

      with open(port_path,'w') as f:
        config.write(f)

      while (not xbmc.abortRequested):
        try:
          asyncore.loop(count=1,timeout=2)
        except Exception:
          pass
    else:
      asyncore.loop()

  except KeyboardInterrupt:
    pass
  log("Exiting")
