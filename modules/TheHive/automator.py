import logging
import requests
import json
import re
from jinja2 import Template, Environment, meta

from core.automator import Main
from modules.TheHive.connector import TheHiveConnector
from modules.Cortex.connector import CortexConnector
from thehive4py.models import CaseTask

class Automators(Main):
    def __init__(self, cfg, use_case_config):
        self.logger = logging.getLogger(__name__)
        self.logger.info('Initiating The Hive Automator')

        self.cfg = cfg
        self.TheHiveConnector = TheHiveConnector(cfg)
        if self.cfg.getboolean('Cortex', 'enabled'):
            self.CortexConnector = CortexConnector(cfg)

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

        uc_task = CaseTask(title=title,
            description=description)
        
        return uc_task

    '''
    Can be used to extract values from the alert/case description in a webhook
    '''
    def fetchValueFromDescription(self, webhook, variable):
        self.value_regex = '\|\s*\*\*%s\*\*\s*\|\s*(.*?)\s*\|' % variable
        
        try:
            #The tag should match this regex to find the value
            value = re.search(self.value_regex, webhook.data['object']['description']).group(1)
            self.logger.debug("Found value for template variable {}: {}".format(variable, value))
            return value
        except:
            return False

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
        self.ucTaskId = self.TheHiveConnector.createTask(self.caseid, self.ucTask)
        if 'auto_send_mail' in action_config and action_config['auto_send_mail'] and not self.stopsend:
            self.logger.info('Sending mail for task with id: %s' % self.ucTaskId)
            self.TheHiveConnector.runResponder('case_task', self.ucTaskId, self.use_case_config['configuration']['mail']['responder_id'])