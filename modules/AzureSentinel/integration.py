import json
import logging
from core.integration import Main
from modules.AzureSentinel.connector import AzureSentinelConnector
from modules.TheHive.connector import TheHiveConnector

class Integration(Main):

    def __init__(self):
        super().__init__()
        self.azureSentinelConnector = AzureSentinelConnector(self.cfg)
        self.theHiveConnector = TheHiveConnector(self.cfg)

    def craftAlertDescription(self, incident):
        """
            From the incident metadata, crafts a nice description in markdown
            for TheHive
        """
        self.logger.debug('craftAlertDescription starts')

        # Start empty
        self.description = ""

        # Add url to incident
        self.url = ('[%s](%s)' % (str(incident['properties']['incidentNumber']), str(incident['properties']['incidentUrl'])))
        self.description += '#### Incident: \n - ' + self.url + '\n\n'

        # Format associated rules
        self.rule_names_formatted = "#### Rules triggered: \n"
        self.rules = incident['properties']['relatedAnalyticRuleIds']
        if len(self.rules) > 0:
            for rule in self.rules:
                self.rule_info = self.azureSentinelConnector.getRule(rule)
                self.logger.debug('Received the following rule information: {}'.format(self.rule_info))
                self.rule_name = self.rule_info['properties']['displayName']
                rule_url = "https://management.azure.com{}".format(rule)
                self.rule_names_formatted += "- %s \n" % (self.rule_name)

        # Add rules overview to description
        self.description += self.rule_names_formatted + '\n\n'

        # Add mitre Tactic information
        # https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json

        # mitre_ta_links_formatted = "#### MITRE Tactics: \n"
        # if 'mitre_tactics' in offense and offense['mitre_tactics']:
        #     for tactic in offense['mitre_tactics']:
        #         mitre_ta_links_formatted += "- [%s](%s/%s) \n" % (tactic, 'https://attack.mitre.org/tactics/', tactic)

        #     #Add associated documentation
        #     self.description += mitre_ta_links_formatted + '\n\n'

        # #Add mitre Technique information
        # mitre_t_links_formatted = "#### MITRE Techniques: \n"
        # if 'mitre_techniques' in offense and offense['mitre_techniques']:
        #     for technique in offense['mitre_techniques']:
        #         mitre_t_links_formatted += "- [%s](%s/%s) \n" % (technique, 'https://attack.mitre.org/techniques/', technique)

        # Add a custom description when the incident does not contain any
        if 'description' not in incident['properties']:
            incident['properties']['description'] = "N/A"

        # Add incident details table
        self.description += (
            '#### Summary\n\n' +
            '|                         |               |\n' +
            '| ----------------------- | ------------- |\n' +
            '| **Start Time**          | ' + str(self.azureSentinelConnector.formatDate("description", incident['properties']['createdTimeUtc'])) + ' |\n' +
            '| **incident ID**          | ' + str(incident['properties']['incidentNumber']) + ' |\n' +
            '| **Description**         | ' + str(incident['properties']['description'].replace('\n', '')) + ' |\n' +
            '| **incident Type**        | ' + str(incident['type']) + ' |\n' +
            '| **incident Source**      | ' + str(incident['properties']['additionalData']['alertProductNames']) + ' |\n' +
            '| **incident Status**      | ' + str(incident['properties']['status']) + ' |\n' +
            '\n\n\n\n')

        return self.description

    def sentinelIncidentToHiveAlert(self, incident):

        def getHiveSeverity(incident):
            # severity in TheHive is either low, medium or high
            # while severity in Sentinel is from Low to High
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
        self.tags = ['AzureSentinel', 'incident', 'Synapse']

        # Skip for now
        self.artifacts = []

        # Retrieve the configured case_template
        self.sentinelCaseTemplate = self.cfg.get('AzureSentinel', 'case_template')

        # Build TheHive alert
        self.alert = self.theHiveConnector.craftAlert(
            "{}, {}".format(incident['properties']['incidentNumber'], incident['properties']['title']),
            self.craftAlertDescription(incident),
            getHiveSeverity(incident),
            self.azureSentinelConnector.formatDate("alert_timestamp", incident['properties']['createdTimeUtc']),
            self.tags,
            2,
            'New',
            'internal',
            'Azure_Sentinel_incidents',
            str(incident['name']),
            self.artifacts,
            self.sentinelCaseTemplate)

        return self.alert

    def validateRequest(self, request):
        if request.is_json:
            self.content = request.get_json()
            if 'type' in self.content and self.content['type'] == "Active":
                self.workflowReport = self.allIncidents2Alert(self.content['type'])
                if self.workflowReport['success']:
                    return json.dumps(self.workflowReport), 200
                else:
                    return json.dumps(self.workflowReport), 500
            else:
                self.logger.error('Missing type or type is not supported')
                return json.dumps({'sucess': False, 'message': "Missing type or type is not supported"}), 500
        else:
            self.logger.error('Not json request')
            return json.dumps({'sucess': False, 'message': "Request didn't contain valid JSON"}), 400

    def allIncidents2Alert(self, status):
        """
        Get all opened incidents created within Azure Sentinel
        and create alerts for them in TheHive
        """
        self.logger.info('%s.allincident2Alert starts', __name__)

        self.report = dict()
        self.report['success'] = True
        self.report['incidents'] = list()

        try:
            self.incidentsList = self.azureSentinelConnector.getIncidents()

            # each incidents in the list is represented as a dict
            # we enrich this dict with additional details
            for incident in self.incidentsList:

                # Prepare new alert
                self.incident_report = dict()
                self.logger.debug("incident: %s" % incident)
                # self.logger.info("Enriching incident...")
                # enrichedincident = enrichIncident(incident)
                # self.logger.debug("Enriched incident: %s" % enrichedincident)
                self.theHiveAlert = self.sentinelIncidentToHiveAlert(incident)

                # searching if the incident has already been converted to alert
                self.query = dict()
                self.query['sourceRef'] = str(incident['name'])
                self.logger.info('Looking for incident %s in TheHive alerts', str(incident['name']))
                self.results = self.theHiveConnector.findAlert(self.query)
                if len(self.results) == 0:
                    self.logger.info('incident %s not found in TheHive alerts, creating it', str(incident['name']))

                    try:
                        self.theHiveEsAlertId = self.theHiveConnector.createAlert(self.theHiveAlert)['id']

                        self.incident_report['raised_alert_id'] = self.theHiveEsAlertId
                        self.incident_report['sentinel_incident_id'] = incident['name']
                        self.incident_report['success'] = True

                    except Exception as e:
                        self.logger.error('%s.allincident2Alert failed', __name__, exc_info=True)
                        self.incident_report['success'] = False
                        if isinstance(e, ValueError):
                            errorMessage = json.loads(str(e))['message']
                            self.incident_report['message'] = errorMessage
                        else:
                            self.incident_report['message'] = str(e) + ": Couldn't raise alert in TheHive"
                        self.incident_report['incident_id'] = incident['name'] 
                        # Set overall success if any fails
                        self.report['success'] = False

                    self.report['incidents'].append(self.incident_report)
                else:
                    self.logger.info('incident %s already imported as alert, checking for updates', str(incident['name']))
                    self.alert_found = self.results[0]

                    # Check if alert is already created, but needs updating
                    if self.check_if_updated(self.alert_found, vars(self.theHiveAlert)):
                        self.logger.info("Found changes for %s, updating alert" % self.alert_found['id'])

                        # update alert
                        self.theHiveConnector.updateAlert(self.alert_found['id'], self.theHiveAlert, fields=["tags", "artifacts"])
                        self.incident_report['updated_alert_id'] = self.alert_found['id']
                        self.incident_report['sentinel_incident_id'] = incident['name']
                        self.incident_report['success'] = True
                    else:
                        self.logger.info("No changes found for %s" % self.alert_found['id'])
                        continue

        except Exception as e:

            self.logger.error('Failed to create alert from Azure Sentinel incident (retrieving incidents failed)', exc_info=True)
            self.report['success'] = False
            self.report['message'] = "%s: Failed to create alert from incident" % str(e)

        return self.report
