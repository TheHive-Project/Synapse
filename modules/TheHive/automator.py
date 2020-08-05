
import logging
from modules.TheHive.connector import TheHiveConnector
from thehive4py.models import CaseTask

class Automators():
    def __init__(self, cfg):
        self.logger = logging.getLogger(__name__)
        self.logger.info('Initiating The Hive Automation')

        self.cfg = cfg
        self.TheHiveConnector = TheHiveConnector(cfg)
        
    def craftUcTask(self, title, description):
        self.logger.debug('%s.craftUcTask starts', __name__)

        uc_task = CaseTask(title=title,
            description=description)
        
        return uc_task

    def createBasicTask(self, action_config, webhook_data):

        #Perform actions for the CreateBasicTask action
        self.case_id = webhook_data['object']['case']
        self.title = action_config['title']
        self.description = action_config['description']

        self.logger.info('Found basic task to create: %s' % self.title)

        #Create Task
        self.uc_task = self.craftUcTask(self.title, self.description)
        self.uc_task_id = self.TheHiveConnector.createTask(self.case_id, self.uc_task)

        return True