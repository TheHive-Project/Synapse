import json
import requests
import time
import logging
from datetime import date

from modules.TheHive.connector import TheHiveConnector
from modules.Cortex.connector import CortexConnector
from modules.QRadar.connector import QRadarConnector

#Load required object models
from thehive4py.models import Case, CustomFieldHelper, CaseObservable, CaseTask

logger = logging.getLogger(__name__)

current_time = 0

#When no condition is match, the default action is None
report_action = 'None'

class Automation():
    
    def __init__(self, webhook, cfg):
        logger.info('Initiating QRadarAutomation')
        self.TheHiveConnector = TheHiveConnector(cfg)
        self.QRadarConnector = QRadarConnector(cfg)
        self.webhook = webhook
        self.cfg = cfg
        self.report_action = report_action
        
        #Close offenses in QRadar
        if self.webhook.isClosedQRadarCase() or self.webhook.isDeletedQRadarCase() or self.webhook.isQRadarAlertMarkedAsRead():
            if self.webhook.data['operation'] == 'Delete':
                self.case_id = self.webhook.data['objectId']
            else:
                self.case_id = self.webhook.data['object']['id']
            logger.info('Case {} has been marked as resolved'.format(self.case_id))
            self.QRadarConnector.closeOffense(self.webhook.offenseId) 
            self.report_action = 'closeOffense'
        
        return self.report_action