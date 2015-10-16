import sys
import time
import ConfigParser
import getpass
import os
import requests

__author__ = 'psaffrey'

"""
Objects to help with creating config files that contain the right details to be used by the BaseSpaceSDK

One way uses the OAuth flow for web application authentication:

https://developer.basespace.illumina.com/docs/content/documentation/authentication/obtaining-access-tokens

to get an access token and put it in the proper place.

Also partly available here is obtaining session tokens (cookies), although these are not currently used.
"""

DEFAULT_SCOPE = "CREATE GLOBAL,BROWSE GLOBAL,CREATE PROJECTS,READ GLOBAL"


class AuthenticationAPI(object):
    DEFAULT_CONFIG_NAME = "DEFAULT"

    def __init__(self, config_path, api_server):
        self.config_path = config_path
        self.api_server = api_server
        self.config = None
        self.parse_config()

    def parse_config(self):
        """
        parses the config_path or creates it if it doesn't exist

        :param config_path: path to config file
        :return: ConfigParser object
        """
        if not os.path.exists(self.config_path):
            self.config = ConfigParser.SafeConfigParser()
        else:
            self.config = ConfigParser.SafeConfigParser()
            self.config.read(self.config_path)

    def construct_default_config(self, api_server):
        self.config.set(self.DEFAULT_CONFIG_NAME, "apiServer", api_server)

    def write_config(self):
        with open(self.config_path, "w") as fh:
            self.config.write(fh)


######
# the BaseSpaceAPI doesn't support using the session tokens (cookies) at the moment
# but this is here in case it's useful to somebody :)
class SessionAuthentication(AuthenticationAPI):
    SESSION_AUTH_URI = "https://accounts.illumina.com/"
    SESSION_TOKEN_NAME = "sessionToken"
    COOKIE_NAME = "IComLogin"

    def basespace_session(self, username, password):
        s = requests.session()
        payload = {"UserName": username,
                   "Password": password,
                   "ReturnUrl": "http://developer.basespace.illumina.com/dashboard"}
        r = s.post(url=self.SESSION_AUTH_URI,
                   params={'Service': 'basespace'},
                   data=payload,
                   headers={'Content-Type': "application/x-www-form-urlencoded"},
                   allow_redirects=False)
        return s, r

    def check_session_details(self):
        pass

    def set_session_details(self, config_path):
        username = raw_input("username:")
        password = getpass.getpass()
        s, r = self.basespace_session(username, password)
        self.config.set(self.DEFAULT_CONFIG_NAME, self.SESSION_TOKEN_NAME, r.cookies[self.COOKIE_NAME])
        self.write_config()

class OAuthAuthentication(AuthenticationAPI):
    WAIT_TIME = 5.0
    ACCESS_TOKEN_NAME = "accessToken"

    def __init__(self, config_path, api_server, api_version):
        super(OAuthAuthentication, self).__init__(config_path, api_server)
        self.api_version = api_version

    def set_oauth_details(self, client_id, client_secret, scope=DEFAULT_SCOPE):
        OAUTH_URI = "%s%s/oauthv2/deviceauthorization" % (self.api_server, self.api_version)
        TOKEN_URI = "%s%s/oauthv2/token" % (self.api_server, self.api_version)
        s = requests.session()
        # make the initial request
        auth_payload = {
            "response_type": "device_code",
            "client_id": client_id,
            "scope": scope,
        }
        try:
            r = s.post(url=OAUTH_URI,
                       data=auth_payload)
        except Exception as e:
            print "problem communicate with oauth server: %s" % str(e)
            raise
        # show the URL to the user
        auth_url = r.json()["verification_with_code_uri"]
        auth_code = r.json()["device_code"]
        print "please authenticate here: %s" % auth_url
        # poll the token URL until we get the token
        token_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": auth_code,
            "grant_type": "device"
        }
        access_token = None
        while 1:
            # put the token into the config file
            r = s.post(url=TOKEN_URI,
                       data=token_payload)
            if r.status_code == 400:
                sys.stdout.write(".")
                sys.stdout.flush()
                time.sleep(self.WAIT_TIME)
            else:
                sys.stdout.write("\n")
                access_token = r.json()["access_token"]
                break
        self.construct_default_config(self.api_server)
        if not access_token:
            raise Exception("problem obtaining token!")
        print "Success!"
        self.config.set(self.DEFAULT_CONFIG_NAME, self.ACCESS_TOKEN_NAME, access_token)
        self.write_config()