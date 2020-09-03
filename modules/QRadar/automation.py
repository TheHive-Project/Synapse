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
        
        #Load the config file for use case automation
        
    
    def parse_hooks(self):

        #Enrich the case information with missing information from the alert 
        if self.webhook.isQRadarAlertImported() and not 'lse' in self.webhook.data['object']['tags']:
            logger.info('Alert {} has been tagged as QRadar and is just imported. Adding custom fields'.format(self.webhook.data['rootId']))
            # Enrich offense with information from the alert by posting the missing information through an API call

            if 'case' in self.webhook.data['object']:
                #Create a Case object
                case = Case()
                
                #Add the case id to the object
                case.id = self.webhook.data['object']['case']
                logger.info('Updating case %s' % case.id)

                #Define which fields need to get updated
                fields = ['customFields']
                
                #Retrieve all required attributes from the alert and add them as custom fields to the case
                customFields = CustomFieldHelper()
                if self.cfg.get('QRadar', 'offense_type_field'):
                    customFields.add_string(self.cfg.get('QRadar', 'offense_type_field'), self.webhook.data['object']['type'])\
                if self.cfg.get('QRadar', 'offense_source_field'):
                    customFields.add_string(self.cfg.get('QRadar', 'offense_source_field'), self.webhook.data['object']['source'])\
                if self.cfg.get('QRadar', 'offense_id_field'):
                    customFields.add_number(self.cfg.get('QRadar', 'offense_id_field'), int(self.webhook.data['object']['sourceRef']))\
                customFields.build()
                
                #Add custom fields to the case object
                case.customFields = customFields

                #Update the case
                self.TheHiveConnector.updateCase(case,fields)
                self.report_action = 'updateCase'
                
            else:
                logger.info('Alert has no attached case, doing nothing...')
        
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