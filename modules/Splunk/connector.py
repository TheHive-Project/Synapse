#!/usr/bin/env python3
# -*- coding: utf8 -*-

import logging
import requests
import re
import json
import time
import base64
import sys
import os
from datetime import datetime, timezone
from dateutil import tz
from collections import OrderedDict
from multiprocessing import Process, Queue

class SplunkConnector:
    'Splunk connector'

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

        #Load proxy as environment variables as splunklib does not allow configuring it
        
        os.environ['http_proxy'] = self.cfg.get('Splunk', 'http_proxy')
        os.environ['https_proxy'] = self.cfg.get('Splunk', 'https_proxy')

        # Retrieve base values for the connection to the Splunk API
        self.splunk_base_url = self.cf g.get('Splunk', 'url')
        self.username = self.cfg.get('Splunk', 'username')
        self.password = self.cfg.get('Splunk', 'password')
        self.max_result_count = self.cfg.get('Splunk', 'max_result_count')

        self.client = self.initiateConnection()

    def initiateConnection(self):

        """
            Returns API client for Splunk

            :return: an object with the API client
            :rtype: object
        """

        self.logger.debug('%s.getClient starts', __name__)

        try:
            logging.debug("logging into {0} as user {1}".format(self.uri, self.username))
            
            client = splunklib.SplunkQueryObject(uri=self.splunk_base_url, username=self.username, password=self.password, max_result_count=self.max_result_count)

            if not client.authenticate():
                self.logger.error("Could not authenticate to Splunk")

            return client

        except Exception as e:
            self.logger.error('Failed to initiate Splunk client', exc_info=True)
            raise

    def query(self, query, start_time=None, end_time=None, relative_time=False):
        """
            Perfoms a query given a query

            :param query: a Splunk query
            :type query: str
            :param start_time: the start time for the query. Can be relative or absolute
            :type start_time: str
            :param end_time: the end time for the query. Can be relative or absolute
            :type end_time: str
            :param relative_time: defines if start and end time are relative or not
            :type relative_time: boolean

            :return body_json: the result of the query
            :rtype body_json: dict
        """

        self.logger.debug('%s.query starts', __name__)
        try:
            #Used to provide relative timestamps to subtract from the current time (00:00:10 will substract 10 seconds)
            if (start_time is not None or end_time is not None) and relative_time:
                    search_result = self.client.query_relative(query, relative_duration_before=start_time, relative_duration_after=end_time)
            #Use exact timestamps ('%m/%d/%Y:%H:%M:%S ex. 03/21/2020:12:00:12)
            else if start_time is not None and end_time is not None and not relative_time:
                search_result = self.client.query_with_time(query, start_time, end_time)
            #When there are no timestamps       
            else:
                search_result = self.client.query(query)

            if not search_result:
                self.logger.error("The search has failed please look at the details of the error")
                sys.exit(1)
            else:
                return self.client.json()

        except Exception as e:
            self.logger.error('%s.query failed', __name__, exc_info=True)
            raise
