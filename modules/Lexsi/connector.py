import logging
import requests
import json
import time
from datetime import datetime, timezone
from dateutil import tz
import urllib

class LexsiConnector:
    'LexsiConnector connector'

    def __init__(self, cfg):
        """
            Class constuctor

            :param cfg: synapse configuration
            :type cfg: ConfigParser

            :return: Object LexsiConnector
            :rtype: LexsiConnector
        """

        self.logger = logging.getLogger(__name__)
        self.cfg = cfg
        self.url = self.cfg.get('Lexsi', 'url')
        self.user = self.cfg.get('Lexsi', 'user')
        self.passw = self.cfg.get('Lexsi', 'password')
        self.http_proxy = self.cfg.get('Lexsi', 'http_proxy')
        self.https_proxy = self.cfg.get('Lexsi', 'http_proxy')

        self.proxies = {
            'http': self.http_proxy,
            'https': self.https_proxy,
        }

        self.__cookiejar = self.__authenticate()

    def __authenticate(self):
        self.logger.debug("Authenticating Lexsi...")

        try:
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Accept': '*/*'
            }

            data = {
                'userName': self.user,
                'password': self.passw
            }

            r = requests.post(self.url + "/api/auth/auth/login/",
                              headers=headers,
                              data=data,
                              proxies=self.proxies,
                              verify=False)
            r.raise_for_status()
            self.logger.debug("Return value {}".format(r.text))
            if "failure" in r.json().keys():
                raise requests.RequestException
        except requests.RequestException as e:
            self.logger.error("Failed authentication to Lexsi with error {}".format(e))
            raise
            self.logger.debug("Successfully authenticated to Lexsi")
        return r.cookies

    def getOpenItems(self, maxResults=200):
        self.logger.info("Started receiving open alerts from Lexsi")

        try:
            data = {
                'filter': self.cfg.get('Lexsi', 'filter'),
                'limit': maxResults
            }

            r = requests.get(self.url + "/api/cyb/alerts/listcybercrimefilter/?" + urllib.parse.urlencode(data),
                             cookies=self.__cookiejar,
                             proxies=self.proxies,
                             verify=False)
            r.raise_for_status()
        except requests.RequestException as e:
            self.logger.error("Failed alert retrieval with error {}".format(e))
            raise

        self.logger.info("Performed alert retrieval with status code {}".format(r.status_code))
        return r.json()

    def createMappingOnFieldName(self, fieldName, issueList):
        fieldId = self.getCustomFieldId(fieldName)
        mapped_values = dict()
        for issue in issueList['issues']:
            mapped_values[issue['key']] = issue['fields'][fieldId]
        return mapped_values
