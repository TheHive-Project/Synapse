#!/usr/bin/env python3
# -*- coding: utf8 -*-

import os, sys
import logging
import copy
import json
import datetime
import re
import itertools
from modules.generic.functions import getConf, loadUseCases
from dateutil import tz
from objects.QRadarConnector import QRadarConnector
from objects.TheHiveConnector import TheHiveConnector
from time import sleep

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = current_dir + '/../..'
sys.path.insert(0, current_dir)
cfg = getConf()
use_cases = loadUseCases()

#Get logger
logger = logging.getLogger('app2a')

def formatDate(qradarTimeStamp):
    #Define timezones
    current_timezone = tz.gettz('UTC')
    configured_timezone = cfg.get('QRadar', 'timezone')
    if not configured_timezone:
        configured_timezone = tz.gettz('Europe/Amsterdam')

    #Parse timestamp received from QRadar
    qradarTimeStamp = qradarTimeStamp / 1000.0
    formatted_time = datetime.datetime.fromtimestamp(qradarTimeStamp).strftime('%Y-%m-%d %H:%M:%S')
    formatted_time formatted_time.replace(tzinfo=current_timezone)

    #Convert to configured timezone
    formatted_time = formatted_time.astimezone(configured_timezone)

    return formatted_time

def extractUseCaseIDs(offense, field_name, extraction_regex):
    logger.debug('%s.extractUseCaseIDs starts', __name__)
    #print(extraction_regex)
    regex = re.compile(extraction_regex)
    #print(str(offense[field_name]))
    logger.debug("offense: %s" % offense[field_name])
    uc_matches = regex.findall(str(offense[field_name]))
    if len(uc_matches) > 0:
        logger.debug("uc_matches: %s" % uc_matches)
        return uc_matches
    else:
        return False
        
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
    if enriched['offense_type_str'] == 'Username':
        artifacts.append({'data':offense['offense_source'], 'dataType':'username', 'message':'Offense Source'})

    # Add the local and remote sources
    #scrIps contains offense source IPs
    srcIps = list()
    #dstIps contains offense destination IPs
    dstIps = list()
    #srcDstIps contains IPs which are both source and destination of offense
    srcDstIps = list()
    for ip in qradarConnector.getSourceIPs(enriched):
        srcIps.append(ip)

    for ip in qradarConnector.getLocalDestinationIPs(enriched):
        dstIps.append(ip)

    #making copies is needed since we want to
    #access and delete data from the list at the same time
    s = copy.deepcopy(srcIps)
    d = copy.deepcopy(dstIps)

    for srcIp in s:
        for dstIp in d:
            if srcIp == dstIp:
                srcDstIps.append(srcIp)
                srcIps.remove(srcIp)
                dstIps.remove(dstIp)

    for ip in srcIps:
        artifacts.append({'data':ip, 'dataType':'ip', 'message':'Source IP', 'tags':['src']})
    for ip in dstIps:
        artifacts.append({'data':ip, 'dataType':'ip', 'message':'Local destination IP', 'tags':['dst']})
    for ip in srcDstIps:
        artifacts.append({'data':ip, 'dataType':'ip', 'message':'Source and local destination IP', 'tags':['src', 'dst']})
        
    # Add all the observables
    enriched['artifacts'] = artifacts

    # Add rule names to offense
    enriched['rules'] = qradarConnector.getRuleNames(offense)
    
    
    # waiting 1s to make sure the logs are searchable
    sleep(1)
    #adding the first 3 raw logs
    enriched['logs'] = qradarConnector.getOffenseLogs(enriched)

    return enriched

