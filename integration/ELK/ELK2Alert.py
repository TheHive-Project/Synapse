#!/usr/bin/env python3
# -*- coding: utf8 -*-

import os, sys
import logging
import copy
import json
import re
import time
from calendar import timegm
from time import sleep
from builtins import str as unicode
from modules.generic.functions import getConf
#Bestaat nog niet niet
#from objects.ELKConnector import ELKConnector
from objects.TheHiveConnector import TheHiveConnector

current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = current_dir + '/..'
sys.path.insert(0, current_dir)
logger = logging.getLogger('app2a')
    
def __findartifacts(value):
    """Checks if the given value is contains regexes
    :param value: The value to check
    :type value: str or number
    :return: Data type of value, if known, else empty string
    :rtype: str
    """

    #Init regexes
    logger.info("Preparing regex statements")

    #### Generic regexes
    
    # IPv4
    regex = [{
        'types': ['ip'],
        'regex': re.compile(r'(?:^|\D)((?:25[0-5]|2[0-4]\d|[1]\d\d|[1-9]\d|[0-9])\.(?:25[0-5]|2[0-4]\d|[1]\d\d|[1-9]\d|[0-9])\.(?:25[0-5]|2[0-4]\d|[1]\d\d|[1-9]\d|[0-9])\.(?:25[0-5]|2[0-4]\d|[1]\d\d|[1-9]\d|[0-9]))(?:\D|$)', re.MULTILINE)
    }]

    # URL
    regex.append({
        'types': ['url','fqdn','domain','uri_path'],
        'regex': re.compile(r'((?:http|https):\/\/((?:(?:.*?)\.)?(.*?(?:\.\w+)+))\/?([a-zA-Z0-9\/\-\_\.\~\=\?]+\??)?)', re.MULTILINE)
    })

    # mail
    regex.append({
        'types': ['mail','domain'],
        'regex': re.compile(r'((?:[a-zA-Z0-9\/\-\_\.\+]+)@{1}([a-zA-Z0-9\-\_]+\.[a-zA-Z0-9\-\_\.]+)+)', re.MULTILINE)
    })

    found_observables = []
    if isinstance(value, (str, unicode)):
        for r in regex:
            matches = re.findall(r.get('regex'), value)
            if len(matches) > 0:
                
                for found_observable in matches:
                    if isinstance(found_observable, tuple):
                        i = 0
                        for groups in found_observable:
                            found_observables.append({
                                'type': r.get('types')[i],
                                'value': found_observable[i]
                                })
                            i += 1
                    else:
                        found_observables.append({
                            'type': r.get('types')[0],
                            'value': found_observable
                            })
        if len(found_observables) > 0:
            return found_observables
        else:
            return []

def enrichAlert(elkConnector, mlalert):
    return True

def ELKToHiveAlert(theHiveConnector, alert_data):
    #
    # Creating the alert
    #

    # Setup Tags
    tags = ['ELK', 'Synapse']

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

    if alert_data['type'] == "asml":
        found_artifacts = __findartifacts(alert_data['influencers'])
    else: 
        found_artifacts = __findartifacts(alert_data['description'])
    if 'rule_id' in alert_data:
        uc_tags = alert_data['rule_id'].split(",")
        uc_tags = list(set(uc_tags) | set(alert_data['rule_triggered_id'].split(",")))
        tags.extend(uc_tags)
    if 'customer_id' in alert_data:
        tags.append(alert_data['customer_id'])
    if 'customer_name' in alert_data:
        tags.append(alert_data['customer_name'])
    if 'machine_name' in alert_data:
        tags.append(alert_data['machine_name'])
    artifacts = []
    for found_artifact in found_artifacts:
        if not 'tags' in found_artifact:
            found_artifact['tags'] = list()
        found_artifact['tags'].append('type:' + found_artifact['type'])

        if found_artifact['type'] in defaultObservableDatatype:
            hiveArtifact = theHiveConnector.craftAlertArtifact(dataType=found_artifact['type'], data=found_artifact['value'], message='', tags=found_artifact['tags'])
        else:
            hiveArtifact = theHiveConnector.craftAlertArtifact(dataType='other', data=found_artifact['data'], message='', tags=found_artifact['tags'])
        artifacts.append(hiveArtifact)

    #Convert timestamp to epoch
    if 'start_time' in alert_data:
        utc_time = time.strptime(alert_data['start_time'], "%Y-%m-%dT%H:%M:%S.%fZ")
        epoch_start_time = timegm(utc_time) * 1000
    else:
        epoch_start_time = timegm(time.gmtime()) * 1000

    # Build TheHive alert
    alert = theHiveConnector.craftAlert(
        alert_data['title'],
        alert_data['description'],
        1,
        epoch_start_time,
        tags,
        2,
        'Imported',
        'internal',
        alert_data['type'],
        str(alert_data['sourceRef']),
        artifacts,
        alert_data['case_template'])

    return alert


