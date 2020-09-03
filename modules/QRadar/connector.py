#!/usr/bin/env python3
# -*- coding: utf8 -*-

import logging
import time, json
from datetime import datetime, timezone
from dateutil import tz
from collections import OrderedDict
from .objects.RestApiClient import RestApiClient
from .objects.arielapiclient import APIClient
from multiprocessing import Process, Queue

class QRadarConnector:
    'QRadar connector'

    def __init__(self, cfg):
        """
            Class constuctor

            :param cfg: synapse configuration
            :type cfg: ConfigParser

            :return: Object QRadarConnector
            :rtype: QRadarConnector
        """

        self.logger = logging.getLogger(__name__)
        self.cfg = cfg
        clients = self.getClients()
        self.client = clients[0]
        self.arielClient = clients[1]
        
        self.redis_enabled = self.cfg.getboolean('QRadar', 'api_redis_cache')
        if self.redis_enabled:
            import redis
            self.redis_sip = redis.StrictRedis(host="localhost", port=6379, db=0)
            self.redis_dip = redis.StrictRedis(host="localhost", port=6379, db=1)

    def formatDate(self, qradarTimeStamp):
        #Define timezones
        current_timezone = tz.gettz('UTC')
        
        #Retrieve timezone from config or use local time (None)
        configured_timezone = self.cfg.get('QRadar', 'timezone', fallback=None)
        new_timezone = tz.gettz(configured_timezone)

        #Parse timestamp received from QRadar
        qradarTimeStamp = qradarTimeStamp / 1000.0
        formatted_time = datetime.fromtimestamp(qradarTimeStamp)
        utc_formatted_time = formatted_time.replace(tzinfo=current_timezone)

        #Convert to configured timezone
        ntz_formatted_time = formatted_time.astimezone(new_timezone)

        #Create a string from time object
        string_formatted_time = ntz_formatted_time.strftime('%Y-%m-%d %H:%M:%S')

        return string_formatted_time

    def getClients(self):

        """
            Returns API client for QRadar and ariel client

            :return: a list which 1st element is API client and
                    2nd is ariel client
            :rtype: list
        """

        self.logger.debug('%s.getClient starts', __name__)

        try:
            server = self.cfg.get('QRadar', 'server')
            auth_token = self.cfg.get('QRadar', 'auth_token')
            cert_filepath = self.cfg.get('QRadar', 'cert_filepath')
            cert_verification = self.cfg.get('QRadar', 'cert_verification')
            api_version = self.cfg.get('QRadar', 'api_version')
            http_proxy = self.cfg.get('QRadar', 'http_proxy')
            https_proxy = self.cfg.get('QRadar', 'https_proxy')

            client = RestApiClient(server,
                auth_token,
                cert_filepath,
                cert_verification,
                api_version,
                http_proxy=http_proxy,
                https_proxy=https_proxy) 

            arielClient = APIClient(server,
                auth_token,
                cert_filepath,
                cert_verification,
                api_version,
                http_proxy=http_proxy,
                https_proxy=https_proxy)

            clients = list()
            clients.append(client)
            clients.append(arielClient)

            return clients

        except Exception as e:
            self.logger.error('Failed to get QRadar client', exc_info=True)
            raise

    def getOffenses(self, timerange):
        """
            Returns all offenses within a list

            :param timerange: timerange in minute (get offense
                                for the last <timerange> minutes)
            :type timerange: int

            :return response_body: list of offenses, one offense being a dict
            :rtype response_body: list
        """

        self.logger.debug('%s.getOffenses starts', __name__)

        try:
            if timerange == "all":
                query = 'siem/offenses?filter=status%3DOPEN'
            else:
                #getting current time as epoch in millisecond
                now = int(round(time.time() * 1000))
            
                #filtering by time for offenses
                #timerange is in minute while start_time in QRadar is in millisecond since epoch
                #converting timerange in second then in millisecond
                timerange = int(timerange * 60 * 1000)
            
                #timerange is by default 1 minutes
                #so timeFilter is now minus 1 minute
                #this variable will be use to query QRadar for every offenses since timeFilter
                timeFilter = now - timerange
            
                # %3E <=> >
                # %3C <=> <
                # moreover we filter on OPEN offenses only
                query = 'siem/offenses?filter=last_updated_time%3E' + str(timeFilter) + '%20and%20last_updated_time%3C' + str(now) + '%20and%20status%3DOPEN'
            
            self.logger.debug(query)
            response = self.client.call_api(
                query, 'GET')
        
            try:
                response_text = response.read().decode('utf-8')
                response_body = json.loads(response_text)
        
                #response_body would look like
                #[
                #  {
                #    "credibility": 42,
                #    "source_address_ids": [
                #      42
                #    ],
                #    "remote_destination_count": 42,
                #    "local_destination_address_ids": [
                #      42
                #    ],
                #    "assigned_to": "String",
                #    "local_destination_count": 42,
                #    "source_count": 42,
                #    "start_time": 42,
                #    "id": 42,
                #    "destination_networks": [
                #      "String"
                #    ],
                #    "inactive": true,
                #    "protected": true,
                #    "policy_category_count": 42,
                #    "description": "String",
                #    "category_count": 42,
                #    "domain_id": 42,
                #    "relevance": 42,
                #    "device_count": 42,
                #    "security_category_count": 42,
                #    "flow_count": 42,
                #    "event_count": 42,
                #    "offense_source": "String",
                #    "status": "String <one of: OPEN, HIDDEN, CLOSED>",
                #    "magnitude": 42,
                #    "severity": 42,
                #    "username_count": 42,
                #    "closing_user": "String",
                #    "follow_up": true,
                #    "closing_reason_id": 42,
                #    "close_time": 42,
                #    "source_network": "String",
                #    "last_updated_time": 42,
                #    "categories": [
                #      "String"
                #    ],
                #    "offense_type": 42
                #  }
                #]

                if (response.code == 200):
                    return response_body
                else:
                    raise ValueError(json.dumps(
                        response_body,
                        indent=4,
                        sort_keys=True))

            except ValueError as e:
                self.logger.error('%s.getOffenses failed, api call returned http %s',
                    __name__, str(response.code))
                raise

        except Exception as e:
            self.logger.error('getOffenses failed', exc_info=True)
            raise

    def getAddressesFromIDs(self, path, field, ids, queue):
        #using queue to implement a timeout mecanism
        #useful if there are more than 50 IPs to look up
        self.logger.debug("Looking up %s with %s IDs..." % (path,ids))

        address_strings = []

        if self.redis_enabled:
            self.logger.debug("Enabling Redis cache")
            if path == "source_addresses":
                self.redis_ip = self.redis_sip
            if path == "local_destination_addresses":
                self.redis_ip = self.redis_dip

        for address_id in ids:
            try:
                #Check if IP is in Redis, if not query QRadar
                if self.redis_enabled:
                    self.logger.debug('Looking for %s in Redis' % address_id)
                    #Redis return byte
                    self.ip = self.redis_ip.get(address_id)
                    self.logger.debug('Found %s in Redis for %s' % (self.ip, address_id))

                if not self.redis_enabled or self.ip == None:
                    self.logger.debug('Looking up %s in QRadar' % address_id)
                    response = self.client.call_api('siem/%s/%s' % (path, address_id), 'GET')
                    response_text = response.read().decode('utf-8')
                    response_body = json.loads(response_text)

                    try:
                        if response.code == 200:
                            address_strings.append(response_body[field])
                            #Put address in Redis
                            if self.redis_enabled:
                                self.ip = self.redis_ip.set(address_id, response_body[field], 604800)
                        else:
                            self.logger.warning("Couldn't get id %s from path %s (response code %s)" % (address_id, path, response.code))

                    except Exception as e:
                        self.logger.error('%s.getAddressFromIDs failed', __name__, exc_info=True)
                        raise e
                
                else:
                    #Add address found in redis. Decode it so it is a proper string in stead of a byte object
                    address_strings.append(self.ip.decode('UTF-8'))

            except Exception as e:
                self.logger.error('%s.getAddressFromIDs failed', __name__, exc_info=True)
                raise e

        queue.put(address_strings)

    def getSourceIPs(self, offense):
        if not "source_address_ids" in offense:
            return []

        queue = Queue()
        proc = Process(target=self.getAddressesFromIDs, args=("source_addresses", "source_ip", offense["source_address_ids"], queue,))
        proc.start()
        try:
            res = queue.get(timeout=int(self.cfg.get('QRadar', 'api_timeout')))
            proc.join()
            return res
        except:
            proc.terminate()
            self.logger.error('%s.getSourceIPs took too long, aborting', __name__, exc_info=True)
            return []

    def getLocalDestinationIPs(self, offense):
        if not "local_destination_address_ids" in offense:
            return []

        queue = Queue()
        proc = Process(target=self.getAddressesFromIDs, args=("local_destination_addresses", "local_destination_ip", offense["local_destination_address_ids"], queue,))
        proc.start()
        try:
            res = queue.get(timeout=int(self.cfg.get('QRadar', 'api_timeout')))
            proc.join()
            return res
        except:
            proc.terminate()
            self.logger.error('%s.getLocalDestinationIPs took too long, aborting', __name__, exc_info=True)
            return []

    def getOffenseTypeStr(self, offenseTypeId):
        """
            Returns the offense type as string given the offense type id 

            :param offenseTypeId: offense type id
            :type timerange: int

            :return offenseTypeStr: offense type as string
            :rtype offenseTypeStr: str
        """

        self.logger.debug('%s.getOffenseTypeStr starts', __name__)

        offenseTypeStr = 'Unknown offense_type name for id=' + \
            str(offenseTypeId)

        try:
            response = self.client.call_api(
                'siem/offense_types?filter=id%3D' + str(offenseTypeId),
                'GET')
            response_text = response.read().decode('utf-8')
            response_body = json.loads(response_text)

            #response_body would look like
            #[
            #  {
            #    "property_name": "sourceIP",
            #    "database_type": "COMMON",
            #    "id": 0,
            #    "name": "Source IP",
            #    "custom": false
            #  }
            #]

            try:
                if response.code == 200:
                    offenseTypeStr = response_body[0]['name']
                else:
                    self.logger.error(
                        'getOffenseTypeStr failed, api returned http %s',
                         str(response.code))
                    self.logger.error(json.dumps(response_body, indent=4))

                return offenseTypeStr

            except IndexError as e:
                #sometimes QRadar api does not find the offenseType
                #even if it exists
                #I saw this happened in QRadar CE for offense type:
                # 3, 4, 5, 6, 7, 12, 13, 15
                self.logger.warning('%s; response_body empty', __name__)
                return offenseTypeStr

        except Exception as e:
            self.logger.error('%s.getOffenseTypeStr failed', __name__, exc_info=True)
            raise

    def getOffenseLogs(self, offense):
        """
            Returns the first 3 raw logs for a given offense 

            :param offense: offense in QRadar
            :type offense: dict

            :return : logs
            :rtype logs: list of dict
        """

        self.logger.debug('%s.getOffenseLogs starts', __name__)

        try:
            offenseId = offense['id']

            # QRadar does not find the log when filtering
            # on the time window's edges
            #if the window is [14:10 ; 14:20]
            #it should be changes to [14:09 ; 14:21]
            #moreover, since only the first 3 logs are returned
            #no need to use last_updated_time (which might be way after start_time
            #and so consume resource for the search)
            #as such search window is [start_time - 1 ; start_time +5]
            start_time = (offense['start_time'] - 1 * 60 * 1000)
            last_updated_time = (offense['start_time'] + 5 * 60 * 1000)

            ####### NEED TO ADD TIMEZONE INFO HERE #########
            start_timeStr = self.formatDate(start_time)
            last_updated_timeStr = self.formatDate(
                last_updated_time
            )

            query = ("select  DATEFORMAT(starttime,'YYYY-MM-dd HH:mm:ss') as Date, UTF8(payload) from events where INOFFENSE('" + str(offenseId) + "') ORDER BY Date ASC  LIMIT 3 START '" + start_timeStr + "' STOP '" + last_updated_timeStr + "';")

            self.logger.debug(query)
            response = self.aqlSearch(query)

            #response looks like
            #{'events': [{'Date': '2018-08-26 12:39:10',
            #             'utf8_payload': '<85>Aug 26 12:43:37 dev sshd[25454]: '
            #                             'pam_unix(sshd:auth): authentication failure; '
            #                             'logname= uid=0 euid=0 tty=ssh ruser= '
            #                             'rhost=10.0.0.24  user=root'},
            #            {'Date': '2018-08-26 12:39:10',
            #             'utf8_payload': '<85>Aug 26 12:43:37 dev sshd[25448]: '
            #                             'pam_unix(sshd:auth): authentication failure; '
            #                             'logname= uid=0 euid=0 tty=ssh ruser= '
            #                             'rhost=10.0.0.24  user=root'},
            #            {'Date': '2018-08-26 12:39:10',
            #             'utf8_payload': '<85>Aug 26 12:43:37 dev sshd[25453]: '
            #                             'pam_unix(sshd:auth): authentication failure; '
            #                             'logname= uid=0 euid=0 tty=ssh ruser= '
            #                             'rhost=10.0.0.24  user=root'}]}

            logs = response['events']
            return logs


        except Exception as e:
            self.logger.error('%s.getOffenseLogs failed', __name__, exc_info=True)
            raise

    def aqlSearch(self, aql_query):
        """
            Perfoms an aqlSearch given an aql_query

            :param aql_query: an aql query
            :type aql_query: str

            :return body_json: the result of the aql query
            :rtype offenseTypeStr: dict
        """
        
        #body_json = collections.OrderedDict()
        
        self.logger.debug('%s.aqlSearch starts', __name__)
        try:
            response = self.arielClient.create_search(aql_query)
            if (response.code in [200,201]):
                response_json = json.loads(response.read().decode('utf-8'))
                self.logger.debug("AQL Search is created: %s" % response_json)
                search_id = response_json['search_id']
                response = self.arielClient.get_search(search_id)
            else:
                self.logger.error("An error occurred while creating the search: %s, %s" % (response.code, response.read().decode('utf-8')))
                return {}

            error = False
            while (response_json['status'] != 'COMPLETED') and not error:
                if (response_json['status'] == 'EXECUTE') | \
                        (response_json['status'] == 'SORTING') | \
                        (response_json['status'] == 'WAIT'):
                    response = self.arielClient.get_search(search_id)
                    response_json = json.loads(response.read().decode('utf-8'))
                else:
                    self.logger.error("An error occurred while waiting for search completion: %s, %s" % (response.code, response.read().decode('utf-8')))
                    error = True

            response = self.arielClient.get_search_results(
                search_id, 'application/json')
    
            body = response.read().decode('utf-8')
            body_json = json.loads(body, object_pairs_hook=OrderedDict)

            return body_json
            #looks like:
            #{'events': [{'field1': 'field1 value',
            #            'field2': 'field2 value'},
            #            {'field1': 'fied1 value',
            #            'field2': 'field2 value'}
            #            ]}
        except Exception as e:
            self.logger.error('%s.aqlSearch failed', __name__, exc_info=True)
            raise

    def offenseIsOpen(self, offenseId):
        """
            Check if an offense is close or open in QRadar

            :param offenseId: the QRadar offense id
            :type offenseId: str

            :return: True if the offense is open, False otherwise
            :rtype: boolean
        """

        self.logger.debug('%s.offenseIsOpen starts', __name__)

        try:
            response = self.client.call_api('siem/offenses?filter=id%3D' + \
                offenseId, 'GET')

            response_text = response.read().decode('utf-8')
            response_body = json.loads(response_text)

            if (response.code == 200):
                #response_body is a list of dict
                if response_body[0]['status'] == 'OPEN':
                    return True
                else:
                    return False
            else:
                raise ValueError(response_body)
        except ValueError:
            self.logger.error('QRadar returned http %s', str(response.code))
            raise
        except Exception as e:
            self.logger.error('Failed to check offense %s status', offenseId, exc_info=True)
            raise
            

    def closeOffense(self, offenseId):
        """
            Close an offense in QRadar given a specific offenseId

            :param offenseId: the QRadar offense id
            :type offenseId: str

            :return: nothing
            :rtype: 
        """

        self.logger.debug('%s.closeOffense starts', __name__)

        if self.offenseIsOpen(offenseId):
            try:
                #when closing an offense with the webUI, the closing_reason_id
                #is set to 1 by default
                #this behavior is implemented here with a hardcoded
                #closing_reason_id=1
                response = self.client.call_api(
                'siem/offenses/' + str(offenseId) + '?status=CLOSED&closing_reason_id=1', 'POST')
                response_text = response.read().decode('utf-8')
                response_body = json.loads(response_text)
        
                #response_body would look like
                #[
                #  {
                #    "property_name": "sourceIP",
                #    "database_type": "COMMON",
                #    "id": 0,
                #    "name": "Source IP",
                #    "custom": false
                #  }
                #]

                if (response.code == 200):
                    self.logger.info('Offense %s successsfully closed', offenseId)
                else:
                    raise ValueError(response_body)
            except ValueError as e:
                self.logger.error('QRadar returned http %s', str(response.code))
            except Exception as e:
                self.logger.error('Failed to close offense %s', offenseId, exc_info=True)
                raise
        else:
            self.logger.info('Offense %s already closed', offenseId)
            
            
#### Troubleshooten. Wilt nog niet de naam toevoegen aan de rule array
    def getRuleNames(self, offense):
        self.logger.debug('%s.getRuleNames starts', __name__)

        rules = []
        if 'rules' not in offense:
            return rules

        for rule in offense['rules']:
            if 'id' not in rule:
                continue
            if 'type' not in rule:
                continue
            if rule['type'] != 'CRE_RULE':
                rules.append({'id':rule['id'], 'type':rule['type']})
                continue
            rule_id = rule['id']
            self.logger.info('Looking up rule id %s', str(rule_id))
            try:
                response = self.client.call_api('analytics/rules/%s' % rule_id, 'GET')
                response_text = response.read().decode('utf-8')
                response_body = json.loads(response_text)

                if response.code == 200:
                    rules.append({'id':rule['id'], 'type':rule['type'], 'name':response_body['name']})
                else:
                    self.logger.warning('Could not get rule name for offense')

            except Exception as e:
                self.logger.warning('Could not get rule name for offense')

        return rules