#Function to check if the alert that has been created contains new/different data in comparison to the alert that is present
def check_if_updated(current_a, new_a):
    logger.debug("Current alert %s" % current_a)
    logger.debug("New alert %s" % new_a)
    for item in sorted(new_a):
        #Skip values that are not required for the compare
        if item is "date":
            continue
        #Artifacts require special attention as these are all separate objects in an array for a new alert. The current alert is a array of dicts
        if item is "artifacts":
            #If the array is of different size an update is required
            if not len(current_a[item]) == len(new_a[item]):
                logger.info("Length mismatch detected: old length:%s, new length: %s" % (len(current_a[item]),len(new_a[item])))
                return True
            
            #loop through the newly created alert array to extract the artifacts and add them so a separate variable
            for i in range(len(new_a[item])):
                vars_current_artifacts = current_a[item][i]
                vars_new_artifacts = vars(new_a[item][i])
                
                #For each artifact loop through the attributes to check for differences
                for attribute in vars_new_artifacts:
                    if vars_current_artifacts[attribute] != vars_new_artifacts[attribute]:
                        logger.debug("Change detected for %s, new value: %s" % (vars_current_artifacts[attribute],vars_new_artifacts[attribute]))
                        logger.debug("old: %s, new: %s" % (vars_current_artifacts,vars_new_artifacts))
                        return True
            
            
            #loop through the newly created alert array to extract the artifacts and add them so a separate variable
            #diff = list(itertools.filterfalse(lambda x: x in vars(new_a['artifacts']), current_a['artifacts']))
            #if len(diff) > 0:
            #    logger.debug("Found diff in artifacts: %s" % diff)
            #    return True
            
        if item is "tags":
            #loop through the newly created alert array to extract the tags and add them so a separate variable
            diff = list(itertools.filterfalse(lambda x: x in new_a['tags'], current_a['tags']))
            if len(diff) > 0:
                logger.debug("Found diff in tags: %s" % diff)
                return True
         
        #Match other items of the new alert to the current alert (string based)
        #if str(current_a[item]) != str(new_a[item]):
            #logger.debug("Change detected for %s, new value: %s" % (item,str(new_a[item])))
            #return True
    return False

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
    
    #Check if the use case id needs te extracted
    if cfg.getboolean('QRadar', 'extract_use_case'):
        
        #Run the extraction function and add it to the tags list
        use_case_ids = extractUseCaseIDs(offense, use_cases['configuration']['uc_field'], use_cases['configuration']['uc_regex'])
        offense['use_case_names'] = extractUseCaseIDs(offense, use_cases['configuration']['uc_field'], use_cases['configuration']['uc_kb_name_regex'])
        
        if use_case_ids:
            tags.extend(use_case_ids)
        else:
            logger.info('No match found for offense %s', offense['id'])
    
    if "categories" in offense:
        for cat in offense['categories']:
            tags.append(cat)

    defaultObservableDatatype = ['autonomous-system',
                                'domain',
                                'file',
                                'filename',
                                'fqdn',
                                'hash',
                                'ip',
                                'mail',
                                'mail_subject',
                                'other',
                                'regexp',
                                'registry',
                                'uri_path',
                                'url',
                                'user-agent']

    artifacts = []
    for artifact in offense['artifacts']:
        if artifact['dataType'] in defaultObservableDatatype:
            hiveArtifact = theHiveConnector.craftAlertArtifact(dataType=artifact['dataType'], data=artifact['data'], message=artifact['message'], tags=artifact['tags'])
        else:
            tags = list()
            tags.append('type:' + artifact['dataType'])
            hiveArtifact = theHiveConnector.craftAlertArtifact(dataType='other', data=artifact['data'], message=artifact['message'], tags=tags)
        artifacts.append(hiveArtifact)

    #Retrieve the configured case_template
    qradarCaseTemplate = cfg.get('QRadar', 'case_template')
        
    # Build TheHive alert
    alert = theHiveConnector.craftAlert(
        "{}, {}".format(offense['id'], offense['description']),
        craftAlertDescription(offense),
        getHiveSeverity(offense),
        offense['start_time'],
        tags,
        2,
        'Imported',
        'internal',
        'QRadar_Offenses',
        str(offense['id']),
        artifacts,
        qradarCaseTemplate)

    return alert


