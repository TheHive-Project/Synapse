#!/usr/bin/env python3
# -*- coding: utf8 -*-

import logging
from .QRadarConnector import QRadarConnector
from .TheHiveConnector import TheHiveConnector
from .CortexConnector import CortexConnector

class Actuator():
    'Actuator class to group all possible actions following a listened webhook'

    def __init__(self, cfg):
        """
            Class constructor

            :param cfg: Synapse's config
            :type cfg: ConfigParser

            :return: Object Actuator
            :rtype: Actuator
        """

        self.cfg = cfg
        self.logger = logging.getLogger('workflows.' + __name__)
        self.theHiveConnector = TheHiveConnector(cfg)
        if self.cfg.getboolean('Cortex', 'enabled'):
            self.cortexConnector = CortexConnector(cfg)
        else:
            self.logger.warning('Cortex integration is not enabled, which can lead to errors notifications if Cortex functions are used')
     
    def updateCase(self, case, fields):
        """
            Update a case with enriched data
        """

        self.logger.debug('%s.updateCase starts', __name__)
        try:
            self.theHiveConnector.updateCase(case, fields)
        except Exception as e:
            self.logger.error('Failed to update case %s', case, exc_info=True)
            raise

    def getCase(self, caseid):
        """
            Get case information by providing the case id
        """

        self.logger.debug('%s.getCase starts', __name__)
        try:
            response = self.theHiveConnector.getCase(caseid)
            case_data = response.json()
            return case_data
        except Exception as e:
            self.logger.error('Failed to get case for %s', caseid, exc_info=True)
            raise

    def createCaseFromAlert(self, alert_id, casetemplate):
        """
            Create a case from an alert
        """

        self.logger.debug('%s.createCaseFromAlert starts', __name__)
        try:
            self.theHiveConnector.createCaseFromAlert(alert_id, casetemplate)
        except Exception as e:
            self.logger.error('Failed to create case from alert %s', alert_id, exc_info=True)
            raise
            
    def updateAlertDescription(self, alertid, alert):
        """
            Update an alert description
        """
        self.fields = ["description"]

        self.logger.debug('%s.updateAlertDescription starts', __name__)
        try:
            self.theHiveConnector.updateAlert(alertid, alert, self.fields)
        except Exception as e:
            self.logger.error('Failed to update alert %s', alertid, exc_info=True)
            raise
            
    def getCaseObservables(self, caseid):
        """
            Get case observables by providing the case id
        """

        self.logger.debug('%s.getCaseObservables starts', __name__)
        try:
            response = self.theHiveConnector.getCaseObservables(caseid)
            case_data = response.json()
            return case_data
        except Exception as e:
            self.logger.error('Failed to get case observables for %s', caseid, exc_info=True)
            raise
            
    def getCaseTasks(self, caseid):
        """
            Get case tasks by providing the case id
        """

        self.logger.debug('%s.getCaseTasks starts', __name__)
        try:
            response = self.theHiveConnector.getCaseTasks(caseid)
            case_task_data = response.json()
            return case_task_data
        except Exception as e:
            self.logger.error('Failed to get case tasks for %s', caseid, exc_info=True)
            raise
            
    def createTask(self, caseid,casetask):
        """
            Create case tasks by providing the case id
        """

        self.logger.debug('%s.createCaseTask starts', __name__)
        try:
            task_id = self.theHiveConnector.createTask(caseid, casetask)
            return task_id
        except Exception as e:
            self.logger.error('Failed to create case task for %s', caseid, exc_info=True)
            raise
    
    def runAnalyzer(self, cortex_server, observable, analyzer):
        """
            Run an analyzer for an observable
        """

        self.logger.debug('%s.runAnalyzer starts', __name__)
        try:
            self.theHiveConnector.runAnalyzer(cortex_server, observable, analyzer)
        except Exception as e:
            self.logger.error('Failed to start analyzer for observable %s', observable, exc_info=True)
            raise

    def runResponder(self, cortex_server, observable, responder):
        """
            Run a responder for an observable
        """

        self.logger.debug('%s.runResponder starts', __name__)
        try:
            self.theHiveConnector.runResponder(cortex_server, observable, responder)
        except Exception as e:
            self.logger.error('Failed to start responder for observable %s', observable, exc_info=True)
            raise

    def runResponderDirect(self, responder, data):
        """
            Run a responder for an observable
        """

        self.logger.debug('%s.runResponderDirect starts', __name__)
        try:
            self.cortexConnector.runResponder(responder, data)
        except Exception as e:
            self.logger.error('Failed to start responder %s', exc_info=True)
            raise

