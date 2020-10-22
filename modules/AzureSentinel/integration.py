import logging
from core.functions import getConf
from modules.AzureSentinel.connector import AzureSentinelConnector
from modules.TheHive.connector import TheHiveConnector

def craftAlertDescription(incident):
    """
        From the incident metadata, crafts a nice description in markdown
        for TheHive
    """
    logger.debug('craftAlertDescription starts')
    
    #Start empty
    description = ""

    #Add url to incident
    url = ('[%s](%s)' % (str(incident['properties']['incidentNumber']), str(incident['properties']['incidentUrl'])))

    description += '#### Incident: \n - ' + url + '\n\n'

    #Add incident details table
    description += (
        '#### Summary\n\n' +
        '|                         |               |\n' +
        '| ----------------------- | ------------- |\n' +
        '| **Start Time**          | ' + str(azureSentinelConnector.formatDate(incident['properties']['createdTimeUtc'])) + ' |\n' +
        '| **incident ID**          | ' + str(incident['properties']['incidentNumber']) + ' |\n' +
        '| **Description**         | ' + str(incident['properties']['description'].replace('\n', '')) + ' |\n' +
        '| **incident Type**        | ' + str(incident['type']) + ' |\n' +
        '| **incident Source**      | ' + str(incident['additionalData']['alertProductNames']) + ' |\n' +
        '\n\n\n\n')

    return description

def sentinelIncidentToHiveAlert(incident):

    def getHiveSeverity(incident):
        #severity in TheHive is either low, medium or high
        #while severity in Sentinel is from Low to High
        if incident['properties']['severity'] < "Low":
            return 1
        elif incident['properties']['severity'] < "Medium":
            return 2
        elif incident['properties']['severity'] < "High":
            return 3

        return 1

    #
    # Creating the alert
    #

    # Setup Tags
    tags = ['Sentinel', 'incident', 'Synapse']

    #Skip for now
    artifacts = []

    #Retrieve the configured case_template
    sentinelCaseTemplate = cfg.get('AzureSentinel', 'case_template')
        
    # Build TheHive alert
    alert = theHiveConnector.craftAlert(
        "{}, {}".format(incident['properties']['incidentNumber'], incident['properties']['title']),
        craftAlertDescription(incident),
        getHiveSeverity(incident),
        incident['properties']['createdTimeUtc'],
        tags,
        2,
        'New',
        'internal',
        'Azure_Sentinel_incidents',
        str(incident['name']),
        artifacts,
        sentinelCaseTemplate)

    return alert

def validateRequest(request):
    if request.is_json:
        content = request.get_json()
        if 'type' in content and content['type'] == "Active":
            workflowReport = allIncidents2Alert(content['type'])
            if workflowReport['success']:
                return json.dumps(workflowReport), 200
            else:
                return json.dumps(workflowReport), 500
        else:
            logger.error('Missing <timerange> key/value')
            return json.dumps({'sucess':False, 'message':"timerange key missing in request"}), 500
    else:
        logger.error('Not json request')
        return json.dumps({'sucess':False, 'message':"Request didn't contain valid JSON"}), 400

def allIncidents2Alert(status):
    """
       Get all opened incidents created within Azure Sentinel 
       and create alerts for them in TheHive
    """
    logger.info('%s.allincident2Alert starts', __name__)

    report = dict()
    report['success'] = True
    report['incidents'] = list()

    try:
        incidentsList = AzureSentinelConnector.getIncidents()
        
        #each incidents in the list is represented as a dict
        #we enrich this dict with additional details
        for incident in incidentsList:
            if not incident['properties']['status'] == 'Active':
                continue

            #Prepare new alert
            incident_report = dict()
            logger.debug("incident: %s" % incident)
            #logger.info("Enriching incident...")
            #enrichedincident = enrichIncident(incident)
            #logger.debug("Enriched incident: %s" % enrichedincident)
            theHiveAlert = sentinelIncidentToHiveAlert(incident)
            
            #searching if the incident has already been converted to alert
            q = dict()
            q['sourceRef'] = str(incident['name'])
            logger.info('Looking for incident %s in TheHive alerts', str(incident['name']))
            results = theHiveConnector.findAlert(q)
            if len(results) == 0:
                logger.info('incident %s not found in TheHive alerts, creating it', str(incident['name']))
                
                try:
                    theHiveEsAlertId = theHiveConnector.createAlert(theHiveAlert)['id']

                    incident_report['raised_alert_id'] = theHiveEsAlertId
                    incident_report['sentinel_incident_id'] = incident['name']
                    incident_report['success'] = True

                except Exception as e:
                    logger.error('%s.allincident2Alert failed', __name__, exc_info=True)
                    incident_report['success'] = False
                    if isinstance(e, ValueError):
                        errorMessage = json.loads(str(e))['message']
                        incident_report['message'] = errorMessage
                    else:
                        incident_report['message'] = str(e) + ": Couldn't raise alert in TheHive"
                    incident_report['incident_id'] = incident['name'] 
                    # Set overall success if any fails
                    report['success'] = False

                report['incidents'].append(incident_report)
            # else:
            #     logger.info('incident %s already imported as alert, checking for updates', str(incident['name']))
            #     alert_found = results[0]
                
            #     #Check if alert is already created, but needs updating
            #     if check_if_updated(alert_found, vars(theHiveAlert)):
            #         logger.info("Found changes for %s, updating alert" % alert_found['id'])
                    
            #         #update alert
            #         theHiveConnector.updateAlert(alert_found['id'], theHiveAlert, fields=["tags", "artifacts"])
            #         incident_report['updated_alert_id'] = alert_found['id']
            #         incident_report['sentinel_incident_id'] = incident['name']
            #         incident_report['success'] = True
            #     else:
            #         logger.info("No changes found for %s" % alert_found['id'])
            #         continue
                ##########################################################

    except Exception as e:

            logger.error('Failed to create alert from Azure Sentinel incident (retrieving incidents failed)', exc_info=True)
            report['success'] = False
            report['message'] = "%s: Failed to create alert from incident" % str(e)
    
    return report