def allOffense2Alert(timerange):
    """
       Get all openned offense created within the last 
       <timerange> minutes and creates alerts for them in
       TheHive
    """
    logger.info('%s.allOffense2Alert starts', __name__)

    report = dict()
    report['success'] = True
    report['offenses'] = list()

    try:
        qradarConnector = QRadarConnector(cfg)
        theHiveConnector = TheHiveConnector(cfg)

        offensesList = qradarConnector.getOffenses(timerange)
        
        #each offenses in the list is represented as a dict
        #we enrich this dict with additional details
        for offense in offensesList:
            #Prepare new alert
            offense_report = dict()
            logger.debug("offense: %s" % offense)
            logger.info("Enriching offense...")
            enrichedOffense = enrichOffense(qradarConnector, offense)
            logger.debug("Enriched offense: %s" % enrichedOffense)
            theHiveAlert = qradarOffenseToHiveAlert(theHiveConnector, enrichedOffense)
            
            #searching if the offense has already been converted to alert
            q = dict()
            q['sourceRef'] = str(offense['id'])
            logger.info('Looking for offense %s in TheHive alerts', str(offense['id']))
            results = theHiveConnector.findAlert(q)
            if len(results) == 0:
                logger.info('Offense %s not found in TheHive alerts, creating it', str(offense['id']))
                
                try:
                    theHiveEsAlertId = theHiveConnector.createAlert(theHiveAlert)['id']

                    offense_report['raised_alert_id'] = theHiveEsAlertId
                    offense_report['qradar_offense_id'] = offense['id']
                    offense_report['success'] = True

                except Exception as e:
                    logger.error('%s.allOffense2Alert failed', __name__, exc_info=True)
                    offense_report['success'] = False
                    if isinstance(e, ValueError):
                        errorMessage = json.loads(str(e))['message']
                        offense_report['message'] = errorMessage
                    else:
                        offense_report['message'] = str(e) + ": Couldn't raise alert in TheHive"
                    offense_report['offense_id'] = offense['id'] 
                    # Set overall success if any fails
                    report['success'] = False

                report['offenses'].append(offense_report)
            else:
                logger.info('Offense %s already imported as alert, checking for updates', str(offense['id']))
                alert_found = results[0]
                
                #Check if alert is already created, but needs updating
                if check_if_updated(alert_found, vars(theHiveAlert)):
                    logger.info("Found changes for %s, updating alert" % alert_found['id'])
                    
                    #update alert
                    theHiveConnector.updateAlert(alert_found['id'], theHiveAlert, fields=["tags", "artifacts"])
                    offense_report['updated_alert_id'] = alert_found['id']
                    offense_report['qradar_offense_id'] = offense['id']
                    offense_report['success'] = True
                else:
                    logger.info("No changes found for %s" % alert_found['id'])
                    continue
                ##########################################################

    except Exception as e:

            logger.error('Failed to create alert from QRadar offense (retrieving offenses failed)', exc_info=True)
            report['success'] = False
            report['message'] = "%s: Failed to create alert from offense" % str(e)
    
    return report
            
def craftAlertDescription(offense):
    """
        From the offense metadata, crafts a nice description in markdown
        for TheHive
    """
    logger.debug('craftAlertDescription starts')
    
    #Start empty
    description = ""
    
    #Format associated rules
    rule_names_formatted = "#### Rules triggered: \n"
    rules = offense['rules']
    if len(rules) > 0:
        for rule in rules:
            if 'name' in rule:
                rule_names_formatted += "- %s \n" % rule['name']
            else:
                continue

    #Format associated documentation
    uc_links_formatted = "#### Use Case documentation: \n"
    if 'use_case_names' in offense and offense['use_case_names']:
        for uc in offense['use_case_names']:
            uc_links_formatted += "- [%s](%s/%s) \n" % (uc, use_cases['configuration']['kb_url'], uc)

    #Add url to Offense
    QRadarIp = cfg.get('QRadar', 'server')
    url = ('[%s](https://%s/console/qradar/jsp/QRadar.jsp?appName=Sem&pageId=OffenseSummary&summaryId=%s)' % (str(offense['id']), QRadarIp, str(offense['id'])))

    description += '#### Offense: \n - ' + url + '\n\n'
    
    #Add rules overview to description
    description += rule_names_formatted + '\n\n'
    
    #Add associated documentation
    description += uc_links_formatted + '\n\n'

    #Add offense details table
    description += (
        '#### Summary\n\n' +
        '|                         |               |\n' +
        '| ----------------------- | ------------- |\n' +
        '| **Start Time**          | ' + str(formatDate(offense['start_time'])) + ' |\n' +
        '| **Offense ID**          | ' + str(offense['id']) + ' |\n' +
        '| **Description**         | ' + str(offense['description'].replace('\n', '')) + ' |\n' +
        '| **Offense Type**        | ' + str(offense['offense_type_str']) + ' |\n' +
        '| **Offense Source**      | ' + str(offense['offense_source']) + ' |\n' +
        '| **Destination Network** | ' + str(offense['destination_networks']) +' |\n' +
        '| **Source Network**      | ' + str(offense['source_network']) + ' |\n\n\n' +
        '\n\n\n\n')

    #Add raw payload
    description += '```\n'
    for log in offense['logs']:
        description += log['utf8_payload'] + '\n'
    description += '```\n\n'

    return description

if __name__ == '__main__':
    #hardcoding timerange as 1 minute when not using the API
    logger.info("Starting QRadar2Alert")
    timerange = cfg.get('QRadar', 'offense_time_range')
    allOffense2Alert(timerange) 
