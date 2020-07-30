#!/usr/bin/env python3
# -*- coding: utf8 -*-

import os, sys
import logging
import automation.Siem as Siem
from modules.generic.WebhookIdentifier import Webhook
from automation.Automation import *

def manageWebhook(webhookData, cfg, use_cases):
    """
        Filter webhooks received from TheHive and initiate actions like:
            - closing offense in QRadar
    """
    logger = logging.getLogger('workflows')
    logger.info('%s.ManageWebhook starts', __name__)

    report = dict()
    report_action = False
    
    #Dump webhook when debug logging is enabled
    logger.debug('raw json: %s' % webhookData)
    
    webhook = Webhook(webhookData, cfg)    
    
    if cfg.getboolean('api', 'debug_mode'):
        logger.info('Enabling Debug logging')
    
    if cfg.getboolean('QRadar', 'enabled'):
        logger.info('Enabling QRadar Automation')
        qr_automation = QRadarAutomation(webhook, cfg)
        report_action = qr_automation.parse_qradar_hooks()

    if cfg.getboolean('ELK', 'enabled'):
        logger.info('Enabling ELK Automation')
        elk_automation = ELKAutomation(webhook, cfg)
        report_action = elk_automation.parse_elk_hooks()
            
    if cfg.getboolean('MISP', 'enabled'):
        logger.info('Enabling MISP Automation')
        misp_automation = MISPAutomation(webhook, cfg)
        report_action = misp_automation.parse_misp_hooks()
        
    if cfg.getboolean('UCAutomation', 'enabled'):
        logger.info('Enabling Use Case Automation')
        uc_automation = Siem.Siem(webhook, cfg, use_cases)
        report_action = uc_automation.check_use_case()

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
