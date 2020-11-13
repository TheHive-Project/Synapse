import logging
import requests
import json
import time
from datetime import datetime, timezone
from dateutil import tz

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
        self.subscription_id = self.cfg.get('AzureSentinel', 'subscription_id')
        self.resource_group = self.cfg.get('AzureSentinel', 'resource_group')
        self.workspace = self.cfg.get('AzureSentinel', 'workspace')
        self.tenant_id = self.cfg.get('AzureSentinel', 'tenant_id')
        self.client_id = self.cfg.get('AzureSentinel', 'client_id')
        self.client_secret = self.cfg.get('AzureSentinel', 'client_secret')
        self.base_url = 'https://management.azure.com/subscriptions/{}/resourceGroups/{}/providers/Microsoft.OperationalInsights/workspaces/{}/providers/Microsoft.SecurityInsights'.format(self.subscription_id, self.resource_group, self.workspace)

        self.bearer_token = self.getBearerToken()

    def getBearerToken(self):
        self.url = 'https://login.microsoftonline.com/{}/oauth2/token'.format(self.tenant_id)
        self.data = 'grant_type=client_credentials&client_id={}&client_secret={}&resource=https%3A%2F%2Fmanagement.azure.com&undefined='.format(self.client_id, self.client_secret)
        # Adding empty header as parameters are being sent in payload
        self.headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "cache-control": "no-cache",
        }
        try:
            self.response = requests.post(self.url, self.data, headers=self.headers)
            self.logger.debug("Retrieved token: {}".format(self.response.json()["access_token"]))
            return self.response.json()["access_token"]
        except Exception as e:
            self.logger.error("Could not get Bearer token from Azure Sentinel: {}".format(e))

    def formatDate(self, target, sentinelTimeStamp):
        #Example: 2020-10-22T12:55:27.9576603Z << can also be six milliseconds. Cropping the timestamp therefore...
        #Define timezones
        current_timezone = tz.gettz('UTC')
        
        #Retrieve timezone from config or use local time (None)
        configured_timezone = self.cfg.get('AzureSentinel', 'timezone', fallback=None)
        new_timezone = tz.gettz(configured_timezone)

        #Parse timestamp received from Sentinel cropping to six milliseconds as 7 is not supported
        self.logger.debug("Cropped timestamp from: {} to: {}".format(sentinelTimeStamp, sentinelTimeStamp[0:23]))
        formatted_time = datetime.strptime(sentinelTimeStamp[0:23], "%Y-%m-%dT%H:%M:%S.%f")
        utc_formatted_time = formatted_time.replace(tzinfo=current_timezone)

        #Convert to configured timezone
        ntz_formatted_time = formatted_time.astimezone(new_timezone)

        if target == "description":

            #Create a string from time object
            string_formatted_time = ntz_formatted_time.strftime('%Y-%m-%d %H:%M:%S')

        elif target == "alert_timestamp":
            #Create a string from time object
            string_formatted_time = ntz_formatted_time.timestamp() * 1000

        return string_formatted_time

    def getIncident(self, incidentId):
        # Variable required for handling regeneration of the Bearer token
        self.bearer_token_regenerated = False
        self.url = self.base_url + '/incidents/{}?api-version=2020-01-01'.format(incidentId)

        # Adding empty header as parameters are being sent in payload
        self.headers = {
            "Authorization": "Bearer " + self.bearer_token,
            "cache-control": "no-cache",
        }
        try:
            self.response = requests.get(self.url, headers=self.headers)
            self.incident = self.response.json()

            if (self.response.status_code == 200):
                self.logger.debug('Incident %s successsfully retrieved', incidentId)
                return self.incident
            elif self.response.status_code == 401:
                raise ConnectionRefusedError(self.response.content)
            else:
                raise ValueError(self.response.content)
        except ValueError as e:
            self.logger.error('AzureSentinel returned http %s', str(self.response.status_code))
        except ConnectionRefusedError as e:
            # Supporting regeneration of the token automatically. Will try once and will fail after
            if not self.bearer_token_regenerated:
                self.logger.info("Bearer token expired. Generating a new one")
                self.bearer_token = self.getBearerToken()
                self.bearer_token_regenerated = True
                self.getIncident()
        except Exception as e:
            self.logger.error('Failed to retrieve incident %s', incidentId, exc_info=True)
            raise

            self.logger.error("Could not retrieve incident from Azure Sentinel: {}".format(e))

    def updateIncidentStatusToActive(self, incidentId):
        # Variable required for handling regeneration of the Bearer token
        self.bearer_token_regenerated = False
        self.url = self.base_url + '/incidents/{}?api-version=2020-01-01'.format(incidentId)

        # Adding empty header as parameters are being sent in payload
        self.headers = {
            "Authorization": "Bearer " + self.bearer_token,
            "cache-control": "no-cache",
        }
        try:
            self.incident = requests.get(self.url, headers=self.headers).json()
            if self.incident['properties']['status'] == "Active":
                self.logger.info("Incident {} is already marked as Active".format(incidentId))
                return True
            else:
                self.data = {
                    "etag": "\"{}\"".format(self.incident['etag']),
                    "properties": {
                        "title": self.incident['properties']['title'],
                        "status": "Active",
                        "severity": self.incident['properties']['severity'],
                    }
                }
                self.response = requests.put(self.url, headers=self.headers, json=self.data)
                if (self.response.status_code == 200):
                    self.logger.info('Incident %s successsfully updated', incidentId)
                    return True
                elif self.response.status_code == 401:
                    raise ConnectionRefusedError(self.response.content)
                else:
                    raise ValueError(self.response.content)
        except ValueError as e:
            self.logger.error('AzureSentinel returned http %s', str(self.response.status_code))
        except ConnectionRefusedError as e:
            # Supporting regeneration of the token automatically. Will try once and will fail after
            if not self.bearer_token_regenerated:
                self.logger.info("Bearer token expired. Generating a new one")
                self.bearer_token = self.getBearerToken()
                self.bearer_token_regenerated = True
                self.getIncident()
        except Exception as e:
            self.logger.error('Failed to update incident %s', incidentId, exc_info=True)
            raise
    
    def closeIncident(self, incidentId, classification, classification_comment):
        # Variable required for handling regeneration of the Bearer token
        self.bearer_token_regenerated = False
        self.url = self.base_url + '/incidents/{}?api-version=2020-01-01'.format(incidentId)

        # Adding empty header as parameters are being sent in payload
        self.headers = {
            "Authorization": "Bearer " + self.bearer_token,
            "cache-control": "no-cache",
        }
        try:
            self.incident = requests.get(self.url, headers=self.headers).json()
            if self.incident['properties']['status'] == "Closed":
                self.logger.info("Incident {} is already closed".format(incidentId))
                return True
            else:
                self.data = {
                    "etag": "\"{}\"".format(self.incident['etag']),
                    "properties": {
                        "title": "{}".format(self.incident['properties']['title']),
                        "status": "Closed",
                        "severity": "Medium",
                        "classification": classification,
                        "classificationComment": classification_comment
                    }
                }
                # True Positive requires classificationReason. Currently there is only one option
                if classification == "TruePositive":
                    self.data['properties']['classificationReason'] = "SuspiciousActivity"
                
                self.response = requests.put(self.url, headers=self.headers, json=self.data)
                if (self.response.status_code == 200):
                    self.logger.info('Incident %s successsfully closed', incidentId)
                    return True
                elif self.response.status_code == 401:
                    raise ConnectionRefusedError(self.response.content)
                else:
                    raise ValueError(self.response.content)
        except ValueError as e:
            self.logger.error('AzureSentinel returned http %s', str(self.response.status_code))
        except ConnectionRefusedError as e:
            # Supporting regeneration of the token automatically. Will try once and will fail after
            if not self.bearer_token_regenerated:
                self.logger.info("Bearer token expired. Generating a new one")
                self.bearer_token = self.getBearerToken()
                self.bearer_token_regenerated = True
                self.getIncident()
        except Exception as e:
            self.logger.error('Failed to close incident %s', incidentId, exc_info=True)
            raise

    def getIncidents(self):
        # Variable required for handling regeneration of the Bearer token
        self.bearer_token_regenerated = False

        # Empty array for incidents
        self.incidents = []

        self.url = self.base_url + '/incidents?api-version=2020-01-01&%24filter=(properties%2Fstatus%20eq%20\'New\'%20or%20properties%2Fstatus%20eq%20\'Active\')&%24orderby=properties%2FcreatedTimeUtc%20desc'

        # Adding empty header as parameters are being sent in payload
        self.headers = {
            "Authorization": "Bearer " + self.bearer_token,
            "cache-control": "no-cache",
        }
        try:
            self.response = requests.get(self.url, headers=self.headers)
            self.incidents.extend(self.response.json()["value"])
            # Lazy loop to grab all incidents
            while 'nextLink' in self.response.json():
                self.url = self.response.json()['nextLink']
                self.response = requests.get(self.url, headers=self.headers)
                self.incidents.extend(self.response.json()["value"])
                if (self.response.status_code == 200):
                    self.logger.debug('Incidents successsfully retrieved')
                elif self.response.status_code == 401:
                    raise ConnectionRefusedError(self.response.content)
                else:
                    raise ValueError(self.response.content)
        except ValueError as e:
            self.logger.error('AzureSentinel returned http %s', str(self.response.status_code))
        except ConnectionRefusedError as e:
            # Supporting regeneration of the token automatically. Will try once and will fail after
            if not self.bearer_token_regenerated:
                self.logger.info("Bearer token expired. Generating a new one")
                self.bearer_token = self.getBearerToken()
                self.bearer_token_regenerated = True
                self.getIncident()
        except Exception as e:
            self.logger.error('Failed to retrieve incidents', exc_info=True)
            raise

        return self.incidents

    def getRule(self, uri):
        #Variable required for handling regeneration of the Bearer token
        self.bearer_token_regenerated = False

        self.url = 'https://management.azure.com{}?api-version={}'.format(uri, "2020-01-01")

        # Adding empty header as parameters are being sent in payload
        self.headers = {
            "Authorization": "Bearer " + self.bearer_token,
            "cache-control": "no-cache",
        }
        try:
            self.response = requests.get(self.url, headers=self.headers)
            return self.response.json()
        except Exception as e:
            #Supporting regeneration of the token automatically. Will try once and will fail after
            if self.response.status_code == 401 and not self.bearer_token_regenerated:
                self.logger.info("Bearer token expired. Generating a new one")
                self.bearer_token = self.getBearerToken()
                self.bearer_token_regenerated = True
                self.getIncidents()

            self.logger.error("Could not retrieve rule information from Azure Sentinel: {}".format(e))
