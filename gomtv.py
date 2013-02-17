import urllib, urllib2, re, cookielib, socket, os, tempfile, json, md5
from BeautifulSoup import BeautifulSoup
import proxy

class NotLoggedInException(Exception):
    pass

class NoBroadcastException(Exception):
    def msg(self):
        self.args[0]

class GOMtv(object):
    VODLIST_ORDER_MOST_RECENT = 1
    VODLIST_ORDER_MOST_VIEWED = 2
    VODLIST_ORDER_MOST_COMMENTED = 3

    LOGIN_SUCCESS = 1
    LOGIN_BAD_USERNAME_OR_PASSWORD = 2
    LOGIN_BAD_EMAIL = 3
    LOGIN_BAD_PASSWORD = 4
    LOGIN_SNS_ACCOUNT = 5

    VODLIST_TYPE_ALL = 0
    VODLIST_TYPE_CODE_S = 32
    VODLIST_TYPE_CODE_A = 16
    VODLIST_TYPE_UP_DOWN = 64

    AUTH_GOMTV = 1
    AUTH_TWITTER = 2
    AUTH_FACEBOOK = 3

    LEVELS = {
            'EHQ': [65, 60, 6, 5],
            'HQ': [60, 6, 5],
            'SQ': [6, 5]
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

        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cookie_jar))
        urllib2.install_opener(opener)

    def _request(self, url, data=None, headers={}):
        # Ugly hack required to fix cookie names.
        # Guessing there's some javascript somewhere on that mess of a website
        # that uppercases the cookies..?
        for cookie in self.cookie_jar:
            if cookie.name.startswith("SES_"):
                cookie.name = cookie.name.upper()

        if data is not None:
            data = urllib.urlencode(data)
        req = urllib2.Request(url, data, headers)
        response = urllib2.urlopen(req)
        ret = response.read()
        response.close()
        self.cookie_jar.save(None,True)
        #print "url: %s" % url
        #print "response:\n%s" % ret
        return ret

    def _get_stream_key(self, server_ip, params):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((server_ip, 63800))
        payload = "Login,0,%s,%s,%s\n" % (params['uno'], server_ip, params['uip'])
        s.send(payload)
        data = s.recv(1024)
        s.close()
        return data[data.rfind(",")+1:-1]

    def _get_ip(self):
        return self._request('http://www.gomtv.net/webPlayer/getIP.gom')

    def set_cookie(self, name, value):
        exp = time() + 24 * 60 * 60
        cookie = cookielib.Cookie(version=0, name=name, value=value, port=None, port_specified=False,
                                  domain='.gomtv.net', domain_specified=True, domain_initial_dot=True,
                                  path='/', path_specified=True, secure=False, expires=exp,
                                  discard=False, comment=None, comment_url=None, rest={})
        self.cookie_jar.set_cookie(cookie)


    def login(self, username, password, auth_type=AUTH_GOMTV):
        self.cookie_jar.clear_session_cookies()
        if auth_type == self.AUTH_GOMTV:
            form = {
                    "mb_username": username,
                    "mb_password": password,
                    "cmd": "login",
                    "rememberme": "1"
                    }
            ret = self._request("http://www.gomtv.net/user/loginProcess.gom", form, {'Referer': 'http://www.gomtv.net/'})
            # FIXME
            return self.LOGIN_SUCCESS
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
                return self.LOGIN_BAD_USERNAME_OR_PASSWORD
            else:
                location = refresh.group(1)
                data = self._request(location)
                return self.LOGIN_SUCCESS

        elif auth_type == self.AUTH_FACEBOOK:
            data = self._request("http://www.gomtv.net/facebook/index.gom?burl=/index.gom")
            soup = BeautifulSoup(data)
            # already logged in
            if data.startswith("<script>"):
                return self.LOGIN_SUCCESS

            url = soup.find("form")["action"]
            payload = {}
            for field in soup.findAll("input"):
                if not field["name"] == "charset_test":
                    payload[field["name"]] = field["value"]
            payload["email"] = username
            payload["pass"] = password

            data = self._request(url, payload)
            if re.search("<title>Logga in", data) is None:
                return self.LOGIN_SUCCESS
            else:
                return self.LOGIN_BAD_USERNAME_OR_PASSWORD

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
            url = "http://www.gomtv.net/%s/vod/index.gom?page=%d&order=%d&ltype=%d" % (league, page, order, type)
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

    def get_vod_set(self, vod_url, quality="HQ"):
        r = self._request(vod_url)

        flashvars = self._get_set_params(r)
        # 0 english, 1 korean
        jsondata = self.extract_jsonData(r)[0]
        soup = BeautifulSoup(r)
        vodlist = soup.find('ul', id='vodList')

        sets = vodlist.findAll("a")
        for (i, s) in enumerate(sets):
            params = dict(flashvars, **jsondata[i])
            yield {"params": params,
                    "title": "%i - %s" % (i+1, s['title'])}

    def _key_or_proxy(self, url, params):
        remote_ip = re.search("//([0-9.]+)/", url).group(1)
        if self.use_proxy:
            return proxy.url({'payload': "Login,0,%s,%s,%s\n" % (params['uno'], remote_ip, params['uip']), 'dest': url})
        else:
            stream_key = self._get_stream_key(remote_ip, params)
            return url + "&key=" + stream_key

    def _gox_params(self, params):
        params["goxkey"] = "qoaEl"
        keys = ["leagueid", "conid", "goxkey", "level", "uno", "uip", "adstate", "vjoinid", "nid"]
        hashstr = "".join([params[key] for key in keys])
        params['goxkey'] = md5.new(hashstr).hexdigest()
        return params

    def _get_url(self, params):
        params = self._gox_params(params)
        r = self._request('http://gox.gomtv.net/cgi-bin/gox_vod_sfile.cgi', params)
        match = re.search('<REF\s+href="(.+)"\s+reftype="vod"', r)
        if match:
            url = match.group(1).replace('&amp;', '&').replace(' ', '%20')
            return self._key_or_proxy(url, params)

    def get_vod_set_url(self, params, quality="EHQ"):
        params["uip"] = self._get_ip()
        params["adstate"] = "0"
        for level in self.LEVELS[quality]:
            params['level'] = str(level)
            url = self._get_url(params)
            if url:
                return url

    def seconds2time(self, seconds):
        days, rest = divmod(seconds, 86400)
        hours, rest = divmod(rest, 3600)
        minutes, rest = divmod(rest, 60)
        def format_unit(val, name):
            if val == 0:
                return ""
            elif val == 1:
                return "%d %s, " % (val, name)
            else:
                return "%d %ss, " % (val, name)
        return "%s%s%s%s" % (format_unit(days, 'day'),
                             format_unit(hours, 'hour'),
                             format_unit(minutes, 'minute'),
                             ("%d seconds" % rest))


    def live(self, quality):
        data = self._request("http://www.gomtv.net/main/goLive.gom")
        soup = BeautifulSoup(data)
        left = int(re.search("var leftTime\s*=\s*'?(-?[0-9]+)'?", data).group(1));
        if left > 0:
            raise NoBroadcastException(("Next broadcast starts in: %s" % self.seconds2time(left)))


        choices = []
        for choice in soup.findAll("dl", "lcy_choiceset"):
            choices.append({"desc": " ".join(choice.findAll("p", text=True)).replace("\n", "").strip(),
                            "link": choice.find("a")["href"]})

        result = {}
        if len(choices) == 0:
            gox = re.search('[^/]var goxUrl[^=]*=[^"]*"(.*);', data).group(1)
            gox = gox.replace('" + playType + "', quality)
            gox = gox.replace('"+ tmpThis.title +"&"', "title")
            data = self._request(gox)
            if data == "1001":
                raise NotLoggedInException()
            url = re.search('href="(.*)"', data).group(1)
            if url.startswith("http"):
                u = url.replace("&amp;", "&")
                result["FIXME"] = u
        for choice in choices:
            data = self._request("http://www.gomtv.net%s" % choice["link"])
            soup = BeautifulSoup(data)
            gox = re.search('[^/]var goxUrl[^=]*=[^"]*"(.*);', data).group(1)
            gox = gox.replace('" + playType + "', quality)
            gox = gox.replace('"+ tmpThis.title +"&"', "title")
            data = self._request(gox)
            if data == "1001":
                raise NotLoggedInException()
            url = re.search('href="(.*)"', data).group(1)
            if url.startswith("http"):
                u = url.replace("&amp;", "&")
                result[choice["desc"]] = u
        return result
