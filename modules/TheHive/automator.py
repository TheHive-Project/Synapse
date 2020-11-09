import logging
import requests
import json
import re
import ipaddress
import time

from core.modules import Main
from modules.TheHive.connector import TheHiveConnector
from modules.Cortex.connector import CortexConnector
from thehive4py.models import CaseTask, Case

class Automators(Main):
    def __init__(self, cfg, use_case_config):
        self.logger = logging.getLogger(__name__)
        self.logger.info('Initiating The Hive Automator')

        self.cfg = cfg
        self.TheHiveConnector = TheHiveConnector(cfg)
        if self.cfg.getboolean('Cortex', 'enabled'):
            self.CortexConnector = CortexConnector(cfg)

        #Read mail config
        self.mailsettings = self.cfg.get('TheHive', 'mail')

    '''
    Can be used to check if there is a match between tags and the provided list.
    Useful for checking if there is a customer tag (having a list of customers) present where only one can match.
    '''    
    def MatchValueAgainstTags(self, tags, list):
        for tag in tags:
            if tag in list:
                return tag
    
    def craftUcTask(self, title, description):
        self.logger.debug('%s.craftUcTask starts', __name__)

        self.uc_task = CaseTask(title=title,
            description=description)
        
        return self.uc_task

    def createBasicTask(self, action_config, webhook):
        #Only continue if the right webhook is triggered
        if webhook.isImportedAlert():
            pass
        else:
            return False

        #Perform actions for the CreateBasicTask action
        self.case_id = webhook.data['object']['case']
        self.title = action_config['title']
        self.description = action_config['description']

        self.logger.info('Found basic task to create: %s' % self.title)

        #Create Task
        self.uc_task = self.craftUcTask(self.title, self.description)
        self.uc_task_id = self.TheHiveConnector.createTask(self.case_id, self.uc_task)

        return True

    def createMailTask(self, action_config, webhook):
        #Only continue if the right webhook is triggered
        if webhook.isImportedAlert():
            pass
        else:
            return False
        
        self.tags = webhook.data['object']['tags']
        self.case_id = webhook.data['object']['case']
        if self.cfg.getboolean('Automation','enable_customer_list', fallback=False):
            self.customer_id = self.MatchValueAgainstTags(self.tags, self.customers)
            self.logger.info('Found customer %s, retrieving recipient' % self.customer_id)
        else:
            self.customer_id = None
        self.notification_type = "email"
        self.title = action_config['title']
        self.description = self.renderTemplate(action_config['long_template'], self.tags, webhook, self.notification_type, customer_id=self.customer_id, mail_settings=self.mailsettings)

        self.logger.info('Found mail task to create: %s' % self.title)

        #Create Task
        self.ucTask = self.craftUcTask(self.title, self.description)
        self.ucTaskId = self.TheHiveConnector.createTask(self.case_id, self.ucTask)
        if 'auto_send_mail' in action_config and action_config['auto_send_mail'] and not self.stopsend:
            self.logger.info('Sending mail for task with id: %s' % self.ucTaskId)
            self.TheHiveConnector.runResponder('case_task', self.ucTaskId, self.use_case_config['configuration']['mail']['responder_id'])

    def runAnalyzer(self, action_config, webhook):
        #Automatically run Analyzers for newly created cases where supported IOC's are present
        if webhook.isNewArtifact():
            self.logger.debug('Case artifact found. Checking if observable is of a supported type to automatically fire the analyzer')
            
            #Retrieve caseid
            self.caseid = webhook.data['rootId']
            
            #List all supported ioc's for the case
            self.observable = webhook.data['object']
            
            #When supported, start a cortex analyzer for it
            if self.observable['dataType'] in action_config['datatypes']:
                self.supported_observable = self.observable['_id']
            
                #Blacklist IP addresses, make sure the blacklist is present
                if self.observable['dataType'] == "ip" and 'blacklist' in action_config and 'ip' in action_config['blacklist']:
                    for entry in action_config['blacklist']['ip']:
                        #Initial values
                        match = False
                        observable_ip = ipaddress.ip_address(self.observable['data'])

                        #Match ip with CIDR syntax
                        if entry[-3:] == "/32":
                            bl_entry = ipaddress.ip_address(entry[:-3])
                            match = observable_ip == bl_entry
                        #Match ip without CIDR syntax
                        elif "/" not in entry:
                            bl_entry = ipaddress.ip_address(entry)
                            match = observable_ip == bl_entry
                        #Capture actual network entries
                        else:
                            bl_entry = ipaddress.ip_network(entry, strict=False)
                            match = observable_ip in bl_entry

                        #If matched add it to new entries to use outside of the loop
                        if match:
                            self.logger.debug("Observable {} has matched {} of blacklist. Ignoring...".format(self.observable['data'], entry))
                            return
                        

                #Trigger a search for the supported ioc
                self.logger.debug('Launching analyzers for observable: {}'.format(self.observable['_id']))
                self.TheHiveConnector.runAnalyzer(action_config['cortex_instance'], self.supported_observable, action_config['analyzer'])
                

    def closeCaseForTaxonomyInAnalyzerResults(self, action_config, webhook):
        #If the Job result contains a successful search with minimum of 1 hit, create a task to investigate the results
        if webhook.isCaseArtifactJob() and webhook.isSuccess():
            #Case ID
            self.caseid = webhook.data['rootId']
            #Load Case information
            self.case_data = self.TheHiveConnector.getCase(self.caseid)
            
            self.logger.debug('Job {} has just finished'.format(webhook.data['object']['cortexJobId']))
            
            #Check if the result count higher than 0
            if int(float(webhook.data['object']['report']['summary']['taxonomies'][0]['level'])) in action_config["taxonomy_level"]:
                self.logger.info('Job {} has configured taxonomy level, checking if a task is already present for this observable'.format(webhook.data['object']['cortexJobId']))
                #Check if task is present for investigating the new results
                if self.case.status != "Resolved":
                    self.logger.info('Case is not yet closed, closing case for {} now...'.format(webhook.data['object']['cortexJobId']))
                    #Close the case
                    self.TheHiveConnector.closeCase(self.caseid)
        
        self.report_action = 'closeCase'
                    
        return self.report_action

    def createTaskForTaxonomyinAnalyzerResults(self, action_config, webhook):
        #If the Job result contains a successful search with minimum of 1 hit, create a task to investigate the results
        if webhook.isCaseArtifactJob() and webhook.isSuccess():
            #Case ID
            self.caseid = webhook.data['rootId']
            #Load Case information
            self.case_data = self.TheHiveConnector.getCase(self.caseid)
            
            self.logger.debug('Job {} has just finished'.format(webhook.data['object']['cortexJobId']))
            
            #Check if the result count higher than 0
            if webhook.data['object']['report']['summary']['taxonomies'][0]['level'] in action_config["taxonomy_level"]:
                self.logger.info('Job {} has configured taxonomy level, checking if a task is already present for this observable'.format(webhook.data['object']['cortexJobId']))
                #Retrieve case task information
                self.response = self.TheHiveConnector.getCaseTasks(self.caseid)
                self.case_tasks = self.response.json()
                
                #Load CaseTask template
                self.casetask = CaseTask()
                
                #Observable + Link
                self.observable = webhook.data['object']['artifactId']
                self.observable_link = self.cfg.get('TheHive', 'url') + "/index.html#/case/" + self.caseid + "/observables/" + webhook.data['object']['artifactId']
                
                #Task name
                self.casetask.title = "{} {}".format(action_config['title'], self.observable)
                
                #Date
                self.date_found = time.strftime("%d-%m-%Y %H:%M")
                
                self.case_task_found = False
                for case_task in self.case_tasks:
                
                    #Check if task is present for investigating the new results
                    if self.casetask.title == case_task['title']:
                        self.case_task_found = True
                
                if not self.case_task_found:
                    self.logger.info('No task found, creating task for observable found in job {}'.format(webhook.data['object']['cortexJobId']))
                    #Add description
                    self.casetask.description = action['description']
                    self.casetask.description = self.casetask.description + "\n\n {} is seen on {}\n".format(self.observable_link, self.date_found)
                    
                    #Check if case is closed
                    if self.case_data['status'] == "Resolved":
                        #Create a Case object
                        case = Case()
                        
                        #Add the case id to the object
                        case.id = self.caseid
                        
                        self.logger.info('Updating case %s' % case.id)

                        #Define which fields need to get updated
                        fields = ['status']
                        
                        #Reopen the case
                        case.status = "Open"

                        #Update the case
                        self.TheHiveConnector.updateCase(case,fields)
                    
                    #Add the case task
                    self.TheHiveConnector.createTask(self.caseid,self.casetask)
                
                self.report_action = 'createTask'
                return self.report_action