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

logger = logging.getLogger('workflows')

current_time = 0

#When no condition is match, the default action is None
report_action = 'None'

class MISPAutomation():
    def __init__(self, webhook, cfg):
        logger.info('Initiating MISPautomation')
        self.TheHiveConnector = TheHiveConnector(cfg)
        if self.cfg.getboolean('Cortex', 'enabled'):
            self.CortexConnector = CortexConnector(cfg)
        self.webhook = webhook
        self.report_action = report_action
        self.qr_config = {}
        for key, value in cfg.items('QRadar'):
            self.qr_config[key] = value
        
    def parse_misp_hooks(self):
        """
        Check for new MISP Alert containing supported IOC to search automatically
        """
        
        if self.webhook.isNewMispAlert():
            logger.info('Alert {} has been tagged as MISP and is just created'.format(self.webhook.data['rootId']))
            
            #Check alert for supported ioc types
            supported_iocs = False
            for artifact in self.webhook.data['object']['artifacts']:
                if artifact['dataType'] in self.qr_config['supported_datatypes']:
                    supported_iocs = True
                
            #Promote alert to case if there are support ioc types
            if supported_iocs:
                alert_id = self.webhook.data['rootId']
                casetemplate = "MISP Event"
            
                logger.info('Alert {} contains IOCs that are supported'.format(alert_id))

                response = self.TheHiveConnector.createCaseFromAlert(alert_id, casetemplate)
                
                self.report_action = 'createCase'
                    
        """
        Add timestamps to keep track of the search activity per case (we do not want to keep searching forever)
        """
        #Perform automated Analyzer runs for supported observables in a case that has been created from a MISP alert
        if self.webhook.isNewMispCase():
            logger.info('Case {} has been tagged as MISP and is just created'.format(self.webhook.data['rootId']))
            
            #Retrieve caseid
            caseid = self.webhook.data['object']['id']
            
            #Add customFields firstSearched and lastSearched
            #Create a Case object? Or whatever it is
            case = Case()
            
            #Add the case id to the object
            case.id = caseid
            
            #Debug output
            logger.info('Updating case %s' % case.id)

            #Define which fields need to get updated
            fields = ['customFields']
            
            #Retrieve all required attributes from the alert and add them as custom fields to the case
            current_time = int(round(time.time() * 1000))
            customFields = CustomFieldHelper()\
                .add_date('firstSearched', current_time)\
                .add_date('lastSearched', current_time)\
                .build()
            
            #Add custom fields to the case object
            case.customFields = customFields

            #Update the case
            self.TheHiveConnector.updateCase(case,fields)
            self.report_action = 'updateCase'
        
        """
        Start the analyzers automatically for MISP observables that are supported and update the case with a new timestamp
        """
        #Automatically run Analyzers for newly created MISP cases where supported IOC's are present
        if self.webhook.isNewMispArtifact():
            logger.info('Case artifact is tagged with "MISP-extern". Checking if observable is of a supported type')
            
            #Retrieve caseid
            caseid = self.webhook.data['rootId']
            
            #Retrieve case data
            case_data = self.TheHiveConnector.getCase(caseid)
            
            #List all supported ioc's for the case
            observable = self.webhook.data['object']
            
            #When supported, start a cortex analyzer for it
            if observable['dataType'] in self.qr_config['supported_datatypes']:
                supported_observable = observable['_id']
            
                #Trigger a search for the supported ioc
                logger.info('Launching analyzers for observable: {}'.format(observable['_id']))
                response = self.CortexConnector.runAnalyzer("Cortex-intern", supported_observable, "IBMQRadar_Search_Manual_0_1")
                
                #Add customFields firstSearched and lastSearched
                #Create a Case object
                case = Case()
                
                #Add the case id to the object
                case.id = caseid
                
                #Debug output
                logger.info('Updating case %s' % case.id)

                #Define which fields need to get updated
                fields = ['customFields']
                
                #Retrieve all required attributes from the alert and add them as custom fields to the case
                current_time = int(round(time.time() * 1000))
                customFields = CustomFieldHelper()\
                    .add_date('firstSearched', case_data['customFields']['firstSearched']['date'])\
                    .add_date('lastSearched', current_time)\
                    .build()
                
                #Add custom fields to the case object
                case.customFields = customFields

                #Update the case
                self.TheHiveConnector.updateCase(case,fields)
                self.report_action = 'updateCase'
                
        """
        Automatically create a task for a found IOC
        """
        #If the Job result contains a successful search with minimum of 1 hit, create a task to investigate the results
        if self.webhook.isCaseArtifactJob() and self.webhook.isSuccess() and self.webhook.isMisp():
            #Case ID
            caseid = self.webhook.data['rootId']
            #Load Case information
            case_data = self.TheHiveConnector.getCase(caseid)
            
            logger.info('Job {} is part of a case that has been tagged as MISP case and has just finished'.format(self.webhook.data['object']['cortexJobId']))
            
            #Check if the result count higher than 0
            if int(float(self.webhook.data['object']['report']['summary']['taxonomies'][0]['value'])) > 0:
                logger.info('Job {} contains hits, checking if a task is already present for this observable'.format(self.webhook.data['object']['cortexJobId']))
                #Retrieve case task information
                response = self.TheHiveConnector.getCaseTasks(caseid)
                case_tasks = response.json()
                
                #Load CaseTask template
                casetask = CaseTask()
                
                #Observable + Link
                observable = self.webhook.data['object']['artifactId']
                observable_link = TheHive.get('url') + "/index.html#/case/" + caseid + "/observables/" + self.webhook.data['object']['artifactId']
                
                #Task name
                casetask.title = "Investigate found IOC with id: {}".format(observable)
                
                #Date
                date_found = time.strftime("%d-%m-%Y %H:%M")
                
                case_task_found = False
                for case_task in case_tasks:
                
                    #Check if task is present for investigating the new results
                    if casetask.title == case_task['title']:
                        case_task_found = True
                
                if not case_task_found:
                    logger.info('No task found, creating task for observable found in job {}'.format(self.webhook.data['object']['cortexJobId']))
                    #Add description
                    casetask.description = "The following ioc is hit in the environment. Investigate the results and act accordingly:\n\n"
                    casetask.description = casetask.description + "{} is seen on {}\n".format(observable_link, date_found)
                    
                    #Check if case is closed
                    if case_data['status'] == "Resolved":
                        #Create a Case object? Or whatever it is
                        case = Case()
                        
                        #Add the case id to the object
                        case.id = caseid
                        
                        logger.info('Updating case %s' % case.id)

                        #Define which fields need to get updated
                        fields = ['status']
                        
                        #Reopen the case
                        case.status = "Open"

                        #Update the case
                        self.TheHiveConnector.updateCase(case,fields)
                    
                    #Add the case task
                    self.TheHiveConnector.createTask(caseid,casetask)
                    self.report_action = 'createTask'
                    
        return self.report_action