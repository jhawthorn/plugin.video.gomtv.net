import urllib, re, xbmcplugin, xbmcgui, os, xbmc, xbmcaddon
from gomtv import GOMtv, NotLoggedInException

BASE_COOKIE_PATH = os.path.join(xbmc.translatePath( "special://profile/" ), "addon_data", "plugin.video.gomtv.net", 'cookie.txt')
handle = int(sys.argv[1])
addon = xbmcaddon.Addon(id="plugin.video.gomtv.net")

def get_setting(setting_id):
    return xbmcplugin.getSetting(handle, setting_id)

def gomtv():
  use_proxy = (get_setting("seek_workaround") == "true")
  return GOMtv(BASE_COOKIE_PATH,use_proxy=use_proxy)

def login():
    g = gomtv()
    AUTH_TYPES = { "Twitter": GOMtv.AUTH_TWITTER, "Facebook": GOMtv.AUTH_FACEBOOK }
    auth_type = AUTH_TYPES.get(get_setting("account_type"), GOMtv.AUTH_GOMTV)
    username, password = get_setting("username"), get_setting("password")
    if not username or not password:
        addon.openSettings()
        return False
    elif not g.login(username, password, auth_type):
        xbmcgui.Dialog().ok("Login failed", "login failed")
        return False
    else:
        return True

def genCallback(func,**params):
    url = "%s?method=%s" % (sys.argv[0], func.__name__)
    for (k,v) in params.items():
        if v is not None:
            url = url + "&%s=%s" % (urllib.quote_plus(k), urllib.quote_plus(str(v)))
    return url

def build_listItem(name):
    li = xbmcgui.ListItem(name)
    li.setInfo( type="Video", infoLabels={ "Title": name } )
    li.setProperty('IsPlayable', 'true');
    return li

def playVod(**params):
    g = gomtv()
    url = g.get_vod_set_url(params, get_quality())
    li = xbmcgui.ListItem(path=url)
    li.setProperty('mimetype', 'video/mp4')
    xbmcplugin.setResolvedUrl(handle=handle, succeeded=True, listitem=li)

def addLink(name, url, iconimage):
    xbmc.log("adding link: %s -> %s" % (name, url), xbmc.LOGDEBUG)
    name = name.encode("utf-8")
    li = build_listItem(name)
    return xbmcplugin.addDirectoryItem(handle = handle,
                                       url = url,
                                       listitem = li)

def addDir(name, iconimage, func, **params):
    name = name.encode("utf-8")
    url = genCallback(func, **params)
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
            addDir("Leagues", "", list_leagues)
        return True
    else:
        return False

def get_quality():
    return get_setting("quality")

def list_leagues():
    g = gomtv()
    leagues = g.get_league_list()
    for league in leagues:
        addDir(league["name"], league["logo"], list_main, league=league["id"])
    return True

def list_vods(order, page, league=None):
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
    g = gomtv()
    for s in g.get_vod_set(url):
        url = genCallback(playVod, **s["params"])
        addLink(s["title"], url, "")
    return True

def get_params():
    params = re.findall("\??&?([^=]+)=([^&]+)", sys.argv[2])
    return dict((key, urllib.unquote_plus(value)) for key, value in params)

params = get_params()
func = locals()[params.pop("method", "list_main")]
try:
    if func.__call__(**params):
        xbmcplugin.endOfDirectory(handle)
except NotLoggedInException:
    if login():
        if func.__call__(**params):
            xbmcplugin.endOfDirectory(handle)

