
import logging
from datetime import datetime
from modules.TheHive.connector import TheHiveConnector
from modules.TheHive.automator import Automators as TheHiveAutomators
from modules.QRadar.connector import QRadarConnector
from thehive4py.models import CaseTask
from jinja2 import Template

class GetOutOfLoop( Exception ):
    pass

class Automators():
    def __init__(self, cfg, use_case_config):
        self.logger = logging.getLogger(__name__)
        self.logger.info('Initiating QRadar Automators')

        self.cfg = cfg
        self.use_case_config = use_case_config
        self.TheHiveConnector = TheHiveConnector(cfg)
        self.TheHiveAutomators = TheHiveAutomators(cfg, use_case_config)
        self.QRadarConnector = QRadarConnector(cfg)

    def parseTimeOffset(self, time, format, offset):
        self.start_time_parsed = datetime.strptime(time, format)
        self.start_time_parsed = self.start_time_parsed - timedelta(minutes=offset)
        self.logger.debug("Time with offset: %s" % self.start_time_parsed.strftime(format))
        return self.start_time_parsed.strftime(format)

    def checkSiem(self, action_config, webhook):
        #Only continue if the right webhook is triggered
        if not webhook.isImportedAlert() or webhook.isNewAlert() or webhook.isQRadarAlertUpdateFollowTrue():
            return False
        
        #Define variables and actions based on certain webhook types
        #Alerts
        if webhook.isNewAlert() or webhook.isQRadarAlertUpdateFollowTrue():
            self.alert_id = webhook.data['object']['id']
            self.alert_description = webhook.data['object']['description']
            self.supported_query_type = 'enrichment_queries'

        #Cases
        elif webhook.isImportedAlert():
            self.case_id = webhook.data['object']['case']
            self.supported_query_type = 'search_queries'


        self.query_variables = {}
        #Prepare search queries for searches
        for query_name, query_config in action_config[self.supported_query_type].items():
            try:
                self.logger.info('Found the following search query: %s' % (query_name))
                
                #Parse Start Time and optional offset
                self.start_time = self.TheHiveAutomators.fetchValueFromDescription(webhook.data,self.use_case_config['configuration']['event_start_time'])
                if not self.start_time:
                    self.logger.warning("Could not find Start Time value ")
                    raise GetOutOfLoop
                self.logger.debug("Found Start Time: %s" % self.start_time)
                if 'start_time_offset' in query_config:
                    self.query_variables['input'][self.use_case_config['configuration']['event_start_time']] = self.parseTimeOffset(self.start_time, self.use_case_config['configuration']['event_start_time_format'], query_config['start_time_offset'])
                else:
                    self.query_variables['input'][self.use_case_config['configuration']['event_start_time']] = self.start_time
                    
                if 'stop_time_offset' in query_config:
                    self.query_variables['input']['Stop Time'] = self.parseTimeOffset(self.start_time, self.use_case_config['configuration']['event_start_time_format'], query_config['stop_time_offset'])
                else:
                    self.query_variables['input']['Stop Time'] = datetime.now().strftime(self.use_case_config['configuration']['event_start_time_format'])
                
                #Render query
                try:
                    self.template = Template(query_config['query'])

                    #Grab all the variales from the template and try to find them in the description
                    template_vars = meta.find_undeclared_variables(template)
                    for template_var in template_vars:
                        self.query_variables['input'][input_item] = self.TheHiveAutomators.fetchValueFromDescription(self.webhook,template_var)

                    self.query_variables[query_name]['query'] = self.template.render(self.query_variables['input'])
                    self.logger.debug("Rendered the following query: %s" % self.query_variables[query_name]['query'])
                except Exception as e:
                    self.logger.warning("Could not render query due to missing variables")
                    raise GetOutOfLoop
                
                #Perform search queries
                try:
                    self.query_variables[query_name]['result'] = self.QRadarConnector.aqlSearch(self.query_variables[query_name]['query'])
                except Exception as e:
                    self.logger.warning("Could not perform query")
                    raise GetOutOfLoop
            
                #Check results
                self.logger.debug('The search result returned the following information: \n %s' % self.query_variables[query_name]['result'])
                    
                if self.supported_query_type == "search_query":
                    #Task name
                    self.uc_task_title = query_config['task_title']
                
                    self.uc_task_description = "The following information is found. Investigate the results and act accordingly:\n\n\n\n"
                    
                    #create a table header
                    self.table_header = "|" 
                    self.rows = "|"
                    if len(self.query_variables[query_name]['result']['events']) != 0:
                        for key in self.query_variables[query_name]['result']['events'][0].keys():
                            self.table_header = self.table_header + " %s |" % key
                            self.rows = self.rows + "---|"
                        self.table_header = self.table_header + "\n" + self.rows + "\n"
                        self.uc_task_description = self.uc_task_description + self.table_header
                        
                        #Create the data table for the results
                        for event in self.query_variables[query_name]['result']['events']:
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

                if self.supported_query_type == "enrichment_query":

                    #Add results to description
                    try:
                        if not self.fetchValueFromDescription(self.webhook,enrichment_query_name) == self.enrichment_query_variables[enrichment_query_name]['result']:
                            self.regex_end_of_table = ' \|\\n\\n\\n'
                            self.end_of_table = ' |\n\n\n'
                            self.replacement_description = '|\n | **%s**  | %s %s' % (enrichment_query_name, self.enrichment_query_variables[enrichment_query_name]['result'], self.end_of_table)
                            self.alert_description=re.sub(self.regex_end_of_table, self.replacement_description, self.alert_description)
                            self.enriched = True
                    except Exception as e:
                        self.logger.warning("Could not add results from the query to the description")
                        raise GetOutOfLoop

            except GetOutOfLoop:
                pass
        
        #Only enrichment queries need to update the alert out of the loop. The search queries will create a task within the loop
        if 'enriched' in self and self.enriched:
            #Update Alert with the new description field
            self.updated_alert = Alert
            self.updated_alert.description = self.alert_description
            self.TheHiveConnector.updateAlert(self.alert_id, self.updated_alert, ["description"])
                
        return True