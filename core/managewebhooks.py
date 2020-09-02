#!/usr/bin/env python3
# -*- coding: utf8 -*-

import os, sys
import logging
from core.automator import Automator
from core.webhookidentifier import Webhook

#Import automation modules

from core.loader import moduleLoader
loaded_modules = moduleLoader("automation")

def manageWebhook(webhookData, cfg, automation_config):
    """
        Filter webhooks received from TheHive and initiate actions like:
            - closing offense in QRadar
    """
    logger = logging.getLogger(__name__)
    logger.info('%s.ManageWebhook starts', __name__)

    report = dict()
    report_action = False
    
    #Dump webhook when debug logging is enabled
    logger.debug('raw json: %s' % webhookData)
    
    webhook = Webhook(webhookData, cfg)    
    
    #loop through all configured sections and create a mapping for the endpoints
    modules = {}
    for cfg_section in cfg.sections():
        automation_enabled = cfg.getboolean(cfg_section, 'automation_enabled', fallback=False)
        if automation_enabled:
            logger.info("Enabling automation for {}".format(cfg_section))

            try:
                #Load the Automators class from the module to initialise it
                automations = loaded_modules[cfg_section].Automation(webhook, cfg)
            except KeyError as e:
                logger.warning("Automation module not found: {}".format(cfg_section), exc_info=True)
                return False

            #Run the function for the task and return the results
            report_action = automations.parse_hooks()

    if cfg.getboolean('Automation', 'enabled'):
         logger.info('Enabling Use Case Automation')
         uc_automation = Automator(webhook, cfg, automation_config)
         report_action = uc_automation.check_automation()

    #Check if an action is performed for the webhook
    if report_action:
        report['action'] = report_action
        report['success'] = True
    else:
        report['success'] = False
    
    #return the report
    return report

if __name__ == '__main__':
    print('Please run from API only')