class QRadarActuator(Actuator):
    'Actuator class to group all possible actions following a listened webhook'

    def __init__(self, cfg):
        """
            Class constructor

            :return: Object Actuator
            :rtype: Actuator
        """

        self.cfg = cfg
        self.logger = logging.getLogger('workflows.' + __name__)
        self.theHiveConnector = TheHiveConnector(cfg)
        self.cortexConnector = CortexConnector(cfg)
        self.qradarConnector = QRadarConnector(cfg)

    def getQRadarConfig(self):
        """
            Get case information by providing the case id
        """

        self.logger.debug('%s.getQRadarSupportedDataTypes starts', __name__)
        try:
            qr_config = {}
            qr_config['supported_datatypes'] = self.cfg.get('QRadar', 'supported_datatypes')
            return qr_config['supported_datatypes']
        except Exception as e:
            self.logger.error('Failed to get supported data types', exc_info=True)
            raise
    
    def Search(self, query):
        """
            Get the results from a query
        """
        #query_results = collections.OrderedDict()
        
        try:
            query_results = self.qradarConnector.aqlSearch(query)
            
            return query_results
        except Exception as e:
            self.logger.error('Failed to perform query', exc_info=True)
            raise
    
    def RetrieveValue(self, query):
        """
            Get a single value from the results of a query
        """
        try:
            query_results = self.qradarConnector.aqlSearch(query)['events'][0]['result']
            
            return query_results
        except Exception as e:
            self.logger.error('Failed to perform query', exc_info=True)
            raise
    
    def closeOffense(self, offenseId):
        """
            Close an offense in QRadar given a specific offenseId
        """

        self.logger.debug('%s.closeOffense starts', __name__)
        try:
            if self.qradarConnector.offenseIsOpen(offenseId):
                self.qradarConnector.closeOffense(offenseId)
            else:
                self.logger.info('Offense %s already closed', offenseId)
        except Exception as e:
            self.logger.error('Failed to close offense %s', offenseId, exc_info=True)
            raise

class ElasticSearchActuator(Actuator):
    'Actuator class to group all possible actions following a listened webhook'

    def __init__(self, cfg):
        """
            Class constructor

            :return: Object Actuator
            :rtype: Actuator
        """

        self.cfg = cfg
        self.logger = logging.getLogger('workflows.' + __name__)
        self.theHiveConnector = TheHiveConnector(cfg)
        self.cortexConnector = CortexConnector(cfg)
        # self.elasticsearchConnector = ElasticSearchConnector(cfg)
    
    # def Search(self, query):
    #     """
    #         Get the results from a query
    #     """

    #     try:
    #         query_results = self.elasticsearchConnector.esSearch(query)
            
    #         return query_results
    #     except Exception as e:
    #         self.logger.error('Failed to perform query', exc_info=True)
    #         raise

    # def RetrieveValue(self, query):
    #     """
    #         Get a single value from the results of a query
    #     """
    #     try:
    #         query_results = self.elasticsearchConnector.esSearch(query)['events'][0]['result']
            
    #         return query_results
    #     except Exception as e:
    #         self.logger.error('Failed to perform query', exc_info=True)
    #         raise