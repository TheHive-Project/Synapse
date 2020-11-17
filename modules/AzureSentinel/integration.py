import json
import logging
import itertools
from core.functions import getConf
from modules.AzureSentinel.connector import AzureSentinelConnector
from modules.TheHive.connector import TheHiveConnector

cfg = getConf()

azureSentinelConnector = AzureSentinelConnector(cfg)
theHiveConnector = TheHiveConnector(cfg)

#Get logger
logger = logging.getLogger(__name__)

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

    #Format associated rules
    rule_names_formatted = "#### Rules triggered: \n"
    rules = incident['properties']['relatedAnalyticRuleIds']
    if len(rules) > 0:
        for rule in rules:
            rule_info = azureSentinelConnector.getRule(rule)
            logger.debug('Received the following rule information: {}'.format(rule_info))
            rule_name = rule_info['properties']['displayName']
            rule_url = "https://management.azure.com{}".format(rule)
            rule_names_formatted += "- %s \n" % (rule_name)

    #Add rules overview to description
    description += rule_names_formatted + '\n\n'

    #Add mitre Tactic information
    #https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json

    # mitre_ta_links_formatted = "#### MITRE Tactics: \n"
    # if 'mitre_tactics' in offense and offense['mitre_tactics']:
    #     for tactic in offense['mitre_tactics']:
    #         mitre_ta_links_formatted += "- [%s](%s/%s) \n" % (tactic, 'https://attack.mitre.org/tactics/', tactic)
        
    #     #Add associated documentation
    #     description += mitre_ta_links_formatted + '\n\n'

    # #Add mitre Technique information
    # mitre_t_links_formatted = "#### MITRE Techniques: \n"
    # if 'mitre_techniques' in offense and offense['mitre_techniques']:
    #     for technique in offense['mitre_techniques']:
    #         mitre_t_links_formatted += "- [%s](%s/%s) \n" % (technique, 'https://attack.mitre.org/techniques/', technique)

    #Add incident details table
    description += (
        '#### Summary\n\n' +
        '|                         |               |\n' +
        '| ----------------------- | ------------- |\n' +
        '| **Start Time**          | ' + str(azureSentinelConnector.formatDate("description", incident['properties']['createdTimeUtc'])) + ' |\n' +
        '| **incident ID**          | ' + str(incident['properties']['incidentNumber']) + ' |\n' +
        '| **Description**         | ' + str(incident['properties']['description'].replace('\n', '')) + ' |\n' +
        '| **incident Type**        | ' + str(incident['type']) + ' |\n' +
        '| **incident Source**      | ' + str(incident['properties']['additionalData']['alertProductNames']) + ' |\n' +
        '| **incident Status**      | ' + str(incident['properties']['status']) + ' |\n' +
        '\n\n\n\n')

    return description

def sentinelIncidentToHiveAlert(incident):

    def getHiveSeverity(incident):
        #severity in TheHive is either low, medium or high
        #while severity in Sentinel is from Low to High
        if incident['properties']['severity'] == "Low":
            return 1
        elif incident['properties']['severity'] == "Medium":
            return 2
        elif incident['properties']['severity'] == "High":
            return 3

        return 1

    #
    # Creating the alert
    #

    # Setup Tags
    tags = ['AzureSentinel', 'incident', 'Synapse']

    #Skip for now
    artifacts = []

    #Retrieve the configured case_template
    sentinelCaseTemplate = cfg.get('AzureSentinel', 'case_template')
        
    # Build TheHive alert
    alert = theHiveConnector.craftAlert(
        "{}, {}".format(incident['properties']['incidentNumber'], incident['properties']['title']),
        craftAlertDescription(incident),
        getHiveSeverity(incident),
        azureSentinelConnector.formatDate("alert_timestamp", incident['properties']['createdTimeUtc']),
        tags,
        2,
        'New',
        'internal',
        'Azure_Sentinel_incidents',
        str(incident['name']),
        artifacts,
        sentinelCaseTemplate)

    return alert

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
            diff = diff + list(itertools.filterfalse(lambda x: x in current_a['tags'], new_a['tags']))
            if len(diff) > 0:
                logger.debug("Found diff in tags: %s" % diff)
                return True
         
        #Match other items of the new alert to the current alert (string based)
        #if str(current_a[item]) != str(new_a[item]):
            #logger.debug("Change detected for %s, new value: %s" % (item,str(new_a[item])))
            #return True
    return False

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
            logger.error('Missing type or type is not supported')
            return json.dumps({'sucess':False, 'message':"Missing type or type is not supported"}), 500
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
        incidentsList = azureSentinelConnector.getIncidents()
        
        #each incidents in the list is represented as a dict
        #we enrich this dict with additional details
        for incident in incidentsList:

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
            else:
                logger.info('incident %s already imported as alert, checking for updates', str(incident['name']))
                alert_found = results[0]
                
                #Check if alert is already created, but needs updating
                if check_if_updated(alert_found, vars(theHiveAlert)):
                    logger.info("Found changes for %s, updating alert" % alert_found['id'])
                    
                    #update alert
                    theHiveConnector.updateAlert(alert_found['id'], theHiveAlert, fields=["tags", "artifacts"])
                    incident_report['updated_alert_id'] = alert_found['id']
                    incident_report['sentinel_incident_id'] = incident['name']
                    incident_report['success'] = True
                else:
                    logger.info("No changes found for %s" % alert_found['id'])
                    continue
                #########################################################

    except Exception as e:

            logger.error('Failed to create alert from Azure Sentinel incident (retrieving incidents failed)', exc_info=True)
            report['success'] = False
            report['message'] = "%s: Failed to create alert from incident" % str(e)
    
    return report