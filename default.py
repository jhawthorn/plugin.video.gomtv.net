import urllib, urllib2, re, xbmcplugin, xbmcgui, os, xbmc, cookielib, socket
from BeautifulSoup import BeautifulSoup

BASE_COOKIE_PATH = os.path.join(xbmc.translatePath( "special://profile/" ), "addon_data", os.path.basename(os.getcwd()), 'cookie.txt')
handle = int(sys.argv[1])

end_dir = False

def get_cookie_jar():
    cookie_jar = cookielib.LWPCookieJar(BASE_COOKIE_PATH)
    if not os.path.exists(os.path.dirname(BASE_COOKIE_PATH)):
        os.makedirs(os.path.dirname(BASE_COOKIE_PATH))
    if (os.path.isfile(BASE_COOKIE_PATH)):
        cookie_jar.load(BASE_COOKIE_PATH)
    return cookie_jar

def request(url, data=None):
    cookie_jar = get_cookie_jar()
    urllib2.install_opener(urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie_jar)))
    
    if data is not None:
        data = urllib.urlencode(data)
        req = urllib2.Request(url, data)
    else:
        req = urllib2.Request(url)
    response = urllib2.urlopen(req)
    ret = response.read()
    response.close()
    cookie_jar.save()
    return ret

def login(username, password):
    ret = request("http://www.gomtv.net/user/loginProcess.gom", {"mb_username": username,
                                                                 "mb_password": password,
                                                                 "cmd": "login",
                                                                 "rememberme": "1"})
    return ret == "1"
    
def mainlist():
    if not login(xbmcplugin.getSetting(handle, "username"), xbmcplugin.getSetting(handle, "password")):
        xbmcgui.Dialog().ok("Login failed", "login failed")
    else:
        ret = addDir("Most recent", "http://www.gomtv.net/videos/index.gom?page=1", 1, "")
        ret = addDir("Most viewed", "http://www.gomtv.net/videos/index.gom?page=1&order=2", 1, "")
        ret = addDir("Most replied", "http://www.gomtv.net/videos/index.gom?page=1&order=3&ltype=", 1, "")
        return ret

def addLink(name, url, iconimage):
    global end_dir
    end_dir = True
    name = name.encode("utf-8")
    li = xbmcgui.ListItem(name, iconImage="DefaultVideo.png", thumbnailImage=iconimage)
    li.setInfo( type="Video", infoLabels={ "Title": name } )
    li.setProperty('mimetype', 'video/x-flv')
    return xbmcplugin.addDirectoryItem(handle = handle,
                                       url = url,
                                       listitem = li)

def addDir(name, url, mode, iconimage):
    global end_dir
    end_dir = True
    name = name.encode("utf-8")
    url = "%s?url=%s&mode=%s&name=%s" % (sys.argv[0], urllib.quote_plus(url), str(mode), urllib.quote_plus(name))
    li = xbmcgui.ListItem(name, iconImage="DefaultFolder.png", thumbnailImage=iconimage)
    li.setInfo( type="Video", infoLabels={ "Title": name } )
    return xbmcplugin.addDirectoryItem(handle = handle,
                                       url = url,
                                       listitem = li,
                                       isFolder = True)

def vod_list(url):
    soup = BeautifulSoup(request(url))
    thumb_links = soup.findAll("td", {"class": "listOff"})
    for thumb_link in thumb_links:
        href = thumb_link.find("a", "thumb_link")["href"]
        iconimage = thumb_link.find("img", "vodthumb")["src"]
        name = thumb_link.find("a", "thumb_link")["title"]
        addDir(name, "http://www.gomtv.net%s" % href.replace("/./", "/"), 2, iconimage)
    page = int(re.search("page=([0-9]+)", url).group(1))
    addDir("Next", url.replace("page=%d" % page, "page=%d" % (page + 1)), 1, "")

def get_stream_key(server_ip, uno, nodeid, local_ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((server_ip, 63800))
    payload = "Login,0,%s,%s,%s\n" % (uno, nodeid, local_ip)
    xbmc.log("payload: %s" % payload, xbmc.LOGDEBUG)
    s.send(payload)
    data = s.recv(1024)
    s.close()
    return data[data.rfind(",")+1:-1]
    
def vod(url):
    r = request(url)
    leagueid = re.search('"leagueid"\s*:\s*"(.*)",', r).group(1)
    soup = BeautifulSoup(r)
    match_sets = soup.find("div", "matchset_set").findAll("a")
    i = 1
    for match_set in match_sets:
        vjoinid = match_set["onclick"]
        vjoinid = vjoinid[vjoinid.find("vjoinid':")+len("vjoinid':"):-1]
        vjoinid = vjoinid[0:vjoinid.find("}")]
        url = "http://www.gomtv.net/gox/gox.gom?&target=vod&leagueid=%s&vjoinid=%s&strLevel=HQ&" % (leagueid, vjoinid)
        r = request(url)
        if "ErrorMessage" in r:
            return
        
        url = re.search("href='(.*)'", r).group(1)
        url = url.replace("&amp;", "&")
        
        uno = re.search("uno=([0-9]+)", url).group(1)
        nodeid = re.search("nodeid=([0-9]+)", url).group(1)
        ip = re.search("ip=([0-9.]+)", url).group(1)
        remote_ip = re.search("//([0-9.]+)/", url).group(1)
        key = get_stream_key(remote_ip, uno, nodeid, ip)
        
        url = url + "&key=" + key

        name = "Set %d" % i
        i = i + 1
        addLink(name, url, "")


def get_params():
    param=[]
    paramstring=sys.argv[2]
    xbmc.log( "get_params() %s" % paramstring, xbmc.LOGDEBUG )
    if len(paramstring)>=2:
        params=sys.argv[2]
        cleanedparams=params.replace('?','')
        if (params[len(params)-1]=='/'):
            params=params[0:len(params)-2]
        pairsofparams=cleanedparams.split('&')
        param={}
        for i in range(len(pairsofparams)):
            splitparams={}
            splitparams=pairsofparams[i].split('=')
            if (len(splitparams))==2:
                param[splitparams[0]]=splitparams[1]
                        
    return param
        
params = get_params()
url = None
name = None
mode = None

try: url=urllib.unquote_plus(params["url"])
except: pass
try: name=urllib.unquote_plus(params["name"])
except: pass
try: mode=int(params["mode"])
except: pass

xbmc.log( "Mode: "+str(mode), xbmc.LOGINFO)
xbmc.log( "URL : "+str(url), xbmc.LOGINFO)
xbmc.log( "Name: "+str(name), xbmc.LOGINFO)

if mode == None or url == None or len(url) < 1:
    mainlist()
elif mode == 1:
    vod_list(url)
elif mode == 2:
    vod(url)

if end_dir:
    xbmcplugin.endOfDirectory(int(sys.argv[1]))
