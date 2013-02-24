import urllib, urllib2, re, cookielib, os, tempfile, json, md5, time
from BeautifulSoup import BeautifulSoup
import proxy
from gomutil import *

class NotLoggedInException(Exception):
    pass

def request(url, params=None, headers={}, opener=None):
    data = params and urllib.urlencode(params)
    req = urllib2.Request(url, data, headers)
    if opener:
        response = opener.open(req)
    else:
        response = urllib2.urlopen(req)
    r = response.read()
    response.close()
    return r

class VodSet(object):
    def __init__(self, params):
        self.params = params
        self._fix_params()

        self.xml = request('http://gox.gomtv.net/cgi-bin/gox_vod_sfile.cgi', self.params)

    def _fix_params(self):
        if 'uip' not in self.params:
            self.params["uip"] = request('http://www.gomtv.net/webPlayer/getIP.gom')
        self.params["adstate"] = "0"
        self.params["goxkey"] = "qoaEl"
        keys = ["leagueid", "conid", "goxkey", "level", "uno", "uip", "adstate", "vjoinid", "nid"]
        hashstr = "".join([self.params[key] for key in keys])
        self.params['goxkey'] = md5.new(hashstr).hexdigest()

    def _get_href(self):
        match = re.search('<REF\s+href="(.+)"\s+reftype="vod"', self.xml)
        if match:
            href = match.group(1).replace('&amp;', '&').replace(' ', '%20')
            remote_ip = re.search("//([0-9.]+)/", href).group(1)
            payload = gom_key_payload(remote_ip, self.params)
            return (href, remote_ip, payload)
        else:
            return (None, None, None)

    def get_url(self):
        href, remote_ip, payload = self._get_href()
        return href and "%s&key=%s" % (href, gom_stream_key(remote_ip, payload))

    def get_proxy_url(self):
        href, remote_ip, payload = self._get_href()
        return proxy.url(href, payload)

