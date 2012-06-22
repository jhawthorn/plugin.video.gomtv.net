import urllib, urllib2, re, xbmcplugin, xbmcgui, os, xbmc, xbmcaddon, cookielib, socket
from BeautifulSoup import BeautifulSoup
from gomtv import GOMtv, NoBroadcastException, NotLoggedInException

BASE_COOKIE_PATH = os.path.join(xbmc.translatePath( "special://profile/" ), "addon_data", "plugin.video.gomtv.net", 'cookie.txt')
handle = int(sys.argv[1])
addon = xbmcaddon.Addon(id="plugin.video.gomtv.net")

def gomtv():
  use_proxy = (addon.getSetting("seek_workaround") == "true")
  return GOMtv(BASE_COOKIE_PATH,use_proxy=use_proxy)

def setting_defined(setting_id):
    s = xbmcplugin.getSetting(handle, setting_id)
    return s is not None and len(s) > 0

def login():
    g = gomtv()
    auth_type = GOMtv.AUTH_GOMTV
    if xbmcplugin.getSetting(handle, "account_type") == "Twitter":
        auth_type = GOMtv.AUTH_TWITTER
    elif xbmcplugin.getSetting(handle, "account_type") == "Facebook":
        auth_type = GOMtv.AUTH_FACEBOOK
    if not setting_defined("username") or not setting_defined("password"):
        xbmcgui.Dialog().ok("Missing configuration", "you need to configure a username and password")
        return False
    elif not g.login(xbmcplugin.getSetting(handle, "username"), xbmcplugin.getSetting(handle, "password"), auth_type) == GOMtv.LOGIN_SUCCESS:
        xbmcgui.Dialog().ok("Login failed", "login failed")
        return False    
    return True

def genCallback(func,**params):
    url = "%s?method=%s" % (sys.argv[0], func.__name__)
    if len(params.items()) > 0:
        for (k,v) in params.items():
            url = url + "&%s=%s" % (urllib.quote_plus(k), urllib.quote_plus(str(v)))
    return url

def playVod(name,url,quality,retrieve_metadata):
    g = gomtv()
    url = g.get_vod_set_url(url, quality, retrieve_metadata)
    li = xbmcgui.ListItem(name)
    li.setInfo( type="Video", infoLabels={ "Title": name } )
    li.setProperty('mimetype', 'video/x-flv')
    xbmc.Player( xbmc.PLAYER_CORE_MPLAYER ).play(url, li, False)

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
def list_main(league=None):
    if login():
        addDir("Most recent", "", list_vods, page=1, order=GOMtv.VODLIST_ORDER_MOST_RECENT, league=league)
        # Kind of ugly 1!
        if league is not None:
            addDir("Most viewed", "", list_vods, page=1, order=GOMtv.VODLIST_ORDER_MOST_VIEWED, league=league)
            addDir("Most commented", "", list_vods, page=1, order=GOMtv.VODLIST_ORDER_MOST_COMMENTED, league=league)
        # Kind of ugly 2!
        if league == None:
            addDir("Live", "", show_live)
            addDir("Leagues", "", list_leagues)
        return True
    else:
        return False

def show_live():
    if xbmcplugin.getSetting(handle, "use_hq") == "true":
        quality = "HQ"
    else:
        quality = "SQ"
    g = gomtv()    
    try:
        ls = g.live(quality)
        for (k,v) in ls.items():
            addLink(k, v, "")
        return True
    except NoBroadcastException, nbe:
        xbmcgui.Dialog().ok("No live broadcast", nbe.msg)

def list_leagues():
    g = gomtv()
    leagues = g.get_league_list()
    for league in leagues:
        addDir(league["name"], league["logo"], list_main, league=league["id"])
    return True
    
def list_vods(order, page, league):
    # ugh.. xbmc?!
    if league == "None":
        league = None
    g = gomtv()
    result = g.get_vod_list(int(order), int(page), league)
    for vod in result["vods"]:
        addDir(vod["title"], vod["preview"], list_vod_set, url=vod["url"])
    if result["has_previous"]:
        addDir("Previous", "", list_vods, order=order, page=int(page)-1, league=league)
    if result["has_next"]:
        addDir("Next", "", list_vods, order=order, page=int(page)+1, league=league)
    return True

def list_vod_set(url):
    if xbmcplugin.getSetting(handle, "use_hq") == "true":
        quality = "HQ"
    else:
        quality = "SQ"
    g = gomtv()
    retrieve_metadata = xbmcplugin.getSetting(handle, "show_races") == "true"
    for s in g.get_vod_set(url):
        url = genCallback(playVod,name=s["title"],url=s["url"],
                          quality=quality,
                          retrieve_metadata = retrieve_metadata)
        addLink(s["title"], url, "")
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
        
    
