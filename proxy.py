#!/usr/bin/env python2
import asyncore, sys, time, re, urllib, ConfigParser, threading, time
from socket import *
from urlparse import urlparse,parse_qs

try:
  import xbmc
  import xbmcaddon
  IN_XBMC=True
except (ImportError):
  IN_XBMC=False

def log(msg):
  if IN_XBMC:
    xbmc.log("gomtv proxy: " + msg)
  else:
    print msg

addon = xbmcaddon.Addon(id='plugin.video.gomtv.net')
BLOCK_SIZE=1024 * 8
START_PORT=38234
BUFFER_SIZE=1024 * 1024 * 2

class Buffer:
  def __init__(self,size):
    self.data = bytearray(size)
    self.buf = memoryview(self.data)
    self.used = 0

  def size(self):
    return self.used

  def in_buffer(self):
    return self.buf[self.used:]

  def out_buffer(self):
    return self.buf[:self.used]

  def grow(self,amount):
    self.used += amount

  def discard(self,amount):
    if self.used > amount:
      rest = self.buf[amount:self.used]
      self.buf[:len(rest)] = rest
    self.used -= amount

class HTTPRequest:
  def __init__(self,verb,path,query,headers):
    self.verb = verb
    self.path = path
    self.query = query
    self.headers = headers

  @property
  def resource(self):
    try:
      query =  urllib.urlencode([(k,v) for k in self.query.keys() for v in self.query[k]])
    except (AttributeError, TypeError):
      query = self.query

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
          ,query=parse_qs(url.query) \
          ,headers=getmatch.group(3))



class ProxyConnection(asyncore.dispatcher):
  def __init__(self,sock,sink,buffer_size=BUFFER_SIZE,sink_buffer_size=BUFFER_SIZE):
    asyncore.dispatcher.__init__(self,sock)
    log("Creating %d byte buffer" % buffer_size)
    self._buf = Buffer(buffer_size)
    self.closed = False
    if isinstance(sink,ProxyConnection):
      self.sink = sink
    else:
      self.sink = ProxyConnection(sink,self,buffer_size=sink_buffer_size)

  def handle_write(self):
    if len(self._buf.out_buffer()) > 0:
      sent = 0
      sent = asyncore.dispatcher.send(self,self._buf.out_buffer())
      self._buf.discard(sent)

  def handle_read(self):
    read = 0
    read = self.recv_into(self.sink._buf.in_buffer())
    if read > 0:
      self.sink._buf.grow(read)

  def handle_close(self):
    self.close()
    self.sink.close()

  def send(self,data):
    self._buf.in_buffer()[:len(data)] = data
    self._buf.grow(len(data))

  def writable(self):
    return (not self.connected) or (len(self._buf.out_buffer()) != 0)

  def readable(self):
    return len(self.sink._buf.in_buffer()) != 0

  def recv_into(self, *args):
    try:
      bytes = self.socket.recv_into(*args)
      if bytes == 0:
        # a closed connection is indicated by signaling
        # a read condition, and having recv() return 0.
        self.handle_close()
      return bytes
    except error, why:
      # winsock sometimes throws ENOTCONN
        if why.args[0] in asyncore._DISCONNECTED:
          self.handle_close()
          return 0
        else:
          raise


  @staticmethod
  def process_request(request):
    if request.verb != 'GET':
      return False
    
    url = urlparse(request.query['dest'][0])

    authsock = socket(AF_INET, SOCK_STREAM)
    authsock.connect((url.netloc, 63800))
    authsock.send(request.query['payload'][0])
    authdata = authsock.recv(1024)
    key = authdata[authdata.rfind(",")+1:-1]
    authsock.close()
     
    query = "%s&key=%s" % (url.query,key)
    drange = re.match(r'Range: bytes=(\d+)-',request.headers)
    if drange != None:
      query += '&startpos=' + drange.group(1)

    request.host = url.netloc
    request.path = url.path
    request.query = query
    log("Proxying to %s" % request.url)
    return True

  @staticmethod
  def setup(sock):
    data = ''
    while data.find("\r\n\r\n") == -1:
      data += sock.recv(BLOCK_SIZE)

    eoh = data.find("\r\n\r\n") + 2
    request = HTTPRequest.parse(data[:eoh])
    initial_data = data[(eoh+2):]

    if not ProxyConnection.process_request(request):
      sock.close
      return None
    else:
      if IN_XBMC:
        buf_size = int(float(addon.getSetting('seek_buffer_size'))) << 20
      else:
        buf_size = BUFFER_SIZE
      conn = ProxyConnection(sock,socket(AF_INET, SOCK_STREAM),buffer_size=1<<20,sink_buffer_size=buf_size)
      conn.sink.connect((request.host, 80))
      conn.sink.send(request.http_format())
      conn.sink.send(initial_data)
      return conn

class ProxyServer(asyncore.dispatcher):
  def __init__(self):
    asyncore.dispatcher.__init__(self)
    self.create_socket( AF_INET, SOCK_STREAM )
    self.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1) 
    bound = False
    port = START_PORT

    while (not bound):
      try:
        log("Trying port %d" % port)
        self.bind(( 'localhost', port ))
        self.listen(5)
        bound = True
      except (gaierror, error):
        port += 1
        if port > START_PORT + 100:
          raise
    self.port = port

    log("Bound to port %d" % self.port)

  def handle_accept(self):
    newsock, address = self.accept()
    ProxyConnection.setup(newsock)

def url(params = None):

  if IN_XBMC:
    port_path = xbmc.translatePath('special://temp/gomtv_proxy.txt')
    config = ConfigParser.SafeConfigParser()
    config.read(port_path)
    port = config.get("network","port")
  else:
    port = START_PORT

  if params == None:
    query = ''
  else:
    query = '?' + urllib.urlencode(params)

  return "http://localhost:%s/%s" % (port,query)

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
