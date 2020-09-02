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
        self.root_id = self.webhook.data['rootId']

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
        try:
            self.tags = self.webhook.data['object']['tags']
        except:
            self.tags = []
            self.logger.warning("no tags found for webhook {}".format(self.webhook.data['rootId']))
        self.automation_regexes = self.cfg.get('Automation', 'automation_regexes')
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
                        self.logger.info('Found the following action for %s: %s, with type %s' % (self.found_a_id, action, action_config['type']))
                        
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

class Main():
    def __init__(self, cfg, use_case_config):
        self.logger = logging.getLogger(__name__)

    def checkCustomerId(self):
        if 'internal' in self.use_cases[self.rule_id] and self.use_cases[self.rule_id]['internal']:
            self.logger.info("Rule %s is marked as internal" % self.rule_id)
            self.results = self.use_case_config['configuration']['internal_contact']
        elif 'debug' in self.use_cases[self.rule_id] and self.use_cases[self.rule_id]['debug']:
            self.logger.info("Using debug settings for rule %s" % self.rule_id)
            self.results = self.use_case_config['configuration']['debug_contact']
        else:
            self.results = self.MatchValueAgainstTags(self.tags, self.customers)
            
        return self.results

    def renderTemplate(self, body, tags, webhook, notification_type, **kwargs):
        self.logger.info('%s.renderTemplate starts', __name__)
        self.body = body
        self.rendered_template = ""
        self.stopsend = False
        self.customer_id = kwargs.get('customer_id', None)
        self.mail_settings = kwargs.get('mail_settings', None)

        #Retrieve variables from the mail template
        self.logger.info('Templating the following body: %s' % self.body)
        self.template = Template(self.body)

        #Find variables in the template
        self.template_env = Environment()
        self.template_parsed = self.template_env.parse(self.body)
        #Grab all the variales from the template and try to find them in the rendered_template
        self.template_vars = meta.find_undeclared_variables(self.template_parsed)
        self.logger.debug("Found the following variables in template: {}".format(self.template_vars))

        #Define the templating dict
        self.template_variables = {}

        for template_var in self.template_vars:
            self.logger.debug("Looking up variable required for template: {}".format(template_var))
            #Replace the underscore from the variable name to a white space as this is used in the rendered_template table
            self.template_var_with_ws = template_var.replace("_", " ")
            self.template_variables[template_var] = self.fetchValueFromDescription(webhook,self.template_var_with_ws)
            #Parse the timestamp to a reasonable format
            if template_var == 'Start_Time':
                try:
                    self.logger.debug("Changing timestamp %s" % self.replacement_var)
                    timestamp = datetime.strptime(self.template_variables[template_var], self.cfg.get('Automation', 'event_start_time_format'))
                    #convert to local time
                    local_timestamp = utc_to_local(timestamp)
                    self.template_variables[template_var] = local_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    self.logger.debug("Changed timestamp to %s" % self.template_variables[template_var])
                except Exception as e:
                    self.logger.error("Could not change timestamp: %s" % template_var, exc_info=True)

        #Render the template
        self.body = self.template.render(self.template_variables)

        #loop through tags to see if there is a recipient present
        if self.customer_id and notification_type == 'email':
            self.logger.info('Found customer %s, retrieving recipient' % self.customer_id)
            self.rendered_template = 'mailto:%s\n' % self.customer_cfg.get(self.customer_id, 'recipient')
        if not self.customer_id and notification_type == 'email':
            self.logger.warning('Could not find customer in tags, using default template')
            self.rendered_template = 'mailto:{recipient}\n'
            self.stopsend = True
        
        if notification_type == "email": 
            if 'header' in self.mail_settings:
                self.rendered_template += '%s \n\n' % self.mail_settings['header']
            
            #Add the body
            self.rendered_template += '%s \n' % self.body

            if 'footer' in self.mail_settings:
                self.rendered_template += '%s \n' % self.mail_settings['footer']

            if 'sender_name' in self.mail_settings:
                self.rendered_template += '%s' % self.mail_settings['sender_name']

        else:
            #Add the body
            self.rendered_template += '%s \n' % self.body
        
        return self.rendered_template