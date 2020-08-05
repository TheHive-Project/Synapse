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

class Automation:
    def __init__(self, webhook, cfg):
        logger.info('Initiating ELKAutomation')
        self.TheHiveConnector = TheHiveConnector(cfg)
        self.webhook = webhook
        self.es_config = {}
        for key, value in cfg.items('ELK'):
            self.es_config[key] = value
        self.report_action = report_action
        self.webhook = webhook
  
    #Allow stringed output when needed
    def __repr__(self):
        return str(self.__dict__)

    #Not working still as thehive4py is not added correctly yet
    def parse_hooks(self):
        logger.info('Start parsing webhooks for ELK automation')
        
        #Set the default action
        self.report_action = 'None'

        #if it is a new case
        if self.webhook.isImportedAlert():
            logger.info('Registered the finishing steps of the creation of a new case')
            #Register case info
            self.caseid = self.webhook.data['details']['case']
            self.tags = self.webhook.data['object']['tags']
            self.description = self.webhook.data['object']['description']

            #Enrich the case information with missing information from the alert 
            if 'ELK' in self.webhook.data['object']['tags']:
                self.report_action = 'enrichCase' 
                logger.info('Alert {} has been tagged as ELK and is just imported or following has been reenabled. Adding custom fields'.format(self.webhook.data['details']['case']))
                # Enrich offense with information from the alert by posting the missing information through an API call

                #Create a Case object
                self.case = Case()
                
                #Add the case id to the object
                self.case.id = self.caseid
                logger.info('Updating case %s' % self.case.id)

                #Define which fields need to get updated
                fields = ['customFields']
                
                #Retrieve all required attributes from the alert and add them as custom fields to the case
                customFields = CustomFieldHelper()\
                    .add_string('anomalyType', self.webhook.data['object']['type'])\
                    .add_string('source', self.webhook.data['object']['source'])\
                    .build()
                
                #Add custom fields to the case object
                self.case.customFields = customFields

                #Update the case
                response = self.TheHiveConnector.updateCase(self.case,fields)

        return report_action