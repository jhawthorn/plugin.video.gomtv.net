#!/usr/bin/env python
from gomtv import GOMtv, NoBroadcastException, NotLoggedInException
from tempfile import NamedTemporaryFile
import os
import sys
from pprint import PrettyPrinter

if __name__  == "__main__":
    try:
        username = os.environ['GOMTV_USERNAME']
        password = os.environ['GOMTV_PASSWORD']
    except KeyError:
        print("Errror: GOMTV_USERNAME or GOMTV_PASSWORD not set in environment")
        sys.exit(1)
    pp = PrettyPrinter()
    cookie_file = NamedTemporaryFile()
    gom = GOMtv(cookie_file.name)
    login = gom.login(username, password, GOMtv.AUTH_GOMTV)
    if not login  == GOMtv.LOGIN_SUCCESS:
        print("Errror: Login failed: %d" % login)
        sys.exit(1)
    result = gom.get_league_list()
    print "LEAGUES"
    pp.pprint(result)
    result = gom.get_vod_list(1, GOMtv.VODLIST_ORDER_MOST_RECENT, "2012gsls2")
    print "2012 GSLS2"
    pp.pprint(result)
    result = gom.get_vod_list(1, GOMtv.VODLIST_ORDER_MOST_RECENT, None)
    print "MOST RECENT"
    pp.pprint(result)
    for i in range(len(result["vods"])):
        result2 = gom.get_vod_set(result["vods"][i]["url"], "HQ", True)
        print "MOST RECENT VOD %d SETS" % i
        for s in result2:
            pp.pprint(s)
    print "LIVE HQ"
    try:
        print gom.live("HQ")
    except NoBroadcastException, nbe:
        print nbe.msg
    print "LIVE SQ"
    try:
        print gom.live("SQ")
    except NoBroadcastException, nbe:
        print nbe.msg

    
