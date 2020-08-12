import logging
import requests
import json
import re

from modules.TheHive.connector import TheHiveConnector
from modules.Cortex.connector import CortexConnector
from thehive4py.models import CaseTask

class Automators():
    def __init__(self, cfg, use_case_config):
        self.logger = logging.getLogger(__name__)
        self.logger.info('Initiating The Hive Automators')

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
        
        self.customer_id = self.MatchValueAgainstTags(self.tags, self.customers)
        self.logger.info('Found customer %s, retrieving recipient' % self.customer_id)
        self.notification_type = "email"
        self.case_description = webhook.data['object']['description']
        self.title = action_config['title']
        self.description = self.craftDescription(self.mailsettings, action_config['long_template'], self.tags, self.case_description, self.customer_id, self.notification_type)

        self.logger.info('Found mail task to create: %s' % self.title)

        #Create Task
        self.ucTask = self.craftUcTask(self.title, self.description)
        self.ucTaskId = self.TheHiveConnector.createTask(id, self.ucTask)
        if action_config['auto_send_mail'] and not self.stopsend:
            self.logger.info('Sending mail for task with id: %s' % self.ucTaskId)
            self.TheHiveConnector.runResponder('case_task', self.ucTaskId, self.use_case_config['configuration']['mail']['responder_id'])

    def SendNotificationFromAlert(self, action_config, webhook):
        #Only continue if the right webhook is triggered
        if webhook.isImportedAlert():
            pass
        else:
            return False

        self.case_description = webhook.data['object']['description']
        self.title = action_config['title']

        if self.cfg.getboolean('UCAutomation','enable_customer_list', fallback=False):
            self.customer_id = self.checkCustomerId()

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