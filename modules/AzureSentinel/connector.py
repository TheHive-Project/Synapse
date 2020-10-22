import logging
import requests
import json

class AzureSentinelConnector:
    'AzureSentinelConnector connector'

    def __init__(self, cfg):
        """
            Class constuctor

            :param cfg: synapse configuration
            :type cfg: ConfigParser

            :return: Object AzureSentinelConnector
            :rtype: AzureSentinelConnector
        """

        self.logger = logging.getLogger(__name__)
        self.cfg = cfg

        self.bearer_token = self.getBearerToken(self.cfg['AzureSentinel', 'auth_id'], self.cfg['AzureSentinel', 'api_key'])

    def getBearerToken(self, auth_id, client_id, api_key):
        self.url = 'https://login.microsoftonline.com/{}/oauth2/token'.format(auth_id)
        self.data= 'grant_type=client_credentials&client_id={}&client_secret={}&resource=https%3A%2F%2Fmanagement.azure.com&undefined='.format(client_id, api_key)
        # Adding empty header as parameters are being sent in payload
        self.headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "cache-control": "no-cache",
        }
        try:
            self.response = requests.post(self.url, self.data, headers=self.headers)
            self.logger.debug("Retrieved token: {}".format(r.json()["access_token"]))
            return self.response.json()["access_token"]
        except Exception as e:
            self.logger.error("Could not get Bearer token from Azure Sentinel: {}".format(e))

    def getIncidents(self, subscription_id, resource_group, workspace):
        self.url = 'https://management.azure.com/subscriptions/{}/resourceGroups/{}/providers/Microsoft.OperationalInsights/workspaces/{}/providers/Microsoft.SecurityInsights/incidents?api-version=2020-01-01'.format(subscription_id, resource_group, workspace)

        # Adding empty header as parameters are being sent in payload
        self.headers = {
            "Authorization": "Bearer " + self.bearer_token,
            "cache-control": "no-cache",
        }
        try:
            self.response = requests.get(self.url, headers=self.headers)
            return self.response.json()["value"]
        except Exception as e:
            self.logger.error("Could not retrieve incidents from Azure Sentinel: {}".format(e))