def ml2Alert(mlalert):
    """
       Parse the received ml watcher notification
       Original example Watch Actions:
       
        "TheHive": {
            "webhook": {
                "scheme": "http",
                "host": "machine.domain.com",
                "port": 5000,
                "method": "post",
                "path": "/ELK2alert",
                "params": {},
                "headers": {
                    "Authorization": "Bearer 2WTbTHH8iaSeoo8yk8y0GA96dX7/Tz7s",
                    "Cookie": "cookie=no",
                    "Content-Type": "application/json"
                },
                "body": "{\"ml_job_id\": \"{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0._source.job_id}}\",\n\"description\": \"some description\",\n\"start_time\": \"{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0.fields.timestamp_iso8601.0}}\",\n\"anomaly_score\": \"{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0.fields.score.0}}\",\n\"url\": \"https://machine.domain.com:5601/app/ml#/explorer/?_g=(ml:(jobIds:!('{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0._source.job_id}}')),refreshInterval:(display:Off,pause:!f,value:0),time:(from:'{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0.fields.start.0}}',mode:absolute,to:'{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0.fields.end.0}}'))&_a=(filters:!(),mlAnomaliesTable:(intervalValue:auto,thresholdValue:0),mlExplorerSwimlane:(selectedLane:Overall,selectedTime:{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0.fields.timestamp_epoch.0}},selectedType:overall),query:(query_string:(analyze_wildcard:!t,query:'**')))\",\n\"influencers\": \"{{ctx.payload.aggregations.record_results.top_record_hits.hits.hits}}\\n{{_source.function}}({{_source.field_name}}) {{_source.by_field_value}} {{_source.over_field_value}} {{_source.partition_field_value}} [{{fields.score.0}}]\\n{{ctx.payload.aggregations.record_results.top_record_hits.hits.hits}}\",\n\"type\": \"asml\",\n\"source\": \"Elastic\",\n\"sourceRef\": \"{{ctx.payload.as_watch_id}}\"}"
            }
        }

       Nice example input:
        "{
            \"ml_job_id\": \"{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0._source.job_id}}\",\n
            \"description\": \"some description\",\n
            \"start_time\": \"{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0.fields.timestamp_iso8601.0}}\",\n
            \"anomaly_score\": \"{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0.fields.score.0}}\",\n
            \"url\": \"https://machine.domain.com:5601/app/ml#/explorer/?_g=(ml:(jobIds:!('{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0._source.job_id}}')),refreshInterval:(display:Off,pause:!f,value:0),time:(from:'{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0.fields.start.0}}',mode:absolute,to:'{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0.fields.end.0}}'))&_a=(filters:!(),mlAnomaliesTable:(intervalValue:auto,thresholdValue:0),mlExplorerSwimlane:(selectedLane:Overall,selectedTime:{{ctx.payload.aggregations.bucket_results.top_bucket_hits.hits.hits.0.fields.timestamp_epoch.0}},selectedType:overall),query:(query_string:(analyze_wildcard:!t,query:'**')))\",\n
            \"influencers\": \"{{ctx.payload.aggregations.record_results.top_record_hits.hits.hits}}\\n
                               {{_source.function}}({{_source.field_name}}) {{_source.by_field_value}} {{_source.over_field_value}} {{_source.partition_field_value}} [{{fields.score.0}}]\\n
                               {{ctx.payload.aggregations.record_results.top_record_hits.hits.hits}}\",\n
            \"type\": \"asml\",\n
            \"source\": \"Elastic\",\n
            \"sourceRef\": \"{{ctx.payload.as_watch_id}}\"
        }"
    """
    #logger = logging.getLogger(__name__)
    logger.info('%s.ml2Alert starts', __name__)

    report = dict()
    report['success'] = True

    try:
        cfg = getConf()

        theHiveConnector = TheHiveConnector(cfg)
        
        #Map the ml watcher alert to the alert that will be enhanced
        logger.info('Looking for ML Alert %s in TheHive alerts', str(mlalert['sourceRef']))
        
        #I should see if we can find a way to generate a shorter more useful sourceRef from within Synapse
        q = dict()
        q['sourceRef'] = str(mlalert['sourceRef'])
        results = theHiveConnector.findAlert(q)
        if len(results) == 0:
            logger.info('ML Alert %s not found in TheHive alerts, creating it', str(mlalert['sourceRef']))
            mlalert_report = dict()

            #Set generic parameters
            mlalert['title'] = "ML: " + mlalert['ml_job_id']
            mlalert['description'] = craftMLAlertDescription(mlalert)
            mlalert['case_template'] = "ELK-ML"

            #Enrichment is not in scope yet
            #enrichedAlert = enrichAlert(elkConnector, mlalert)
            
            try:
                theHiveAlert = ELKToHiveAlert(theHiveConnector, mlalert)
                theHiveEsAlertId = theHiveConnector.createAlert(theHiveAlert)

                mlalert_report['raised_alert_id'] = theHiveEsAlertId
                mlalert_report['ml_alert_id'] = mlalert['sourceRef']
                mlalert_report['success'] = True

            except Exception as e:
                logger.error('%s.ml2Alert failed', __name__, exc_info=True)
                mlalert_report['success'] = False
                if isinstance(e, ValueError):
                    errorMessage = json.loads(str(e))['message']
                    mlalert_report['message'] = errorMessage
                else:
                    mlalert_report['message'] = str(e) + ": Couldn't raise alert in TheHive"
                mlalert_report['ml_alert_id'] = mlalert['sourceRef']
                # Set overall success if any fails
                report['success'] = False

            report['mlalert'] = mlalert_report
        else:
            logger.info('ML Alert %s already imported as alert', str(mlalert['sourceRef']))

    except Exception as e:

            logger.error('Failed to create alert from ML Alert', exc_info=True)
            report['success'] = False
            report['message'] = "%s: Failed to create alert from ML Alert" % str(e)
    
    return report

