import urllib, urllib2, re, cookielib, socket, os, tempfile
from BeautifulSoup import BeautifulSoup

class NotLoggedInException(Exception):
    pass

class NoBroadcastException(Exception):
    def __init__(self, msg):
        self.msg = msg

class GOMtv(object):
    VODLIST_ORDER_MOST_RECENT = 1
    VODLIST_ORDER_MOST_VIEWED = 2
    VODLIST_ORDER_MOST_COMMENTED = 3

    LOGIN_SUCCESS = 1
    LOGIN_BAD_EMAIL = 3
    LOGIN_BAD_PASSWORD = 4
    LOGIN_SNS_ACCOUNT = 5
    
    def __init__(self, cookie_path=None):
        if cookie_path is None:
            cookie_path = "%s%scookies_gomtv.txt" % (tempfile.gettempdir(), os.path.sep)
        self.cookie_jar = cookielib.LWPCookieJar(cookie_path)
        if not os.path.exists(os.path.dirname(cookie_path)):
            os.makedirs(os.path.dirname(cookie_path))
        if (os.path.isfile(cookie_path)):
            self.cookie_jar.load(cookie_path)

    def _request(self, url, data=None):
        urllib2.install_opener(urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cookie_jar)))
        
        if data is not None:
            data = urllib.urlencode(data)
            req = urllib2.Request(url, data)
        else:
            req = urllib2.Request(url)
        response = urllib2.urlopen(req)
        ret = response.read()
        response.close()
        self.cookie_jar.save()
        return ret

    def _get_stream_key(self, server_ip, uno, nodeid, local_ip):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((server_ip, 63800))
        payload = "Login,0,%s,%s,%s\n" % (uno, nodeid, local_ip)
        s.send(payload)
        data = s.recv(1024)
        s.close()
        return data[data.rfind(",")+1:-1]
    
    def login(self, username, password):
        ret = self._request("http://www.gomtv.net/user/loginProcess.gom", {"mb_username": username,
                                                                           "mb_password": password,
                                                                           "cmd": "login",
                                                                           "rememberme": "1"})
        return int(ret)

    def get_vod_list(self, order=1, page=1):
        url = "http://www.gomtv.net/videos/index.gom?page=%d&order=%d" % (page, order)
        soup = BeautifulSoup(self._request(url))
        thumb_links = soup.findAll("td", {"class": "listOff"})
        last = int(re.search("page=([0-9]+)", soup.find("a", text="Last >>").parent["href"]).group(1))
        vods = []
        result = {"order": order,
                  "page": page,
                  "vods": vods,
                  "has_previous": page is not 1,
                  "has_next": page is not last}
        if page > last or page < 1:
            return result
        for thumb_link in thumb_links:
            href = thumb_link.find("a", "thumb_link")["href"].replace("/./", "/")
            vods.append({"url": "http://www.gomtv.net%s" % href,
                           "preview": thumb_link.find("img", "vodthumb")["src"],
                           "title": thumb_link.find("a", "thumb_link")["title"]})
        return result
    
    def get_vod_set(self, vod_url, quality="HQ"):
        r = self._request(vod_url)
        leagueid = re.search('"leagueid"\s*:\s*"(.*)",', r).group(1)
        soup = BeautifulSoup(r)
        matchset_div = soup.find("div", "matchset_set")
        if matchset_div is None:
            raise NotLoggedInException()
        match_sets = matchset_div.findAll("a")
        i = 1
        result = []
        for match_set in match_sets:
            vjoinid = match_set["onclick"]
            vjoinid = vjoinid[vjoinid.find("vjoinid':")+len("vjoinid':"):-1]
            vjoinid = vjoinid[0:vjoinid.find("}")]
            url = "http://www.gomtv.net/gox/gox.gom?&target=vod&leagueid=%s&vjoinid=%s&strLevel=%s&" % (leagueid, vjoinid, quality)
            r = self._request(url)
            if "ErrorMessage" in r:
                return result

            url = re.search("href='(.*)'", r).group(1)
            url = url.replace("&amp;", "&")
        
            uno = re.search("uno=([0-9]+)", url).group(1)
            nodeid = re.search("nodeid=([0-9]+)", url).group(1)
            ip = re.search("ip=([0-9.]+)", url).group(1)
            remote_ip = re.search("//([0-9.]+)/", url).group(1)
            key = self._get_stream_key(remote_ip, uno, nodeid, ip)
            
            url = url + "&key=" + key
        
            name = "Set %d" % i
            i = i + 1
            result.append({"url": url,
                           "title": name})
        return result
            
        
    def live(self):
        soup = BeautifulSoup(self._request("http://www.gomtv.net"))
        live_link = soup.find("a", "golive_on")
        if live_link is None:
            raise NoBroadcastException("".join(soup.find("span", "tooltip").findAll(text=True)))
        else:
            data = self._request("http://www.gomtv.net%s" % live_link["href"])
            gox = re.search('var goxUrl[^=]*=[^"]*"(.*);', data).group(1)
            gox = gox.replace('" + playType + "', "SQ")
            gox = gox.replace('"+tmpThis.title', "title")
            data = self._request(gox)
            if data == "1001":
                raise NotLoggedInException()
            url = re.search('href="(.*)"', data).group(1)
            if url.startswith("http"):
                sq = url.replace("&amp;", "&")
                data = self._request(gox.replace("SQ", "HQ"))
                hq = re.search('href="(.*)"', data).group(1).replace("&amp;", "&")
                return {"sq": sq,
                        "hq": hq}
            else:
                url = re.search("LiveAddr=(.*)", url).group(1)
                url = url[0:url.find("&amp;")]
                return {"sq": urllib2.unquote(url)}
                
    
