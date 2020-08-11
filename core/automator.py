import logging
import os
from datetime import datetime, timezone, timedelta
import pytz
import requests
import json
from configparser import ConfigParser
from thehive4py.models import CaseTask, Alert

from modules.TheHive.connector import TheHiveConnector
from modules.Cortex.connector import CortexConnector

from core.loader import moduleLoader
loaded_modules = moduleLoader("automator")

#Small timezone converter. Source: https://stackoverflow.com/questions/4563272/convert-a-python-utc-datetime-to-a-local-datetime-using-only-python-standard-lib
def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=pytz.timezone('CET'))

class GetOutOfLoop( Exception ):
    pass

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
        if self.cfg.getboolean('Cortex', 'enabled'):
            self.CortexConnector = CortexConnector(cfg)
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

        if self.use_case_config['configuration']['mail']['enabled']:
            self.logger.info('Loading Mail configuration')
            #Check for mail variables
            self.mailsettings = {}
            self.mailsettings['header'] = self.use_case_config['configuration']['mail']['header']
            self.mailsettings['footer'] = self.use_case_config['configuration']['mail']['footer']
            self.mailsettings['sender_name'] = self.use_case_config['configuration']['mail']['sender_name']
    
    def check_use_case(self):
        self.logger.info('Start parsing use cases for the SIEM based alerts/cases')
        self.ucTaskId = False
        self.report_action = 'None'
        self.tags = self.webhook.data['object']['tags']
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
                    self.action_config['webhook'] == "importedAlert":
                    self.logger.info('Found the following action for %s: %s, with type %s' % (self.rule_id, action, action_type))
                    self.case_id = self.webhook.data['object']['case']
                    
                    #Run actions through the automator
                    if self.Automate(action_config, self.webhook.data):
                        continue
                    else:
                        self.logger.info('Did not find any supported actions')

            else:
                self.logger.info('Did not find any matching use cases for %s' % tag)

                    #Define customer_id
                    if self.cfg.getboolean('UCAutomation','enable_customer_list', fallback=False):
                        if 'internal' in self.use_cases[self.rule_id] and self.use_cases[self.rule_id]['internal']:
                            self.logger.info("Rule %s is marked as internal" % self.rule_id)
                            self.customer_id = self.use_case_config['configuration']['internal_contact']
                        elif 'debug' in self.use_cases[self.rule_id] and self.use_cases[self.rule_id]['debug']:
                            self.logger.info("Using debug settings for rule %s" % self.rule_id)
                            self.customer_id = self.use_case_config['configuration']['debug_contact']
                        else:
                            self.customer_id = self.MatchValueAgainstTags(self.tags, self.customers)

                    ## Try to retrieve the defined actions
                    self.use_case_actions = self.use_cases[self.rule_id]['automation']
                    #perform actions defined for the use case
                    for action, action_config in self.use_case_actions.items():
                        action_type = action_config['type']
                        self.logger.info('Found the following action for %s: %s, with type %s' % (self.rule_id, action, action_type))
                        self.case_id = self.webhook.data['object']['id']

                        #Perform actions for the checkSiem action
                        if action_type == "checkSiem":
                            if self.checkSiem(action_config, "enrichment_query"):
                                self.report_action = 'updateAlert'
                        elif action_type == "SendNotificationFromAlert":
                            self.case_description = self.webhook.data['object']['description']
                            self.title = action_config['title']

                            if "email" in action_config['platforms']:
                                self.notification_type = "email"
                                self.description = self.craftDescription(self.mailsettings, action_config['long_template'], self.tags, self.case_description, self.customer_id, self.notification_type)
                                self.logger.info('Found alert to send mail for: %s' % self.title)

                                self.data = {
                                    "data": {
                                        "description": self.description,
                                        "title": self.title
                                    },
                                    "dataType":"thehive:case_task"
                                }

                                self.logger.info('Sending mail for alert with id: %s' % self.alert_id)
                                self.CortexConnector.runResponder(self.use_case_config['configuration']['mail']['responder_id'], self.data)
                            #Posting to slack
                            if "slack" in action_config['platforms']:
                                #Fallback for notification where no short_template is available
                                if 'short_template' in action_config:
                                    template = action_config['short_template']
                                else:
                                    template = action_config['long_template']

                                self.notification_type = "slack"
                                self.description = self.craftDescription(self.mailsettings, template, self.tags, self.case_description, self.customer_id, self.notification_type)
                                try:
                                    self.slack_url = self.customer_cfg.get(self.customer_id, 'slack_url')
                                except:
                                    self.logger.error("Could not retrieve slack url for customer %s" % self.customer_id)
                                
                                if hasattr(self, 'slack_url'):
                                    self.slack_data = {}
                                    self.slack_data['text'] = "*%s*\n %s" % (self.title, self.description)

                                    try:
                                        self.response = requests.post(self.slack_url, data=json.dumps(self.slack_data), headers={'Content-Type': 'application/json'})
                                        if self.response.status_code not in [200, 201]:
                                            self.logger.error("Something went wrong when posting to slack: %s" % self.response.raw.read())
                                    except Exception as e:
                                        self.logger.error("Could not post alert to Slack", exc_info=True)
                            #Posting to teams
                            if "teams" in action_config['platforms']:
                                #Fallback for notification where no short_template is available
                                if 'short_template' in action_config:
                                    template = action_config['short_template']
                                else:
                                    template = action_config['long_template']

                                self.notification_type = "teams"
                                self.description = self.craftDescription(self.mailsettings, template, self.tags, self.case_description, self.customer_id, self.notification_type)
                                try:
                                    self.teams_url = self.customer_cfg.get(self.customer_id, 'teams_url')
                                except:
                                    self.logger.error("Could not retrieve teams url for customer %s" % self.customer_id)
                                
                                if hasattr(self, 'teams_url'):
                                    self.teams_data = {}
                                    self.teams_data['text'] = "***%s***</br><pre>%s</pre>" % (self.title, self.description)

                                    try:
                                        self.response = requests.post(self.teams_url, data=json.dumps(self.teams_data), headers={'Content-Type': 'application/json'})
                                        if self.response.status_code not in [200, 201]:
                                            self.logger.error("Something went wrong when posting to teams: %s" % self.response.raw.read())
                                    except Exception as e:
                                        self.logger.error("Could not post alert to teams", exc_info=True)
                        else:
                            self.logger.info('Did not find any supported actions')

                else:
                    self.logger.info('Did not find any matching use cases for %s' % tag)

        return self.report_action

    def Automate(self, task_config, webhook_data):

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
            self.results = getattr(automators, '{}'.format(function_name))(task_config, webhook_data)
            
            #Return the results or True if the task was succesful without returning information
            if self.results:
                return self.results
            else:
                return False
        except KeyError as e:
            self.logger.warning("Automator task not found for {}: {}".format(module_name, function_name), exc_info=True)
            return False