
from modules.TheHive.connector import TheHiveConnector

class Automators():
    def __init__(cfg):
        self.logger = logging.getLogger('workflows')
        self.logger.info('Initiating The Hive Automation')

        self.cfg = cfg
        self.TheHiveConnector = TheHiveConnector(cfg)
        
    def craftUcTask(self, title, description):
        self.logger.debug('%s.craftUcTask starts', __name__)

        uc_task = CaseTask(title=title,
            description=description)
        
        return uc_task

    def createBasicTask(action_config):

        #Perform actions for the CreateBasicTask action

        self.title = action_config['title']
        self.description = action_config['description']

        self.logger.info('Found basic task to create: %s' % self.title)

        #Create Task
        self.uc_task = self.craftUcTask(self.title, self.description)
        self.uc_task_id = self.TheHiveConnector.createTask(self.case_id, self.uc_task)

        return True