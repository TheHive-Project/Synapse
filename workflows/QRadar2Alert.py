#!/usr/bin/env python3
# -*- coding: utf8 -*-

import os, sys
import logging
import copy
import itertools

current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = current_dir + '/..'
sys.path.insert(0, current_dir)

from common.common import getConf
from objects.QRadarConnector import QRadarConnector
from objects.TheHiveConnector import TheHiveConnector

def getEnrichedOffenses(qradarConnector, timerange):
    enrichedOffenses = []

    for offense in qradarConnector.getOffenses(timerange):
        enrichedOffenses.append(enrichOffense(qradarConnector, offense))

    return enrichedOffenses

def enrichOffense(qradarConnector, offense):

    enriched = copy.deepcopy(offense)

    artifacts = []

    enriched['offense_type_str'] = \
                qradarConnector.getOffenseTypeStr(offense['offense_type'])

    # Add the offense source explicitly 
    if enriched['offense_type_str'] == "Username":
        artifacts.append({"data":offense["offense_source"], "dataType":"user", "message":"Offense Source"})

    if enriched['offense_type_str'] == "Destination IP" or enriched['offense_type_str'] == "Source IP":
        artifacts.append({"data":offense["offense_source"], "dataType":"ip", "message": enriched['offense_type_str']})

    # Add the local and remote sources
    for ip in qradarConnector.getSourceIPs(enriched):
        artifacts.append({"data":ip, "dataType":"ip", "message":"Source IP"})

    for ip in qradarConnector.getLocalDestinationIPs(enriched):
        artifacts.append({"data":ip, "dataType":"ip", "message":"Local destination IP"})

    # Add all the observables
    enriched["artifacts"] = artifacts

    # Get the Rule details - NYI
    #enriched["rule_names"] = qradarConnector.getRuleNames(enriched)

    # Try and guess a use case / type - NYI 
    #enriched["use_case"] = guessUseCase(enriched)

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

    #
    # Creating the alert
    #

    # Setup Tags
    tags = ['QRadar', 'Offense', 'Synapse']
    
    if "categories" in offense:
        for cat in offense['categories']:
            tags.append(cat)

    artifacts = []
    for artifact in offense['artifacts']:
        hiveArtefact = theHiveConnector.craftAlertArtifact(dataType = artifact["dataType"], data = artifact["data"], message=artifact["message"])
        artifacts.append(hiveArtefact)

    # Build TheHive alert
    alert = theHiveConnector.craftAlert(
        offense['description'],
        craftAlertDescription(offense),
        getHiveSeverity(offense),
        offense['start_time'],
        tags,
        2,
        'Imported',
        'internal',
        'QRadar_Offenses',
        'usertest_%s' % str(offense['id']),
        artifacts,
        '')

    return alert


def allOffense2Alert(timerange):
    """
       Get all openned offense created within the last 
       <timerange> minutes and creates alerts for them in
       TheHive
    """
    logger = logging.getLogger(__name__)
    logger.info('%s.allOffense2Alert starts', __name__)

    report = dict()
    report['success'] = True
    report['offenses'] = list()

    try:
        cfg = getConf()

        qradarConnector = QRadarConnector(cfg)
        theHiveConnector = TheHiveConnector(cfg)

        offensesList = getEnrichedOffenses(qradarConnector, timerange)
        
        #each offenses in the list is represented as a dict
        #we enrich this dict with additional details
        for offense in offensesList:

            offense_report = dict()
            offense_report['original_offense'] = offense
            
            try:
                theHiveAlert = qradarOffenseToHiveAlert(theHiveConnector, offense)
                theHiveConnector.createAlert(theHiveAlert)

                offense_report['raised_alert'] = theHiveAlert.jsonify()
                offense_report['success'] = True

            except Exception as e:
                offense_report['success'] = False
                offense_report['message'] = str(e)
                offense_report['message'] = "Couldn't raise alert in the Hive (%s)" % str(e)

                # Set overall success if any fails
                report['success'] = False

            report['offenses'].append(offense_report)

    except Exception as e:

            logger.error('Failed to create alert from QRadar offense (retrieving offenses failed)', exc_info=True)
            report['success'] = False
            report['message'] = "Couldn't create alert from QRadar offense (couldn't retrieve offenses: %s)" % str(e)
    
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
