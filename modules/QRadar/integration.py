#!/usr/bin/env python3
# -*- coding: utf8 -*-

import os
import sys
import logging
import copy
import json
import datetime
import re
from core.integration import Main
from modules.QRadar.connector import QRadarConnector
from modules.TheHive.connector import TheHiveConnector
from time import sleep

class Integration(Main):

    def init(self):
        super().__init__
        self.qradarConnector = QRadarConnector(self.cfg)
        self.theHiveConnector = TheHiveConnector(self.cfg)

    def enrichOffense(self, offense):

        self.enriched = copy.deepcopy(offense)

        self.artifacts = []

        self.enriched['offense_type_str'] = \
            self.qradarConnector.getOffenseTypeStr(offense['offense_type'])

        # Add the offense source explicitly
        if self.enriched['offense_type_str'] == 'Username':
            self.artifacts.append({'data': offense['offense_source'], 'dataType': 'username', 'message': 'Offense Source'})

        # Add the local and remote sources
        # scrIps contains offense source IPs
        self.srcIps = list()
        # dstIps contains offense destination IPs
        self.dstIps = list()
        # srcDstIps contains IPs which are both source and destination of offense
        self.srcDstIps = list()
        for ip in self.qradarConnector.getSourceIPs(self.enriched):
            self.srcIps.append(ip)

        for ip in self.qradarConnector.getLocalDestinationIPs(self.enriched):
            self.dstIps.append(ip)

        # making copies is needed since we want to
        # access and delete data from the list at the same time
        self.s = copy.deepcopy(self.srcIps)
        self.d = copy.deepcopy(self.dstIps)

        for srcIp in self.s:
            for dstIp in self.d:
                if srcIp == dstIp:
                    self.srcDstIps.append(srcIp)
                    self.srcIps.remove(srcIp)
                    self.dstIps.remove(dstIp)

        for ip in self.srcIps:
            self.artifacts.append({'data': ip, 'dataType': 'ip', 'message': 'Source IP', 'tags': ['QRadar', 'src']})
        for ip in self.dstIps:
            self.artifacts.append({'data': ip, 'dataType': 'ip', 'message': 'Local destination IP', 'tags': ['QRadar', 'dst']})
        for ip in self.srcDstIps:
            self.artifacts.append({'data': ip, 'dataType': 'ip', 'message': 'Source and local destination IP', 'tags': ['QRadar', 'src', 'dst']})

        # Parse offense types to add the offense source as an observable when a valid type is used
        for offense_type, extraction_config in self.cfg.get('QRadar', 'observables_in_offense_type', fallback={}).items():
            if self.enriched['offense_type_str'] == offense_type:
                if isinstance(extraction_config, str):
                    self.observable_type = extraction_config
                    self.artifacts.append({'data': self.enriched['offense_source'], 'dataType': self.observable_type, 'message': 'QRadar Offense source', 'tags': ['QRadar']})
                elif isinstance(extraction_config, list):
                    for extraction in extraction_config:
                        self.regex = re.compile(extraction['regex'])
                        self.matches = self.regex.findall(str(self.enriched['offense_source']))
                        if len(self.matches) > 0:
                            # if isinstance(found_observable, tuple): << Fix later loop through matches as well
                            for match_group, self.observable_type in extraction['match_groups'].items():
                                try:
                                    self.artifacts.append({'data': self.matches[0][match_group], 'dataType': self.observable_type, 'message': 'QRadar Offense Type based observable', 'tags': ['QRadar', 'offense_type']})
                                except Exception as e:
                                    self.logger.warning("Could not find match group {} in {}".format(match_group, self.enriched['offense_type_str']))
                else:
                    self.logger.error("Configuration for observables_in_offense_type is wrongly formatted. Please fix this to enable this functionality")

        # Add all the observables
        self.enriched['artifacts'] = self.artifacts

        # Add rule names to offense
        self.enriched['rules'] = self.qradarConnector.getRuleNames(offense)

        # waiting 1s to make sure the logs are searchable
        sleep(1)
        # adding the first 3 raw logs
        self.enriched['logs'] = self.qradarConnector.getOffenseLogs(self.enriched)

        return self.enriched

    def qradarOffenseToHiveAlert(self, offense):

        def getHiveSeverity(self, offense):
            # severity in TheHive is either low, medium or high
            # while severity in QRadar is from 1 to 10
            # low will be [1;4] => 1
            # medium will be [5;6] => 2
            # high will be [7;10] => 3
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
        self.tags = ['QRadar', 'Offense', 'Synapse']
        # Add the offense type as a tag
        if 'offense_type_str' in offense:
            self.tags.append("qr_offense_type: {}".format(offense['offense_type_str']))

        # Check if the automation ids need to be extracted
        if self.cfg.getboolean('QRadar', 'extract_automation_identifiers'):

            # Run the extraction function and add it to the offense data
            # Extract automation ids
            self.tags_extracted = self.tagExtractor(offense, self.cfg.get('QRadar', 'automation_fields'), self.cfg.get('QRadar', 'tag_regexes'))
            # Extract any possible name for a document on a knowledge base
            offense['use_case_names'] = self.tagExtractor(offense, self.cfg.get('QRadar', 'automation_fields'), self.cfg.get('QRadar', 'uc_kb_name_regexes'))
            if len(self.tags_extracted) > 0:
                self.tags.extend(self.tags_extracted)
            else:
                self.logger.info('No match found for offense %s', offense['id'])

        # Check if the mitre ids need to be extracted
        if self.cfg.getboolean('QRadar', 'extract_mitre_ids'):
            # Extract mitre tactics
            offense['mitre_tactics'] = self.tagExtractor(offense, ["rules"], ['[tT][aA]\d{4}'])
            if 'mitre_tactics' in offense:
                self.tags.extend(offense['mitre_tactics'])

            # Extract mitre techniques
            offense['mitre_techniques'] = self.tagExtractor(offense, ["rules"], ['[tT]\d{4}'])
            if 'mitre_techniques' in offense:
                self.tags.extend(offense['mitre_techniques'])

        if "categories" in offense:
            for cat in offense['categories']:
                self.tags.append(cat)

        self.defaultObservableDatatype = ['autonomous-system',
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

        self.artifacts = []
        for artifact in offense['artifacts']:
            # Add automation tagging and mitre tagging to observables
            if len(self.tags_extracted) > 0:
                artifact['tags'].extend(self.tags_extracted)
            if 'mitre_tactics' in offense:
                artifact['tags'].extend(offense['mitre_tactics'])
            if 'mitre_techniques' in offense:
                artifact['tags'].extend(offense['mitre_techniques'])

            if artifact['dataType'] in self.defaultObservableDatatype:
                self.hiveArtifact = self.theHiveConnector.craftAlertArtifact(dataType=artifact['dataType'], data=artifact['data'], message=artifact['message'], tags=artifact['tags'])
            else:
                artifact_tags = list()
                artifact_tags.append('type:' + artifact['dataType'])
                self.hiveArtifact = self.theHiveConnector.craftAlertArtifact(dataType='other', data=artifact['data'], message=artifact['message'], tags=self.tags)
            self.artifacts.append(self.hiveArtifact)

        # Retrieve the configured case_template
        self.qradarCaseTemplate = self.cfg.get('QRadar', 'case_template')

        # Build TheHive alert
        self.alert = self.theHiveConnector.craftAlert(
            "{}, {}".format(offense['id'], offense['description']),
            self.craftAlertDescription(offense),
            self.getHiveSeverity(offense),
            offense['start_time'],
            self.tags,
            2,
            'Imported',
            'internal',
            'QRadar_Offenses',
            str(offense['id']),
            self.artifacts,
            self.qradarCaseTemplate)

        return self.alert

    def validateRequest(self, request):
        if request.is_json:
            self.content = request.get_json()
            if 'timerange' in self.content:
                workflowReport = self.allOffense2Alert(self.content['timerange'])
                if self.workflowReport['success']:
                    return json.dumps(self.workflowReport), 200
                else:
                    return json.dumps(self.workflowReport), 500
            else:
                self.logger.error('Missing <timerange> key/value')
                return json.dumps({'sucess': False, 'message': "timerange key missing in request"}), 500
        else:
            self.logger.error('Not json request')
            return json.dumps({'sucess': False, 'message': "Request didn't contain valid JSON"}), 400

    def allOffense2Alert(self, timerange):
        """
        Get all openned offense created within the last
        <timerange> minutes and creates alerts for them in
        TheHive
        """
        self.logger.info('%s.allOffense2Alert starts', __name__)

        self.report = dict()
        self.report['success'] = True
        self.report['offenses'] = list()

        try:
            self.offensesList = self.qradarConnector.getOffenses(timerange)

            # each offenses in the list is represented as a dict
            # we enrich this dict with additional details
            for offense in self.offensesList:
                self.matched = False
                # Filter based on regexes in configuration
                for offense_exclusion_regex in self.cfg.get('QRadar', 'offense_exclusion_regexes', fallback=[]):
                    self.logger.debug("Offense exclusion regex found '{}'. Matching against offense {}".format(offense_exclusion_regex, offense['id']))
                    self.regex = re.compile(offense_exclusion_regex)
                    if self.regex.match(offense['description']):
                        self.logger.debug("Found exclusion match for offense {} and regex {}".format(offense['id'], offense_exclusion_regex))
                        self.matched = True
                if self.matched:
                    continue

                # Prepare new alert
                self.offense_report = dict()
                self.logger.debug("offense: %s" % offense)
                self.logger.info("Enriching offense...")
                self.enrichedOffense = self.enrichOffense(offense)
                self.logger.debug("Enriched offense: %s" % self.enrichedOffense)
                self.theHiveAlert = self.qradarOffenseToHiveAlert(self.enrichedOffense)

                # searching if the offense has already been converted to alert
                q = dict()
                q['sourceRef'] = str(offense['id'])
                self.logger.info('Looking for offense %s in TheHive alerts', str(offense['id']))
                self.results = self.theHiveConnector.findAlert(q)
                if len(self.results) == 0:
                    self.logger.info('Offense %s not found in TheHive alerts, creating it', str(offense['id']))

                    try:
                        self.theHiveEsAlertId = self.theHiveConnector.createAlert(self.theHiveAlert)['id']

                        self.offense_report['raised_alert_id'] = self.theHiveEsAlertId
                        self.offense_report['qradar_offense_id'] = offense['id']
                        self.offense_report['success'] = True

                    except Exception as e:
                        self.logger.error('%s.allOffense2Alert failed', __name__, exc_info=True)
                        self.offense_report['success'] = False
                        if isinstance(e, ValueError):
                            self.errorMessage = json.loads(str(e))['message']
                            self.offense_report['message'] = self.errorMessage
                        else:
                            self.offense_report['message'] = str(e) + ": Couldn't raise alert in TheHive"
                        self.offense_report['offense_id'] = offense['id']
                        # Set overall success if any fails
                        self.report['success'] = False

                    self.report['offenses'].append(self.offense_report)
                else:
                    self.logger.info('Offense %s already imported as alert, checking for updates', str(offense['id']))
                    self.alert_found = self.results[0]

                    # Check if alert is already created, but needs updating
                    if self.check_if_updated(self.alert_found, vars(self.theHiveAlert)):
                        self.logger.info("Found changes for %s, updating alert" % self.alert_found['id'])

                        # update alert
                        self.theHiveConnector.updateAlert(self.alert_found['id'], self.theHiveAlert, fields=["tags", "artifacts"])
                        self.offense_report['updated_alert_id'] = self.alert_found['id']
                        self.offense_report['qradar_offense_id'] = offense['id']
                        self.offense_report['success'] = True
                    else:
                        self.logger.info("No changes found for %s" % self.alert_found['id'])
                        continue
                    ##########################################################

        except Exception as e:
            self.logger.error('Failed to create alert from QRadar offense (retrieving offenses failed)', exc_info=True)
            self.report['success'] = False
            self.report['message'] = "%s: Failed to create alert from offense" % str(e)

        return self.report

    def craftAlertDescription(self, offense):
        """
            From the offense metadata, crafts a nice description in markdown
            for TheHive
        """
        self.logger.debug('craftAlertDescription starts')

        # Start empty
        self.description = ""

        # Add url to Offense
        self.qradar_ip = self.cfg.get('QRadar', 'server')
        self.url = ('[%s](https://%s/console/qradar/jsp/QRadar.jsp?appName=Sem&pageId=OffenseSummary&summaryId=%s)' % (str(offense['id']), self.qradar_ip, str(offense['id'])))

        self.description += '#### Offense: \n - ' + self.url + '\n\n'

        # Format associated rules
        self.rule_names_formatted = "#### Rules triggered: \n"
        self.rules = offense['rules']
        if len(self.rules) > 0:
            for rule in self.rules:
                if 'name' in rule:
                    self.rule_names_formatted += "- %s \n" % rule['name']
                else:
                    continue

        # Add rules overview to description
        self.description += self.rule_names_formatted + '\n\n'

        # Format associated documentation
        self.uc_links_formatted = "#### Use Case documentation: \n"
        if 'use_case_names' in offense and offense['use_case_names']:
            for uc in offense['use_case_names']:
                self.uc_links_formatted += "- [%s](%s/%s) \n" % (uc, self.cfg.get('QRadar', 'kb_url'), uc)

            # Add associated documentation
            self.description += self.uc_links_formatted + '\n\n'

        # Add mitre Tactic information
        self.mitre_ta_links_formatted = "#### MITRE Tactics: \n"
        if 'mitre_tactics' in offense and offense['mitre_tactics']:
            for tactic in offense['mitre_tactics']:
                self.mitre_ta_links_formatted += "- [%s](%s/%s) \n" % (tactic, 'https://attack.mitre.org/tactics/', tactic)

            # Add associated documentation
            self.description += self.mitre_ta_links_formatted + '\n\n'

        # Add mitre Technique information
        self.mitre_t_links_formatted = "#### MITRE Techniques: \n"
        if 'mitre_techniques' in offense and offense['mitre_techniques']:
            for technique in offense['mitre_techniques']:
                self.mitre_t_links_formatted += "- [%s](%s/%s) \n" % (technique, 'https://attack.mitre.org/techniques/', technique)

            # Add associated documentation
            self.description += self.mitre_t_links_formatted + '\n\n'

        # Add offense details table
        self.description += (
            '#### Summary\n\n' +
            '|                         |               |\n' +
            '| ----------------------- | ------------- |\n' +
            '| **Start Time**          | ' + str(self.qradarConnector.formatDate(offense['start_time'])) + ' |\n' +
            '| **Offense ID**          | ' + str(offense['id']) + ' |\n' +
            '| **Description**         | ' + str(offense['description'].replace('\n', '')) + ' |\n' +
            '| **Offense Type**        | ' + str(offense['offense_type_str']) + ' |\n' +
            '| **Offense Source**      | ' + str(offense['offense_source']) + ' |\n' +
            '| **Destination Network** | ' + str(offense['destination_networks']) + ' |\n' +
            '| **Source Network**      | ' + str(offense['source_network']) + ' |\n\n\n' +
            '\n\n\n\n')

        # Add raw payload
        self.description += '```\n'
        for log in offense['logs']:
            self.description += log['utf8_payload'] + '\n'
        self.description += '```\n\n'

        return self.description
