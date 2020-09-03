import logging
import re

from core.automator import Main
from modules.Cortex.connector import CortexConnector

class Automators(Main):
    def __init__(self, cfg, use_case_config):
        self.logger = logging.getLogger(__name__)
        self.logger.info('Initiating The Hive Automators')

        self.cfg = cfg
        if self.cfg.getboolean('Cortex', 'enabled'):
            self.CortexConnector = CortexConnector(cfg)

        #Read mail config
        self.mailsettings = self.cfg.get('Cortex', 'mail')

    def SendEmailFromAlert(self, action_config, webhook):
        #Only continue if the right webhook is triggered
        if webhook.isImportedAlert():
            pass
        else:
            return False

        self.tags = webhook.data['object']['tags']
        self.title = action_config['title']

        if self.cfg.getboolean('Automation','enable_customer_list', fallback=False):
            self.customer_id = self.checkCustomerId()
        else:
            self.customer_id = None

        self.notification_type = "email"
        self.rendered_template = self.renderTemplate(action_config['long_template'], self.tags, webhook, self.notification_type, customer_id=self.customer_id, mail_settings=self.mailsettings)
        self.logger.info('Found alert to send mail for: %s' % self.title)

        self.data = {
            "data": {
                "description": self.rendered_template,
                "title": self.title
            },
            "dataType":"thehive:case_task"
        }

        self.logger.info('Sending mail for alert with id: %s' % self.alert_id)
        self.CortexConnector.runResponder(self.use_case_config['configuration']['mail']['responder_id'], self.data)