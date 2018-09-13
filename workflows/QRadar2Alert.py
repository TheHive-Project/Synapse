#!/usr/bin/env python3
# -*- coding: utf8 -*-

import os, sys
import logging
import copy

current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = current_dir + '/..'
sys.path.insert(0, current_dir)

from common.common import getConf
from objects.QRadarConnector import QRadarConnector
from objects.TheHiveConnector import TheHiveConnector

def getOffenses(qradarConnector, timerange):
    return qradarConnector.getOffenses(timerange)
    
def getEnrichedOffenses(qradarConnector, timerange):
    enrichedOffenses = []

    for offense in getOffenses(qradarConnector, timerange):
        enrichedOffenses.append(enrichOffense(qradarConnector, offense))

    return enrichedOffenses

def enrichOffense(qradarConnector, offense):
    enriched = copy.deepcopy(offense)

    enriched['offense_type_str'] = \
                qradarConnector.getOffenseTypeStr(offense['offense_type'])

    #adding the first 3 raw logs
    enriched['logs'] = qradarConnector.getOffenseLogs(enriched)

    return enriched

def qradarOffenseToHiveAlert(theHiveConnector, offense):

    def getHiveSeverity(offense):
        #severity in TheHive is either low, medium or high
        #while severity in QRadar is from 1 to 10
        #low will be [1;4] => 1
        #medium will be [5;6] => 2
        #high will be [7;10] => 3
        if offense['severity'] < 5:
            return 1
        elif offense['severity'] < 7:
            return 2
        elif offense['severity'] < 11:
            return 3

        return 1

    #creating the alert
    alert = theHiveConnector.craftAlert(
        offense['description'],
        craftAlertDescription(offense),
        getHiveSeverity(offense),
        offense['start_time'],
        ['QRadar', 'Offense', 'Synapse'],
        2,
        'Imported',
        'internal',
        'QRadar_Offenses',
        str(offense['id']),
        [],
        '')

    return alert


def offense2Alert(timerange):
    """
       Get all openned offense created within the last 
       <timerange> minutes and creates alerts for them in
       TheHive
    """
    logger = logging.getLogger(__name__)
    logger.info('%s.offense2Alert starts', __name__)

    report = dict()
    report['success'] = bool()

    try:
        cfg = getConf()

        qradarConnector = QRadarConnector(cfg)
        theHiveConnector = TheHiveConnector(cfg)

        offensesList = getEnrichedOffenses(qradarConnector, timerange)
        
        #each offenses in the list is represented as a dict
        #we enrich this dict with additional details
        for offense in offensesList:
            #the offense type is an int (when queried through api)
            #which has to be mapped with a string
            theHiveAlert = qradarOffenseToHiveAlert(theHiveConnector, offense)
            esAlertId = theHiveConnector.createAlert(theHiveAlert)
            logger.info('Alert created under ES id: %s', str(esAlertId))

        report['success'] = True
        return report

    except Exception as e:
            # FIXME This should return whether or not QRadar reading or TheHive raising
            # failed.
            logger.error('Failed to create alert from QRadar offense', exc_info=True)
            report['success'] = False
            report['message'] = str(e)
            return report
            
def craftAlertDescription(offense):
    """
        From the offense metadata, crafts a nice description in markdown
        for TheHive
    """
    logger = logging.getLogger(__name__)
    logger.info('craftAlertDescription starts')


    cfg = getConf()
    QRadarIp = cfg.get('QRadar', 'server')
    url = ('https://' + QRadarIp + '/console/qradar/jsp/QRadar.jsp?' +
        'appName=Sem&pageId=OffenseSummary&summaryId=' + str(offense['id']))

    description = (
        '## Summary\n\n' +
        '|                         |               |\n' +
        '| ----------------------- | ------------- |\n' +
        '| **Offense ID**          | ' + str(offense['id']) + ' |\n' +
        '| **Description**         | ' + str(offense['description'].replace('\n', '')) + ' |\n' +
        '| **Offense Type**        | ' + str(offense['offense_type_str']) + ' |\n' +
        '| **Offense Source**      | ' + str(offense['offense_source']) + ' |\n' +
        '| **Destination Network** | ' + str(offense['destination_networks']) +' |\n' +
        '| **Source Network**      | ' + str(offense['source_network']) + ' |\n\n\n' +
        '\n\n\n\n```\n')

    for log in offense['logs']:
        description += log['utf8_payload'] + '\n'

    description += '```\n\n' + url

    return description

if __name__ == '__main__':
    #hardcoding timerange as 1 minute when not using the API
    timerange = 1
    offense2Alert(timerange) 
