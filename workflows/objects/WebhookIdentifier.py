#!/usr/bin/env python3
# -*- coding: utf8 -*-

import logging
from .TheHiveConnector import TheHiveConnector

class Webhook:
    'Webhook class to identify where the webhook comes from, usual case, QRadar, etc..'

    def __init__(self, webhookData, cfg):
        """
            Class constructor

            :param cfg: Synapse's config
            :type cfg: ConfigParser

            :param webhookData: the json webhook from TheHive
            :type webhookData: dict

            :return: Object Webhook
            :rtype: Webhook
        """

        self.logger = logging.getLogger('workflows.' + __name__)
        self.data = webhookData
        self.theHiveConnector = TheHiveConnector(cfg)
        #if the webhook is related to a QRadar offense, the offenseid will be in
        #this attribute
        self.offenseId = ''

    def isAlert(self):
        """
            Check if the webhook describes an alert

            :return: True if it is an alert, False if not
            :rtype: boolean
        """

        self.logger.info('%s.isAlert starts', __name__)

        if self.data['objectType'] == 'alert':
            return True
        else:
            return False

    def isCase(self):
        """
            Check if the webhook describes a case

            :return: True if it is a case, False if not
            :rtype: boolean
        """

        self.logger.info('%s.isCase starts', __name__)

        if self.data['objectType'] == 'case':
            return True
        else:
            return False

    def isUpdate(self):
        """
            Check if the webhook describes an update

            :return: True if it is an update, False if not
            :rtype: boolean
        """

        self.logger.info('%s.isUpdate starts', __name__)

        if self.data['operation'] == 'Update':
            return True
        else:
            return False

    def isMarkedAsRead(self):
        """
            Check if the webhook describes an marked as read alert

            :return: True if it is marked as read, False if not
            :rtype: boolean
        """

        self.logger.info('%s.isMarkedAsRead starts', __name__)

        try:
            if self.data['details']['status'] == 'Ignored':
                return True
            else:
                return False
        except KeyError:
            #when the alert is ignored (ignore new updates), the webhook does
            #not have the status key, this exception handles that
            return False

    def isClosed(self):
        """
            Check if the webhook describes a closing event
            if it returns false, it doesn't mean that the case is open
            if a case is already closed, and a user update something
            the webhook will not describe a closing event but an update

            :return: True if it is a closing event, False if not
            :rtype: boolean
        """

        self.logger.info('%s.isClosed starts', __name__)

        try:
            if self.data['details']['status'] == 'Resolved':
                return True
            else:
                return False
        except KeyError:
            #happens when the case is already closed
            #and user updates the case with a custom field (for example)
            # then status key is not included in the webhook
            return False

    def isQRadarAlertMarkedAsRead(self):
        """
            Check if the webhook describes a QRadar alert marked as read
            "store" the offenseId in the webhook attribute "offenseId"
    
            :return: True if it is a QRadar alert marked as read, False if not
            :rtype: boolean
        """
    
        self.logger.info('%s.isQRadarAlertMarkedAsRead starts', __name__)
    
        if (self.isAlert() and self.isMarkedAsRead()):
            #the value 'QRadar_Offenses' is hardcoded at creation by
            #workflow QRadar2alert
            if self.data['object']['source'] == 'QRadar_Offenses':
                self.offenseId = self.data['object']['sourceRef']
                return True
        return False
    
    def isClosedQRadarCase(self):
        """
            Check if the webhook describes a closing QRadar case,
            if the case has been opened from a QRadar alert
            returns True
            "store" the offenseId in the webhook attribute "offenseId"
    
            :return: True if it is a QRadar alert marked as read, False if not
            :rtype: boolean
        """
    
        self.logger.info('%s.isClosedQRadarCase starts', __name__)
    
        try:
            if self.isCase() and self.isClosed():
                #searching in alerts if the case comes from a QRadar alert
                esCaseId = self.data['objectId']
                query = dict()
                query['case'] = esCaseId
                results = self.theHiveConnector.findAlert(query)
    
                if len(results) == 1:
                #should only have one hit
                    if results[0]['source'] == 'QRadar_Offenses':
                        #case opened from alert
                        #and from QRadar
                        self.offenseId = results[0]['sourceRef']
                        return True
                    else:
                        #case opened from an alert but
                        #not from QRadar
                        return False
                else:
                    #case not opened from an alert
                    return False
            else:
                #not a case or have not been closed when
                #when the webhook has been issued
                #(might be open or already closed)
                return False
    
        except Exception as e:
            self.logger.error('%s.isClosedQRadarCase failed', __name__, exc_info=True)
            raise