class GOMtv(object):
    VODLIST_ORDER_MOST_RECENT = 1
    VODLIST_ORDER_MOST_VIEWED = 2
    VODLIST_ORDER_MOST_COMMENTED = 3

    VODLIST_TYPE_ALL = 0
    VODLIST_TYPE_CODE_S = 32
    VODLIST_TYPE_CODE_A = 16
    VODLIST_TYPE_UP_DOWN = 64

    AUTH_GOMTV = 1
    AUTH_TWITTER = 2
    AUTH_FACEBOOK = 3

    LEVEL = {
            'EHQ': 65,
            'HQ': 60,
            'SQ': 6
            }
    OLDLEVEL = {
            'EHQ': 50,
            'HQ': 50,
            'SQ': 5
            }

    def __init__(self, cookie_path=None, use_proxy=False):
        self.use_proxy = use_proxy
        self.vod_sets = {}
        if cookie_path is None:
            cookie_path = "%s%scookies_gomtv.txt" % (tempfile.gettempdir(), os.path.sep)
        self.cookie_jar = cookielib.LWPCookieJar(cookie_path)
        if not os.path.exists(os.path.dirname(cookie_path)):
            os.makedirs(os.path.dirname(cookie_path))
        if (os.path.isfile(cookie_path) and os.path.getsize(cookie_path) > 0):
            self.cookie_jar.load(cookie_path,True)

        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cookie_jar))

    def _request(self, url, data=None, headers={}):
        # Ugly hack required to fix cookie names.
        # Guessing there's some javascript somewhere on that mess of a website
        # that uppercases the cookies..?
        for cookie in self.cookie_jar:
            if cookie.name.startswith("SES_"):
                cookie.name = cookie.name.upper()

        r = request(url, data, headers, opener=self.opener)
        self.cookie_jar.save(None,True)
        return r

    def set_cookie(self, name, value):
        exp = time.time() + 24 * 60 * 60
        cookie = cookielib.Cookie(version=0, name=name, value=value, port=None, port_specified=False,
                                  domain='.gomtv.net', domain_specified=True, domain_initial_dot=True,
                                  path='/', path_specified=True, secure=False, expires=exp,
                                  discard=False, comment=None, comment_url=None, rest={})
        self.cookie_jar.set_cookie(cookie)


    def login(self, username, password, auth_type=AUTH_GOMTV):
        self.cookie_jar.clear()
        if auth_type == self.AUTH_GOMTV:
            form = {
                    "mb_username": username,
                    "mb_password": password,
                    "cmd": "login",
                    "rememberme": "1"
                    }
            ret = self._request("http://www.gomtv.net/user/loginProcess.gom", form, {'Referer': 'http://www.gomtv.net/'})
            cookies = [cookie.name for cookie in self.cookie_jar if cookie.domain == '.gomtv.net']
            return 'SES_userno' in cookies
        elif auth_type == self.AUTH_TWITTER:
            data = self._request("http://www.gomtv.net/twitter/redirect.gom?burl=/index.gom")
            location = re.search("document.location.replace\(\"(.*)\"\)", data).group(1)
            oauth_token = re.search("setCookie\('oauth_token', \"(.*)\"", data).group(1)
            oauth_token_secret = re.search("setCookie\('oauth_token_secret', \"(.*)\"", data).group(1)
            self.set_cookie("oauth_token", oauth_token)
            self.set_cookie("oauth_token_secret", oauth_token_secret)

            data = self._request(location)
            soup = BeautifulSoup(data)
            oauth_token = soup.find("input", {"id": "oauth_token"})["value"]
            auth_token = soup.find("input", {"name": "authenticity_token"})["value"]
            url = soup.find("form")["action"]
            data = self._request(url, {"oauth_token": oauth_token,
                                        "session[username_or_email]": username,
                                        "session[password]": password,
                                        "submit": "Sign in",
                                        "authenticity_token": auth_token})

            refresh = re.search('<meta http-equiv="refresh" content="0;url=(.*)">', data)
            if refresh is None:
                return False
            else:
                location = refresh.group(1)
                data = self._request(location)
                return True

        elif auth_type == self.AUTH_FACEBOOK:
            data = self._request("http://www.gomtv.net/facebook/index.gom?burl=/index.gom")
            soup = BeautifulSoup(data)
            # already logged in
            if data.startswith("<script>"):
                return False

            url = soup.find("form")["action"]
            payload = {}
            for field in soup.findAll("input"):
                if not field["name"] == "charset_test":
                    payload[field["name"]] = field["value"]
            payload["email"] = username
            payload["pass"] = password

            data = self._request(url, payload)
            if re.search("<title>Logga in", data) is None:
                return True
            else:
                return False

    def get_league_list(self):
        soup = BeautifulSoup(self._request("http://www.gomtv.net/view/channelDetails.gom?gameid=0"))
        leagues = soup.findAll("dl", "league_list")
        result = []
        for league in leagues:
            result.append({"id": league.find("a")["href"].replace("/", ""),
                           "logo": league.find("img")["src"],
                           "name": league.find("strong").find(text=True)})
        return result

    def get_most_recent_list(self, page=1):
        return self.get_vod_list(league=None, page=page)

    def get_vod_list(self, order=1, page=1, league=None, type=VODLIST_TYPE_ALL):
        if league is None:
            url = "http://www.gomtv.net/videos/index.gom?page=%d" % (page)
        else:
            url = "http://www.gomtv.net/%s/vod/?page=%d&order=%d&ltype=%d" % (league, page, order, type)
        soup = BeautifulSoup(self._request(url))
        thumb_links = soup.findAll("td", {"class": ["vod_info", "listOff"]})
        nums = soup.findAll("a", "num", href=re.compile("page=[0-9]+"))
        if len(nums) > 0:
            last = int(re.search("page=([0-9]+)",
                                 nums[-1]["href"]).group(1))
        else:
            last = page
        vods = []
        result = {"order": order,
                  "page": page,
                  "vods": vods,
                  "has_previous": page is not 1,
                  "has_next": page is not last}
        if page > last or page < 1:
            return result
        for thumb_link in thumb_links:
            href = thumb_link.find("a", {'class': ["vod_link", "vodlink"]})["href"].replace("/./", "/")
            thumb = thumb_link.find("img", {'class': ["v_thumb", "vodthumb"]})
            vods.append({"url": "http://www.gomtv.net%s" % href, "preview": thumb["src"], "title": thumb["alt"]})
        return result

    def _get_set_params(self, body):
        flashvars = re.search('flashvars\s+=\s+([^;]+);', body).group(1)
        return json.loads(flashvars)

    def extract_jsonData(self, body):
        jsondata = re.search('var\s+jsonData\s+=\s+eval\s+\(([^)]*)\)', body).group(1)
        return json.loads(jsondata)

    def get_vod_set(self, vod_url, quality="EHQ"):
        self.set_cookie('SES_VODLEVEL',    str(self.LEVEL[quality]))
        self.set_cookie('SES_VODOLDLEVEL', str(self.OLDLEVEL[quality]))

        r = self._request(vod_url)

        flashvars = self._get_set_params(r)
        if flashvars['uno'] == '0':
            raise NotLoggedInException
        # 0 english, 1 korean
        jsondata = self.extract_jsonData(r)[0]
        soup = BeautifulSoup(r)
        vodlist = soup.find('ul', id='vodList')

        sets = vodlist.findAll("a")
        for (i, s) in enumerate(sets):
            params = dict(flashvars, **jsondata[i])
            yield {"params": params,
                    "title": "%i - %s" % (i+1, s['title'])}


    def get_vod_set_url(self, params):
        vod_set = VodSet(params)
        if self.use_proxy:
            return vod_set.get_proxy_url()
        else:
            return vod_set.get_url()

