import importlib
import logging
import os
import re
from datetime import datetime, timezone
import pytz
import requests
import json
from jinja2 import Template
from datetime import datetime, timedelta
from configparser import ConfigParser
from thehive4py.models import CaseTask, Alert

from modules.TheHive.connector import TheHiveConnector
from modules.Cortex.connector import CortexConnector
from modules.QRadar.connector import QRadarConnector

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
        if self.cfg.getboolean('QRadar','enabled'):
            self.QRadarConnector = QRadarConnector(cfg)
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
        
    def MatchValueAgainstTags(self, tags, list):
        #loop through tags to see if there is a recipient present
        for tag in tags:
            if tag in list:
                return tag

    def fetchValueFromDescription(self, webhook, variable):
        self.value_regex = '\|\s*\*\*%s\*\*\s*\|\s*(.*?)\s*\|' % variable
        
        try:
            #The tag should match this regex to find the value
            value = re.search(self.value_regex, webhook.data['object']['description']).group(1)
            return value
        except:
            return False
            
    def parseTimeOffset(self, time, format, offset):
        self.start_time_parsed = datetime.strptime(time, format)
        self.start_time_parsed = self.start_time_parsed - timedelta(minutes=offset)
        self.logger.debug("Time with offset: %s" % self.start_time_parsed.strftime(format))
        return self.start_time_parsed.strftime(format)

    def craftUcTask(self, title, description):
        self.logger.debug('%s.craftUcTask starts', __name__)

        uc_task = CaseTask(title=title,
            description=description)
        
        return uc_task
    
    def craftDescription(self, settings, body, tags, case_description, customer_id, notification_type):
        self.logger.info('%s.craftDescription starts', __name__)
        self.case_description = case_description
        self.body = body
        self.description = ""
        self.stopsend = False

        #Retrieve variables from the mail template
        self.logger.info('Templating the following body: %s' % self.body)
        self.mt_regex = u"\{(.*?)\}"
        self.template_vars = re.findall(self.mt_regex, self.body)
        self.logger.info('Found the following variables: %s' % self.template_vars)
        #Find and replace all variables in the description body of the case
        for template_var in self.template_vars:
            self.desc_regex = u"\|\*\*%s\*\*\| ?(.*?)\|" % template_var
            self.replacement_object = re.search(self.desc_regex, self.case_description)
            try:
                self.replacement_var = self.replacement_object.group(1)
                #Need to escape the curly brackets, for regex purposes
                self.template_var = "{" + template_var + "}"
                #Parse the timestamp to a reasonable format
                if template_var == self.use_case_config['configuration']['event_start_time']:
                    try:
                        self.logger.debug("Changing timestamp %s" % self.replacement_var)
                        timestamp = datetime.strptime(self.replacement_var, self.use_case_config['configuration']['event_start_time_format'])
                        #convert to local time
                        local_timestamp = utc_to_local(timestamp)
                        self.replacement_var = local_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                        self.logger.debug("Changed timestamp to %s" % self.replacement_var)
                    except Exception as e:
                        self.logger.error("Could not change timestamp: %s" % template_var, exc_info=True)
                #replace the variables with the found value
                self.logger.info('Replacing %s with %s' % (template_var, self.replacement_var))
                #self.body = re.sub(self.template_var, self.replacement_var, self.body)
                self.body = self.body.replace(self.template_var, self.replacement_var)
            except Exception as e:
                self.logger.warning("Could not match the regex for %s in the case_description" % template_var, exc_info=True)
                self.stopsend = True

        #loop through tags to see if there is a recipient present
        if customer_id and notification_type == 'email':
            self.logger.info('Found customer %s, retrieving recipient' % customer_id)
            self.description = 'mailto:%s\n' % self.customer_cfg.get(customer_id, 'recipient')
        if not customer_id and notification_type == 'email':
            self.logger.warning('Could not find customer in tags, using default template')
            self.description = 'mailto:{recipient}\n'
            self.stopsend = True
        
        if notification_type == "email": 
            if 'header' in settings:
                self.description += '%s \n\n' % settings['header']
            
            #Add the body
            self.description += '%s \n' % self.body

            if 'footer' in settings:
                self.description += '%s \n' % settings['footer']

            if 'sender_name' in settings:
                self.description += '%s' % settings['sender_name']

        else:
            #Add the body
            self.description += '%s \n' % self.body
        
        return self.description
    
    def checkSiem(self, action_config, search_type):
        #Need to check for joining the code below as 90% is equal
        if search_type == "search_query":
            self.search_query_variables = {}
            #Prepare search queries for searches
            for search_query_name, search_query_config in action_config['search_queries'].items():
                try:
                    self.logger.info('Found the following search queries for %s: %s' % (self.rule_id, search_query_name))
                    
                    #Gather variable for input fields
                    self.search_query_variables[search_query_name] = {} 
                    self.search_query_variables['input'] = {}
                    for input_item in search_query_config['input']:
                        self.search_query_variables['input'][input_item] = self.fetchValueFromDescription(self.webhook,input_item)
                        if not self.search_query_variables['input'][input_item]:
                            self.logger.warning("Could not find input value '%s' for search query" % input_item) 
                            raise GetOutOfLoop
                    
                    #Parse Start Time and optional offset
                    self.start_time = self.fetchValueFromDescription(self.webhook,self.use_case_config['configuration']['event_start_time'])
                    if not self.start_time:
                        self.logger.warning("Could not find Start Time value ")
                        raise GetOutOfLoop
                    self.logger.debug("Found Start Time: %s" % self.start_time)
                    if 'start_time_offset' in search_query_config:
                        self.search_query_variables['input'][self.use_case_config['configuration']['event_start_time']] = self.parseTimeOffset(self.start_time, self.use_case_config['configuration']['event_start_time_format'], search_query_config['start_time_offset'])
                    else:
                        self.search_query_variables['input'][self.use_case_config['configuration']['event_start_time']] = self.start_time
                        
                    if 'stop_time_offset' in search_query_config:
                        self.search_query_variables['input']['Stop Time'] = self.parseTimeOffset(self.start_time, self.use_case_config['configuration']['event_start_time_format'], search_query_config['stop_time_offset'])
                    else:
                        self.search_query_variables['input']['Stop Time'] = datetime.now().strftime(self.use_case_config['configuration']['event_start_time_format'])
                    
                    #Render query
                    try:
                        self.template = Template(search_query_config['query'])
                        self.search_query_variables[search_query_name]['query'] = self.template.render(v=self.search_query_variables['input'])
                        self.logger.debug("Rendered the following query: %s" % self.search_query_variables[search_query_name]['query'])
                    except Exception as e:
                        self.logger.warning("Could not render query due to missing variables")
                        raise GetOutOfLoop
                    
                    #Perform search queries
                    try:
                        self.search_query_variables[search_query_name]['result'] = self.QRadarConnector.aqlSearch(self.search_query_variables[search_query_name]['query'])
                    except Exception as e:
                        self.logger.warning("Could not perform query")
                        raise GetOutOfLoop
                
                    #Check results
                    self.logger.debug('The search result returned the following information: \n %s' % self.search_query_variables[search_query_name]['result'])
                    
                    #Task name
                    self.uc_task_title = search_query_config['task_title']
                
                    self.uc_task_description = "The following information is found. Investigate the results and act accordingly:\n\n\n\n"
                    
                    #create a table header
                    self.table_header = "|" 
                    self.rows = "|"
                    if len(self.search_query_variables[search_query_name]['result']['events']) != 0:
                        for key in self.search_query_variables[search_query_name]['result']['events'][0].keys():
                            self.table_header = self.table_header + " %s |" % key
                            self.rows = self.rows + "---|"
                        self.table_header = self.table_header + "\n" + self.rows + "\n"
                        self.uc_task_description = self.uc_task_description + self.table_header
                        
                        #Create the data table for the results
                        for event in self.search_query_variables[search_query_name]['result']['events']:
                            self.table_data_row = "|" 
                            for field_key, field_value in event.items():
                                # Escape pipe signs
                                if field_value:
                                    field_value = field_value.replace("|", "&#124;")
                                # Use &nbsp; to create some additional spacing
                                self.table_data_row = self.table_data_row + " %s &nbsp;|" % field_value
                            self.table_data_row = self.table_data_row + "\n"
                            self.uc_task_description = self.uc_task_description + self.table_data_row
                    else: 
                        self.uc_task_description = self.uc_task_description + "No results \n"
                        
                    
                    #Add the case task
                    self.uc_task = self.craftUcTask(self.uc_task_title, self.uc_task_description)
                    self.TheHiveConnector.createTask(self.case_id, self.uc_task)

                except GetOutOfLoop:
                    pass
                    
            return True
        
        elif search_type == "enrichment_query":
            self.enrichment_query_variables = {}
            #Prepare search queries for enrichment
            for enrichment_query_name, enrichment_query_config in action_config['enrichment_queries'].items():
                try:
                    self.logger.info('Found the following enrichment queries for %s: %s' % (self.rule_id, enrichment_query_name))
                    
                    #Gather variables
                    self.enrichment_query_variables[enrichment_query_name] = {}
                    self.enrichment_query_variables['input'] = {}
                    
                    #Create template variable for input fields
                    for input_item in enrichment_query_config['input']:
                        #Retrieve value from description
                        self.enrichment_query_variables['input'][input_item] = self.fetchValueFromDescription(self.webhook,input_item)
                        if not self.enrichment_query_variables['input'][input_item]:
                            self.logger.warning("Could not find input value '%s' for enrichment query" % input_item) 
                            raise GetOutOfLoop
                    
                    #Parse Start Time and optional offsets
                    self.start_time = self.fetchValueFromDescription(self.webhook,self.use_case_config['configuration']['event_start_time'])
                    if not self.start_time:    
                        self.logger.warning("Could not find Start Time value ")
                        raise GetOutOfLoop
                    self.logger.debug("Found Start Time: %s" % self.start_time)
                    if 'start_time_offset' in enrichment_query_config:
                        self.enrichment_query_variables['input'][self.use_case_config['configuration']['event_start_time']] = self.parseTimeOffset(self.start_time, self.use_case_config['configuration']['event_start_time_format'], search_query_config['start_time_offset'])
                    else:
                        self.enrichment_query_variables['input'][self.use_case_config['configuration']['event_start_time']] = self.start_time
                    
                    if 'stop_time_offset' in enrichment_query_config:
                        self.enrichment_query_variables['input']['Stop Time'] = self.parseTimeOffset(self.start_time, self.use_case_config['configuration']['event_start_time_format'], search_query_config['stop_time_offset'])
                    else:
                        self.enrichment_query_variables['input']['Stop Time'] = datetime.now().timestamp()
                    
                    #Render query
                    try:
                        self.template = Template(enrichment_query_config['query'])
                        self.enrichment_query_variables[enrichment_query_name]['query'] = self.template.render(v=self.enrichment_query_variables['input'])
                        self.logger.debug("Rendered the following query: %s" % self.enrichment_query_variables[enrichment_query_name]['query'])
                    except Exception as e:
                        self.logger.warning("Could not render query due to missing variables")
                        raise GetOutOfLoop
                
                    #Perform enrichment queries
                    try:
                        self.enrichment_query_variables[enrichment_query_name]['result'] = self.QRadarConnector.aqlSearch(self.enrichment_query_variables[enrichment_query_name]['query'])['events'][0]['result']
                        self.logger.debug("Found result for %s: %s" % (enrichment_query_name, self.enrichment_query_variables[enrichment_query_name]['result']))
                    except Exception as e:
                        self.logger.warning("Could not perform query")
                        raise GetOutOfLoop
                    
                    #Add results to description
                    try:
                        if not self.fetchValueFromDescription(self.webhook,enrichment_query_name) == self.enrichment_query_variables[enrichment_query_name]['result']:
                            self.regex_end_of_table = ' \|\\n\\n\\n'
                            self.end_of_table = ' |\n\n\n'
                            self.replacement_description = '|\n | **%s**  | %s %s' % (enrichment_query_name, self.enrichment_query_variables[enrichment_query_name]['result'], self.end_of_table)
                            self.alert_description=re.sub(self.regex_end_of_table, self.replacement_description, self.alert_description)
                    except Exception as e:
                        self.logger.warning("Could not add results from the query to the description")
                        raise GetOutOfLoop
                        
                except GetOutOfLoop:
                    pass
                
            #Update Alert with the new description field
            self.updated_alert = Alert
            self.updated_alert.description = self.alert_description
            self.TheHiveConnector.updateAlert(self.alert_id, self.updated_alert, ["description"])
                
            return True
            
        else:
            return False
    
    def check_use_case(self):
        self.logger.info('Start parsing use cases for the SIEM based alerts/cases')
        self.ucTaskId = False
        self.report_action = 'None'
        if self.webhook.isImportedAlert():
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
                        action_type = action_config['type']
                        self.logger.info('Found the following action for %s: %s, with type %s' % (self.rule_id, action, action_type))
                        self.case_id = self.webhook.data['object']['case']
                        
                        #Run actions through the automator
                        if self.Automate(action_type, action_config, self.webhook.data):
                            continue

                        #Perform actions for the checkSiem action
                        if action_type == "checkSiem":
                            if self.checkSiem(action_config, "search_query"):
                                self.report_action = 'updateCase'
                            
                        elif action_type == "CreateMailTask":
                            self.customer_id = self.MatchValueAgainstTags(self.tags, self.customers)
                            self.logger.info('Found customer %s, retrieving recipient' % self.customer_id)
                            self.notification_type = "email"
                            self.case_description = self.webhook.data['object']['description']
                            self.title = action_config['title']
                            self.description = self.craftDescription(self.mailsettings, action_config['long_template'], self.tags, self.case_description, self.customer_id, self.notification_type)

                            self.logger.info('Found mail task to create: %s' % self.title)

                            #Create Task
                            self.ucTask = self.craftUcTask(self.title, self.description)
                            self.ucTaskId = self.TheHiveConnector.createTask(id, self.ucTask)
                            if action_config['auto_send_mail'] and not self.stopsend:
                                self.logger.info('Sending mail for task with id: %s' % self.ucTaskId)
                                self.TheHiveConnector.runResponder('case_task', self.ucTaskId, self.use_case_config['configuration']['mail']['responder_id'])
                        else:
                            self.logger.info('Did not find any supported actions')

                else:
                    self.logger.info('Did not find any matching use cases for %s' % tag)
        
        #Using isQRadarAlertUpdateFollowTrue as a hack to force the enrichment of an alert
        if self.webhook.isNewAlert() or self.webhook.isQRadarAlertUpdateFollowTrue():
            self.alert_id = self.webhook.data['object']['id']
            self.alert_description = self.webhook.data['object']['description']
            self.tags = self.webhook.data['object']['tags']
            self.uc_regex = self.use_case_config['configuration']['uc_regex']
            self.use_cases = self.use_case_config['use_cases']
            self.alert_updated = False

            #loop through tags to see if there is a use case present
            for tag in self.tags:
                #The tag should match this regex otherwise it is no use case
                try:
                    tag = re.search(self.uc_regex, tag).group(0)
                    self.logger.info("Tag: %s is matching the uc regex" % tag)
                except:
                    self.logger.debug("Tag: %s is not matching the uc regex" % tag)
                    continue
                
                #check if use case that is provided, matches the case
                if tag in self.use_cases:
                    self.rule_id = tag

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

    def Automate(self, task, task_config, webhook_data):

        #Split the task name on the dot to have a module and a function variable in a list
        try:
            self.task = task.split(".")
            #Should probably also do some matching for words to mitigate some security concerns?
            module_name = self.task[0]
            function_name = self.task[1]

        except:
            self.logger.error("{} does not seem to be a valid automator task name".format(task))
            return
        

        try:
            #Load the Automators class from the module to initialise it
            automators = loaded_modules[module_name].Automators(self.cfg)
        except KeyError as e:
            self.logger.warning("Automation module not found: {}".format(module_name), exc_info=True)
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
            self.logger.warning("Automation Task not found for {}: {}".format(module_name, function_name), exc_info=True)
            return False