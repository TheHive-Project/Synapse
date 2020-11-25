import json
import logging
import itertools
import os
import sys
import time
from thehive4py.query import In

from modules.Lexsi.connector import LexsiConnector
from modules.TheHive.connector import TheHiveConnector

from core.integration import Main


# Get logger
logger = logging.getLogger(__name__)

class Integration(Main):

    def __init__(self):
        super().__init__()
        self.lexsi = LexsiConnector(self.cfg)
        self.theHiveConnector = TheHiveConnector(self.cfg)

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
        Get all opened incidents created within lexsi
        and create alerts for them in TheHive
        """
        self.logger.info('%s.allincident2Alert starts', __name__)

        self.incidentsList = self.lexsi.getOpenItems()['result']

        self.report = dict()
        self.report['success'] = True
        self.report['incidents'] = list()

        try:
            # each incidents in the list is represented as a dict
            # we enrich this dict with additional details
            for incident in self.incidentsList:

                # Prepare new alert
                self.incident_report = dict()
                self.logger.debug("incident: %s" % incident)

                self.theHiveAlert = self.IncidentToHiveAlert(incident)

                # searching if the incident has already been converted to alert
                self.query = dict()
                self.query['sourceRef'] = str(incident['incident'])
                self.logger.info('Looking for incident %s in TheHive alerts', str(incident['incident']))
                self.results = self.theHiveConnector.findAlert(self.query)
                if len(self.results) == 0:
                    self.logger.info('incident %s not found in TheHive alerts, creating it', str(incident['incident']))
                    try:

                        self.theHiveEsAlertId = self.theHiveConnector.createAlert(self.theHiveAlert)['id']
                        self.theHiveConnector.promoteCaseToAlert(self.theHiveEsAlertId)

                        self.incident_report['raised_alert_id'] = self.theHiveEsAlertId
                        self.incident_report['lexsi_incident_id'] = incident['incident']
                        self.incident_report['success'] = True

                    except Exception as e:
                        self.logger.error(self.incident_report)
                        self.logger.error('%s.allincident2Alert failed', __name__, exc_info=True)
                        self.incident_report['success'] = False
                        if isinstance(e, ValueError):
                            errorMessage = json.loads(str(e))['message']
                            self.incident_report['message'] = errorMessage
                        else:
                            self.incident_report['message'] = str(e) + ": Couldn't raise alert in TheHive"
                        self.incident_report['incident_id'] = incident['incident']
                        # Set overall success if any fails
                        self.report['success'] = False

                    self.report['incidents'].append(self.incident_report)
                else:
                    self.logger.info('incident %s already imported as alert, checking for updates', str(incident['incident']))
                    self.alert_found = self.results[0]

                    # Check if alert is already created, but needs updating
                    if self.check_if_updated(self.alert_found, vars(self.theHiveAlert)):
                        self.logger.info("Found changes for %s, updating alert" % self.alert_found['id'])

                        # update alert
                        self.theHiveConnector.updateAlert(self.alert_found['id'], self.theHiveAlert, fields=["tags", "artifacts"])

                        # Mark the alert as read
                        self.theHiveConnector.markAlertAsRead(self.alert_found['id'])

                        self.incident_report['updated_alert_id'] = self.alert_found['id']
                        self.incident_report['lexsi_incident_id'] = incident['incident']
                        self.incident_report['success'] = True
                    else:
                        self.logger.info("No changes found for %s" % self.alert_found['id'])
                        continue

            self.thehiveAlerts = self.lexsi_opened_alerts_thehive()
            self.set_alert_status_ignored(self.incidentsList)

        except Exception as e:

            self.logger.error('Failed to create alert from Lexsi incident (retrieving incidents failed)', exc_info=True)
            self.report['success'] = False
            self.report['message'] = "%s: Failed to create alert from incident" % str(e)

        return self.report

    def IncidentToHiveAlert(self, incident):

        #
        # Creating the alert
        #

        # Setup Tags
        self.tags = ['Lexsi', 'incident', 'Synapse']

        # Skip for now
        self.artifacts = []

        # Retrieve the configured case_template
        self.CaseTemplate = self.cfg.get('Lexsi', 'case_template')

        # Build TheHive alert
        self.alert = self.theHiveConnector.craftAlert(
            "{}: {}".format(incident['incident'], incident['title']),
            self.craftAlertDescription(incident),
            self.getHiveSeverity(incident),
            self.timestamp_to_epoch(incident['detected'], "%Y-%m-%d %H:%M:%S"),
            self.tags,
            2,
            'New',
            'internal',
            'Lexsi',
            str(incident['incident']),
            self.artifacts,
            self.CaseTemplate)

        return self.alert

    def craftAlertDescription(self, incident):
        """
            From the incident metadata, crafts a nice description in markdown
            for TheHive
        """
        self.logger.debug('craftAlertDescription starts')

        # Start empty
        self.description = ""

        # Add incident details table
        self.description += (
            '#### Summary\n\n' +
            '|                         |               |\n' +
            '| ----------------------- | ------------- |\n' +
            '| **URL**          | ' + "{}{}{}".format("```", str(incident['url']), "```") + ' |\n' +
            '| **Type**          | ' + str(incident['type']) + ' |\n' +
            '| **Severity**          | ' + str(incident['severity']) + ' |\n' +
            '| **Category**         | ' + str(incident['category']) + ' |\n' +
            '| **Updated**        | ' + str(incident['updated']) + ' |\n' +
            '| **Detected**        | ' + str(incident['detected']) + ' |\n' +
            '| **Source**        | ' + str(incident['source']) + ' |\n' +
            '| **Analyst Name(Lexsi)**        | ' + str(incident['analystName']) + ' |\n' +
            '| **Link to Orange Portal**        | ' + str("https://cert.orangecyberdefense.com/#cyb/alerts/{}".format(incident['incident'])) + ' |\n' +
            '\n\n\n\n')

        return self.description

    def timestamp_to_epoch(self, date_time, pattern):
        return int(time.mktime(time.strptime(date_time, pattern))) * 1000

    def getHiveSeverity(self, incident):
        # severity in TheHive is either low, medium, high or critical
        # while severity in Lexsi is from 0 to 5
        if int(incident['severity']) in {0, 5}:
            return 1
        # elif int(incident['severity']) in {2,3}:
        #    return 2
        # elif int(incident['severity']) in {4,5}:
        #    return 3

    def lexsi_opened_alerts_thehive(self):
        self.thehiveAlerts = []
        self.query = In('tags', ['Lexsi'])

        self.logger.info('Looking for incident in TheHive alerts with tag Lexsi')
        # self.logger.info(self.query)
        self.results = self.theHiveConnector.findAlert(self.query)
        for i in self.results:
            self.thehiveAlerts.append(i['sourceRef'])
        self.logger.info("Lexsi Alerts opened in theHive: {}".format(self.thehiveAlerts))
        return self.thehiveAlerts

    def compare_lists(self, list1, list2):
        return list(set(list1) - set(list2))

    def set_alert_status_ignored(self, incidentsList):
        self.lexsi_reporting = []
        # self.incidentsList = self.lexsi.getOpenItems()['result']

        for incident in incidentsList:
            self.lexsi_reporting.append(incident['incident'])

        self.logger.info("the list of opened Lexsi Incidents: {}".format(self.lexsi_reporting))
        self.uncommon_elements = self.compare_lists(self.thehiveAlerts, self.lexsi_reporting)
        # self.uncommon_elements=['476121']
        self.logger.info("Alerts present in TheHive but not in list of opened Lexsi Incidents: {}".format((self.uncommon_elements)))

        for element in self.uncommon_elements:
            self.logger.info("Preparing to change the status for {}".format(element))
            self.query = dict()
            self.query['sourceRef'] = str(element)
            self.logger.info('Looking for incident %s in TheHive alerts', str(element))
            self.alert = self.theHiveConnector.findAlert(self.query)[0]
            if 'case' in self.alert:
                try:
                    # Resolve the case
                    self.logger.info("AlertID for element {}: {}".format(element, self.case_id))
                    self.case_id = self.alert['case']
                    self.logger.info("Preparing to resolve the case")
                    self.theHiveConnector.closeCase(self.case_id)

                except Exception as e:
                    self.logger.debug(e)
                    continue
