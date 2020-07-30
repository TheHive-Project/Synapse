import json
import requests
import time
import threading
import logging
from threading import Thread
from queue import Queue
from datetime import date

import modules.connectors.TheHiveProject.TheHiveConnector as TheHiveConnector
import modules.connectors.TheHiveProject.CortexConnector as CortexConnector
import modules.connectors.QRadar.QRadarConnector as QRadarConnector

#Load required object models
from thehive4py.models import Case, CustomFieldHelper, CaseObservable, CaseTask

logger = logging.getLogger('workflows')

current_time = 0

#Define Queue/Thread settings
#Allowed concurrent threads
concurrent = 5
#Queue size
q = Queue(concurrent * 1000)

#When no condition is match, the default action is None
report_action = 'None'
        
#Define the logic that makes it possible to perform asynchronous requests to The Hive in order to speed up the integration        
def thapi_queue(queued_request):
    
    #Build up the queue
    logger.info('Adding action: %s to queue for: %s (Current queue length: %i)' % (queued_request['action'], queued_request['caseid'], q.qsize()))
    q.put(queued_request)
    
    #Create the first thread
    thread_count = threading.active_count()
    if thread_count <= 1:
        logger.info('Creating thread')
        t = Thread(target=doWork)
        t.daemon = True
        t.start()
        logger.debug('Created thread')
        
#Define the functionality each workers gets
def doWork():
    #Build a loop that keeps the thread alive until queue is empty
    while not q.empty():
        #Build up the threads
        thread_count = threading.active_count()
        #Make sure that the thread count is lower than configured limit and is lower than the queue size
        if thread_count < concurrent and thread_count < q.qsize():
            new_thread_count = thread_count + 1
            logger.info('Current queue size(%i) allows more threads. Creating additional thread: %i' % (q.qsize(), new_thread_count))
            t = Thread(target=doWork)
            t.daemon = True
            t.start()
            logger.debug('Created thread: %i' % new_thread_count)
        
        #Retrieve a queued item
        queued_item = q.get()
        
        #Handle a queued item based on its provided action
        # if queued_item['action'] == "create_case_observable":
        #     logger.info('Working on %s from queue, caseid: %s' % (queued_item['action'], queued_item['caseid']))
        #     #########################
        #     #########################
        #     #Gaat niet werken met self hier
        #     response = self.TheHiveConnector.createCaseObservable(queued_item['caseid'],queued_item['observable'])
            
        #     #Remove the item from queue
        #     q.task_done()

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

            
class QRadarAutomation():
    
    def __init__(self, webhook, cfg):
        logger.info('Initiating QRadarAutomation')
        self.TheHiveConnector = TheHiveConnector(cfg)
        self.QRadarConnector = QRadarConnector(cfg)
        self.webhook = webhook
        self.qr_config = {}
        for key, value in cfg.items('QRadar'):
            self.qr_config[key] = value
        self.report_action = report_action
        
        #Load the config file for use case automation
        
    
    def parse_qradar_hooks(self):

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
                customFields = CustomFieldHelper()\
                    .add_string(self.qr_config['offense_type_field'], self.webhook.data['object']['type'])\
                    .add_string(self.qr_config['offense_source_field'], self.webhook.data['object']['source'])\
                    .add_number(self.qr_config['offense_id_field'], int(self.webhook.data['object']['sourceRef']))\
                    .build()
                
                #Add custom fields to the case object
                case.customFields = customFields

                #Update the case
                self.TheHiveConnector.updateCase(case,fields)
                self.report_action = 'updateCase'
                
            else:
                logger.info('Alert has no attached case, doing nothing...')
            
        #Automatically update cases when new observables are added to the corresponding alert
        # if self.webhook.isQRadarAlertWithArtifacts():
        #     logger.info('Alert {} has been tagged as QRadar and contains artifacts. Updating case artifacts'.format(self.webhook.data['rootId']))
        #     # Enrich offense with information from the alert by posting the missing information through an API call

        #     #Retrieve the value of the linked case
        #     caseid = self.webhook.data['object']['case']
            
        #     #Retrieve observables from the linked case
        #     response = self.TheHiveConnector.getCaseObservables(caseid)
        #     case_observables = response.json()
            
        #     logger.debug('case observables %s' % str(case_observables) )
            
        #     #Build a list of observables present in the case
        #     case_observable_list = []
        #     # observable_tags = {}
        #     for observable in case_observables:
        #         case_observable_list.append(observable['data'])
        #         # if observable['dataType'] == "fqdn":
        #             # observable_tags[observable['data']] = observable['tags']
            
        #     #Debug output
        #     logger.info('Checking for new observables for case %s' % caseid)
            
        #     #Make a counter to count the number of observables updated
        #     observable_counter = 0
            
        #     missing_observables_list = []
            
        #     #Loop through every found artifact
        #     for artifact in self.webhook.data['details']['artifacts']:
            
        #         observable_dict = {}
        #         #Check if the artifact is already present in the case
        #         observable_missing = False
        #         if not artifact['data'] in case_observable_list:
        #             observable_missing = True
                    
        #         # if artifact['dataType'] == "fqdn" and artifact['data'] in observable_tags:
        #             # for tag in artifact['tags']:
        #                 # if not tag in observable_tags[artifact['data']]:
        #                     # observable_missing = True
                
        #         if observable_missing:
        #             logger.debug('Observable %s is missing' % str(artifact['data']) )
        #             observable_counter += 1
                
        #             #Create a Case object? Or whatever it is
        #             observable = CaseObservable()
                    
        #             #Add dataType to the observable object
        #             observable.dataType = artifact['dataType']
                    
        #             #Add description to the observable object
        #             observable.message = artifact['message']
                    
        #             #Add TLP to the observable object
        #             observable.tlp = artifact['tlp']
                    
        #             #Add tags to the observable object
        #             observable.tags = artifact['tags']
                    
        #             #Add dataType to the observable object
        #             observable.data = artifact['data']

        #             #Create observable queue item
        #             observable_dict['action'] = "create_case_observable"
        #             observable_dict['caseid'] = caseid
        #             observable_dict['observable'] = observable
        #             missing_observables_list.append(observable_dict)

        #             #Add it to the queue
        #             thapi_queue(observable_dict)
                    
        #     logger.info('Created %i observables' % observable_counter)
        #     self.report_action = 'updateCase'

        #Placeholder for actions to be handled when a case is created from an offense
        #if self.webhook.isNewQRadarCase():
            logger.info('Case {} has been tagged as QRadar and is just created'.format(self.webhook.data['rootId']))
            
            #Extract the use case id
            #self.webhook.
            
            #Retrieve the use case configuration from the config file
            
            #If boolean search, perform search
            
            #If observable based searched. Enrich case with information from QRadar by firing off the appropriate analyzer(s)
        
        #Close offenses in QRadar
        if self.webhook.isClosedQRadarCase() or self.webhook.isQRadarAlertMarkedAsRead():
            logger.info('Case {} has been marked as resolved'.format(self.webhook.data['object']['id']))
            self.QRadarConnector.closeOffense(self.webhook.offenseId) 
            self.report_action = 'closeOffense'
        
        return self.report_action

class ELKAutomation:
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
    def parse_elk_hooks(self):
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