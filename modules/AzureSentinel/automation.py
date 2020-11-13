import json
import requests
import time
import logging
from datetime import date

from modules.TheHive.connector import TheHiveConnector
from modules.Cortex.connector import CortexConnector
from modules.AzureSentinel.connector import AzureSentinelConnector

# Load required object models
from thehive4py.models import Case, CustomFieldHelper, CaseObservable, CaseTask

logger = logging.getLogger(__name__)

current_time = 0

# When no condition is match, the default action is None
report_action = 'None'

class Automation():

    def __init__(self, webhook, cfg):
        logger.info('Initiating AzureSentinel Automation')
        self.TheHiveConnector = TheHiveConnector(cfg)
        self.AzureSentinelConnector = AzureSentinelConnector(cfg)
        self.webhook = webhook
        self.cfg = cfg
        self.report_action = report_action

    def parse_hooks(self):
        # Close incidents in Azure Sentinel
        if self.webhook.isClosedAzureSentinelCase or self.webhook.isDeletedAzureSentinelCase():
            if self.webhook.data['operation'] == 'Delete':
                self.case_id = self.webhook.data['objectId']
            else:
                self.case_id = self.webhook.data['object']['id']
            logger.info('Case {} has been marked as resolved'.format(self.case_id))
            self.AzureSentinelConnector.closeIncident(self.webhook.incidentId)
            self.report_action = 'closeIncident'

        return self.report_action