def logstash2Alert(event):
    """
       Parse the received ml watcher notification
       Original example logstash output:

       Nice example input:
        
    """
    #logger = logging.getLogger(__name__)
    logger.info('%s.logstash2Alert starts', __name__)

    report = dict()
    report['success'] = True

    try:
        cfg = getConf()

        theHiveConnector = TheHiveConnector(cfg)
        
        #Map the ml watcher alert to the alert that will be enhanced
        logger.info('Looking for Logstash Alert %s in TheHive alerts', str(event['sourceRef']))
        
        #I should see if we can find a way to generate a shorter more useful sourceRef from within Synapse
        q = dict()
        q['sourceRef'] = str(event['sourceRef'])
        results = theHiveConnector.findAlert(q)
        if len(results) == 0:
            logger.info('Logstash Alert %s not found in TheHive alerts, creating it', str(event['sourceRef']))
            event_report = dict()

            event['case_template'] = "ELK-Anomalies"

            #Enrichment is not in scope yet
            #enrichedAlert = enrichAlert(elkConnector, event)
            
            try:
                theHiveAlert = ELKToHiveAlert(theHiveConnector, event)
                theHiveEsAlertId = theHiveConnector.createAlert(theHiveAlert)

                event_report['raised_alert_id'] = theHiveEsAlertId
                event_report['alert_id'] = event['sourceRef']
                event_report['success'] = True

            except Exception as e:
                logger.error('%s.logstash2Alert failed', __name__, exc_info=True)
                event_report['success'] = False
                if isinstance(e, ValueError):
                    errorMessage = json.loads(str(e))['message']
                    event_report['message'] = errorMessage
                else:
                    event_report['message'] = str(e) + ": Couldn't raise alert in TheHive"
                event_report['alert_id'] = event['sourceRef']
                # Set overall success if any fails
                report['success'] = False

            report['event'] = event_report
        else:
            logger.info('Logstash Alert %s already imported as alert', str(event['sourceRef']))

    except Exception as e:

            logger.error('Failed to create alert from Logstash Alert', exc_info=True)
            report['success'] = False
            report['message'] = "%s: Failed to create alert from Logstash Alert" % str(e)
    
    return report
            
def craftMLAlertDescription(mlalert):
    """
        From the mlalert metadata, crafts a nice description in markdown
        for TheHive
    """
    logger = logging.getLogger(__name__)
    logger.info('craftMLAlertDescription starts')


    cfg = getConf()
    ELKIp = cfg.get('ELK', 'server')
    url = ('https://' + ELKIp + '/test')

    description = (
        '## Summary\n\n' +
        '|                         |               |\n' +
        '| ----------------------- | ------------- |\n' +
        '| **ML Alert ID**          | ' + str(mlalert['sourceRef']) + ' |\n' +
        '| **Description**         | ' + str(mlalert['description'].replace('\n', '')) + ' |\n' +
        '| **ML Influencers**        | ' + str(mlalert['influencers'].replace('\n', '')) + ' |\n' +
        '| **ML Type**        | ' + str(mlalert['type']) + ' |\n' +
        '| **ML Source**      | ' + str(mlalert['source']) + ' |\n' +
        '| **URL**        | ' + str(mlalert['url']) + ' |\n\n\n' +
        '\n\n\n\n```\n')

    description += '```\n\n' + url

    return description