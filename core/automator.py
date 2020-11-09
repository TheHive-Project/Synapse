import logging
import re
import os
import pytz
from configparser import ConfigParser
from thehive4py.models import CaseTask, Alert

from modules.TheHive.connector import TheHiveConnector

from core.loader import moduleLoader
loaded_modules = moduleLoader("automator")

class Automator():
    def __init__(self, webhook, cfg, automation_config):
        """
            Class constructor

            :return: use case report
            :rtype: API call
        """
        self.logger = logging.getLogger(__name__)
        self.logger.info('Initiating Siem Integration')
        
        self.cfg = cfg
        self.app_dir = os.path.dirname(os.path.abspath(__file__)) + "/.."
        self.automation_config = automation_config
        self.TheHiveConnector = TheHiveConnector(cfg)
        self.webhook = webhook

        if cfg.getboolean('Automation','enable_customer_list', fallback=False):
            self.logger.info('Loading Customer configuration')
            #Load optional customer config
            self.customer_cfg = ConfigParser(converters={'list': lambda x: [i.strip() for i in x.split(';')]})
            self.confPath = self.app_dir + '/conf/customers.conf'
            try:
                self.logger.debug('Loading configuration from %s' % self.confPath)
                self.customer_cfg.read(self.confPath)
                self.customers = self.customer_cfg.sections()
                self.logger.debug('Loaded configuration for %s' % self.customers)
            except Exception as e:
                self.logger.error('%s', __name__, exc_info=True)
    
    def check_automation(self):
        self.logger.info('Start parsing use cases for the SIEM based alerts/cases')
        self.ucTaskId = False
        self.report_action = 'None'
        
        if 'tags' in self.webhook.data['object']:
            self.tags = self.webhook.data['object']['tags']
        #Add tagging to webhooks that are missing tags
        else if 'artifactId' in webhook.data['object'] and self.webhook.isCaseArtifactJob:
            self.logger.debug('Found artifact id {} for webhook {}. Retrieving tags from there'.format(self.webhook.data['details']['rootId'], self.webhook.id))
            self.tags = self.TheHiveConnector.getCaseObservable(self.webhook.data['object']['artifactId'])['tags']
        else:
            self.tags = []
            self.logger.warning("no tags found for webhook {}".format(self.webhook.id))
        self.automation_regexes = self.cfg.get('Automation', 'automation_regexes', fallback=None)
        if not self.automation_regexes:
            self.logger.error("Could not find any regexes to find tags for automation")
            return report_action
        self.automation_ids = self.automation_config['automation_ids']

        #loop through tags to see if there is a use case present
        for tag in self.tags:
            for automation_regex in self.automation_regexes:
                #The tag should match this regex otherwise it is no use case
                try:
                    tag = re.search(automation_regex, tag).group(0)
                except:
                    self.logger.info("Tag: %s is not matching the uc regex" % tag)
                    continue
            
                #check if use case that is provided, matches the case
                if tag in self.automation_ids:
                    self.found_a_id = tag

                    ## Try to retrieve the defined actions
                    self.use_case_actions = self.automation_ids[self.found_a_id]['automation']
                    #perform actions defined for the use case
                    for action, action_config in self.use_case_actions.items():
                        self.action_config = action_config
                        #Give automator information regarding the webhook as some actions are limited to the state of the alert/case
                        self.logger.info('Found the following action for %s: %s, with task %s' % (self.found_a_id, action, action_config['task']))
                        
                        #Add support for multiple tasks, loop them 1 by 1
                        if 'tasks' in self.action_config:
                            for task in self.action_config['tasks']:
                                self.action_config['task'] = task

                                #Run actions through the automator
                                if self.Automate(self.action_config, self.webhook):
                                    continue
                                else:
                                    self.logger.info('Did not find any supported actions')
                        #Run actions through the automator
                        else:
                            if self.Automate(self.action_config, self.webhook):
                                continue
                            else:
                                self.logger.info('Did not find any supported actions')
        return self.report_action

    def Automate(self, task_config, webhook):
        
        #Split the task name on the dot to have a module and a function variable in a list
        try:
            self.task = task_config['task'].split(".")
            #Should probably also do some matching for words to mitigate some security concerns?
            module_name = self.task[0]
            function_name = self.task[1]

        except:
            self.logger.error("{} does not seem to be a valid automator task name".format(self.task))
            return
        

        try:
            #Load the Automators class from the module to initialise it
            automators = loaded_modules[module_name].Automators(self.cfg, self.automation_config)
        except KeyError as e:
            self.logger.warning("Automator module not found: {}".format(module_name), exc_info=True)
            return False

        try:
            #Run the function for the task and return the results
            self.results = getattr(automators, '{}'.format(function_name))(task_config, webhook)
            
            #Return the results or True if the task was succesful without returning information
            if self.results:
                return self.results
            else:
                return False
        except KeyError as e:
            self.logger.warning("Automator task not found for {}: {}".format(module_name, function_name), exc_info=True)
            return False