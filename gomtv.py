import urllib, urllib2, re, cookielib, socket, os, tempfile
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

    def _get_stream_key(self, server_ip, uno, nodeid, local_ip):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((server_ip, 63800))
        payload = "Login,0,%s,%s,%s\n" % (uno, nodeid, local_ip)
        s.send(payload)
        data = s.recv(1024)
        s.close()
        return data[data.rfind(",")+1:-1]

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
            ret = self._request("http://www.gomtv.net/user/loginProcess.gom", {"mb_username": username,
                                                                               "mb_password": password,
                                                                               "cmd": "login",
                                                                               "rememberme": "1"})
            return int(ret)
        
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

    def get_most_recent_list(self):
        url = "http://www.gomtv.net/videos/index.gom"
        soup = BeautifulSoup(self._request(url))
        thumb_links = soup.findAll("td", {"class": "vod_info"})
        vods = []
        result = {"order": self.VODLIST_ORDER_MOST_RECENT,
                  "page": 1,
                  "vods": vods,
                  "has_previous": False,
                  "has_next": False}
        for thumb_link in thumb_links:
            href = thumb_link.find("a", "vod_link")["href"].replace("/./", "/")
            thumb = thumb_link.find("img", "v_thumb")
            vods.append({"url": "http://www.gomtv.net%s" % href, "preview": thumb["src"], "title": thumb["alt"]})
        return result

    def get_vod_list(self, order=1, page=1, league=None, type=VODLIST_TYPE_ALL):
        if league is None:
            return self.get_most_recent_list()
        url = "http://www.gomtv.net/%s/vod/index.gom?page=%d&order=%d&ltype=%d" % (league, page, order, type)
        soup = BeautifulSoup(self._request(url))
        thumb_links = soup.findAll("td", {"class": "listOff"})
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
            href = thumb_link.find("a", "vodlink")["href"].replace("/./", "/")
            vods.append({"url": "http://www.gomtv.net%s" % href,
                           "preview": thumb_link.find("img", "vodthumb")["src"],
                           "title": thumb_link.find("a", "thumb_link")["title"]})
        return result

    def _get_set_info(self, leagueid, vjoinid, quality, conid):
        vod_key = (leagueid, vjoinid, quality, conid)

        if vod_key not in self.vod_sets:
            url = "http://www.gomtv.net/gox/ggox.gom?&target=vod&leagueid=%s&vjoinid=%s&strLevel=%s&conid=%s" % vod_key
            r = self._request(url)
            if "ErrorMessage" in r:
                return None, None
            
            urls = re.findall("href=\"(.*)\"", r)
            for url in urls:
                url = url.replace("&amp;", "&")
                url_vjoinid = re.search("vjoinid=([0-9]+)",url).group(1)
                url_vod_key = (leagueid, url_vjoinid, quality, conid)
                uno = re.search("uno=([0-9]+)", url).group(1)
                nodeid = re.search("nodeid=([0-9]+)", url).group(1)
                ip = re.search("USERIP>([0-9.]+)", r).group(1)
                remote_ip = re.search("//([0-9.]+)/", url).group(1)

                self.vod_sets[url_vod_key] = (url, (remote_ip, uno, nodeid, ip))
        if self.use_proxy:
          url, (remote_ip, uno, nodeid, ip) = self.vod_sets.pop(vod_key)
          return proxy.url({'payload': "Login,0,%s,%s,%s\n" % (uno, nodeid, ip),'dest': url})
        else:
          url, (remote_ip, uno, nodeid, ip) = self.vod_sets[vod_key]
          key = self._get_stream_key(remote_ip, uno, nodeid, ip)
          return url + "&key=" + key

    def _get_set_params(self, body):
        flashvars = re.search("FlashVars=\"([^\"]+)\"", body).group(1)
        params = [v.split('=',1) for v in flashvars.split("&")]
        params = [(key, urllib.unquote_plus(urllib.unquote(value))) for (key, value) in params]
        return dict(params)
        
    def get_vod_set(self, vod_url, quality="HQ"):
        r = self._request(vod_url + "/?set=%d" % (1))
        soup = BeautifulSoup(r)

        sets = soup.findAll("li", "li_set")
        for (i, s) in enumerate(sets, 1):
            yield {"url": vod_url + "/?set=%d" % i,
                    "title": "%i - Game %s" % (i, s.text)}

    def get_vod_set_url(self, set_url, quality="HQ"):
        r = self._request(set_url)
        params = self._get_set_params(r)
        url = self._get_set_info(params["leagueid"], params["vjoinid"], quality, params["conid"])
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
