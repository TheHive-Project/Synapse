#!/usr/bin/env python3
# -*- coding: utf8 -*-

import logging
import json

from cortex4py.api import Api


class CortexConnector:
    'Cortex connector'

    def __init__(self, cfg):
        self.logger = logging.getLogger('workflows.' + __name__)
        self.cfg = cfg

        self.CortexApi = self.connect()

    def connect(self):
        self.logger.info('%s.connect starts', __name__)

        url = self.cfg.get('Cortex', 'url')
        api_key = self.cfg.get('Cortex', 'api_key')

        return Api(url, api_key)
    
    def runResponder(self, responder_id, data):

        """
        :param object_type: type of object for the responder to act upon (for example; case, case_task)
        :param object_id: identifier of the object (id of for example; case, case_task)
        :param responder_id: name of the responder used by the job
        :rtype: json
        """

        self.logger.info('%s.runResponder starts', __name__)

        response = self.CortexApi.responders.run_by_id(responder_id, data)
        return response.json()