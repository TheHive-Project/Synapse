import logging
import re
import os
from datetime import datetime, timezone
import pytz
from configparser import ConfigParser
from thehive4py.models import CaseTask, Alert

from modules.TheHive.connector import TheHiveConnector

from core.loader import moduleLoader
loaded_modules = moduleLoader("automator")

#Small timezone converter. Source: https://stackoverflow.com/questions/4563272/convert-a-python-utc-datetime-to-a-local-datetime-using-only-python-standard-lib
def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=pytz.timezone('CET'))

class Automator:
    def __init__(self, webhook, cfg, use_cases):
        """
            Class constructor

            :return: use case report
            :rtype: API call
        """
        self.logger = logging.getLogger(__name__)
        self.logger.info('Initiating Siem Integration')

        self.cfg = cfg
        self.app_dir = os.path.dirname(os.path.abspath(__file__)) + "/.."
        self.use_case_config = use_cases
        self.TheHiveConnector = TheHiveConnector(cfg)
        self.webhook = webhook
        self.root_id = self.webhook.data['rootId']

        if cfg.getboolean('UCAutomation','enable_customer_list', fallback=False):
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
    
    def check_use_case(self):
        self.logger.info('Start parsing use cases for the SIEM based alerts/cases')
        self.ucTaskId = False
        self.report_action = 'None'
        try:
            self.tags = self.webhook.data['object']['tags']
        except:
            self.tags = []
            self.logger.warning("no tags found for webhook {}".format(self.webhook.data['rootId']))
        self.uc_regex = self.use_case_config['configuration']['uc_regex']
        self.use_cases = self.use_case_config['use_cases']

        #loop through tags to see if there is a use case present
        for tag in self.tags:
            #The tag should match this regex otherwise it is no use case
            try:
                tag = re.search(self.uc_regex, tag).group(0)
            except:
                self.logger.info("Tag: %s is not matching the uc regex" % tag)
                continue
            
            #check if use case that is provided, matches the case
            if tag in self.use_cases:
                self.rule_id = tag

                ## Try to retrieve the defined actions
                self.use_case_actions = self.use_cases[self.rule_id]['automation']
                #perform actions defined for the use case
                for action, action_config in self.use_case_actions.items():
                    self.action_config = action_config
                    #Give automator information regarding the webhook as some actions are limited to the state of the alert/case
                    self.logger.info('Found the following action for %s: %s, with type %s' % (self.rule_id, action, action_config['type']))
                    
                    #Run actions through the automator
                    if self.Automate(action_config, self.webhook):
                        continue
                    else:
                        self.logger.info('Did not find any supported actions')

            else:
                self.logger.info('Did not find any matching use cases for %s' % tag)

        return self.report_action

    def Automate(self, task_config, webhook):

        #Split the task name on the dot to have a module and a function variable in a list
        try:
            self.task = task_config['type'].split(".")
            #Should probably also do some matching for words to mitigate some security concerns?
            module_name = self.task[0]
            function_name = self.task[1]

        except:
            self.logger.error("{} does not seem to be a valid automator task name".format(task))
            return
        

        try:
            #Load the Automators class from the module to initialise it
            automators = loaded_modules[module_name].Automators(self.cfg, self.use_case_config)
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