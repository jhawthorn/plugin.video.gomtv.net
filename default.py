import urllib, urllib2, re, xbmcplugin, xbmcgui, os, xbmc, cookielib, socket
from BeautifulSoup import BeautifulSoup
from gomtv import GOMtv, NoBroadcastException, NotLoggedInException

BASE_COOKIE_PATH = os.path.join(xbmc.translatePath( "special://profile/" ), "addon_data", os.path.basename(os.getcwd()), 'cookie.txt')
handle = int(sys.argv[1])

def setting_defined(setting_id):
    s = xbmcplugin.getSetting(handle, setting_id)
    return s is not None and len(s) > 0

def login():
    g = GOMtv(BASE_COOKIE_PATH)
    if not setting_defined("username") or not setting_defined("password"):
        xbmcgui.Dialog().ok("Missing configuration", "you need to configure a username and password")
        return False
    elif not g.login(xbmcplugin.getSetting(handle, "username"), xbmcplugin.getSetting(handle, "password")) == GOMtv.LOGIN_SUCCESS:
        xbmcgui.Dialog().ok("Login failed", "login failed")
        return False    
    return True

def addLink(name, url, iconimage):
    xbmc.log("adding link: %s -> %s" % (name, url), xbmc.LOGDEBUG)
    name = name.encode("utf-8")
    li = xbmcgui.ListItem(name, iconImage="DefaultVideo.png", thumbnailImage=iconimage)
    li.setInfo( type="Video", infoLabels={ "Title": name } )
    li.setProperty('mimetype', 'video/x-flv')
    return xbmcplugin.addDirectoryItem(handle = handle,
                                       url = url,
                                       listitem = li)

def addDir(name, iconimage, func, **params):
    name = name.encode("utf-8")
    url = "%s?method=%s" % (sys.argv[0], func.__name__)
    if len(params.items()) > 0:
        for (k,v) in params.items():
            url = url + "&%s=%s" % (urllib.quote_plus(k), urllib.quote_plus(str(v)))
    li = xbmcgui.ListItem(name,
                          iconImage="DefaultFolder.png",
                          thumbnailImage=iconimage)
    li.setInfo( type="Video", infoLabels={ "Title": name } )
    return xbmcplugin.addDirectoryItem(handle = handle,
                                       url = url,
                                       listitem = li,
                                       isFolder = True)
def list_main():
    if login():
        addDir("Most recent", "", list_vods, page=1, order=1)
        addDir("Most viewed", "", list_vods, page=1, order=2)
        addDir("Most replied", "", list_vods, page=1, order=3)
        addDir("Live", "", show_live)
        return True
    else:
        return False

def show_live():
    g = GOMtv(BASE_COOKIE_PATH)
    try:
        ls = g.live()
        for (k,v) in ls.items():
            addLink(k, v, "")
        return True
    except NoBroadcastException, nbe:
        xbmcgui.Dialog().ok("No live broadcast", nbe.msg)
    
def list_vods(order, page):
    g = GOMtv(BASE_COOKIE_PATH)
    result = g.get_vod_list(int(order), int(page))
    for vod in result["vods"]:
        addDir(vod["title"], vod["preview"], list_vod_set, url=vod["url"])
    if result["has_previous"]:
        addDir("Previous", "", list_vods, order=order, page=int(page)-1)
    if result["has_next"]:
        addDir("Next", "", list_vods, order=order, page=int(page)+1)
    return True

def list_vod_set(url):
    if xbmcplugin.getSetting(handle, "use_hq") == "true":
        quality = "HQ"
    else:
        quality = "SQ"
    g = GOMtv(BASE_COOKIE_PATH)
    sets = g.get_vod_set(url, quality)
    for s in sets:
        addLink(s["title"], s["url"], "")
    return True

def get_params():
    params = re.findall("\??&?([^=]+)=([^&]+)", sys.argv[2])
    return dict((key, urllib.unquote_plus(value)) for key, value in params)

params = get_params()
if not "method" in params:
    params["method"] = "list_main"

func = locals()[params["method"]]
del params["method"]
try:
    if func.__call__(**params):
        xbmcplugin.endOfDirectory(handle)
except NotLoggedInException:
    if login():
        if func.__call__(**params):
            xbmcplugin.endOfDirectory(handle)
        
    
