#!/usr/bin/env python3
# -*- coding: utf8 -*-

import logging
import json
# Only required to extend TheHiveApi
import requests

from thehive4py.api import TheHiveApi
from thehive4py.models import Case, CaseTask, CaseTaskLog, CaseObservable, AlertArtifact, Alert
from thehive4py.query import Eq

# Only required to extend TheHiveApi
from thehive4py.exceptions import TheHiveException, AlertException

class TheHiveExtendedApi(TheHiveApi):
    """ This is a class that adds a few very basic capabilities to
    theHive4py. Unfortunately at time of writing the library was
    going through a rewrite, so hopefully this will not be needed
    soon. This is not typically a good idea and is only temporary
    until the upstream library is changed."""

    def promote_alert_to_case(self, alertId):
        #pylint:disable=C0103
        """ This uses the TheHiveAPI to promote an alert to a case """

        req = self.url + "/api/alert/{}/createCase".format(alertId)

        try:
            return requests.post(req, headers={'Content-Type': 'application/json'},
                                 proxies=self.proxies, auth=self.auth,
                                 verify=self.cert, data=json.dumps({}))

        except requests.exceptions.RequestException as theException:
            raise AlertException("Couldn't promote alert to case: {}".format(theException))

        return None

    def find_case_templates(self, **attributes):
        #pylint:disable=C0103
        """ This uses TheHive API to allow searching for a template """
        find_url = "/api/case/template/_search"

        req = self.url + find_url

        # Add range and sort parameters
        params = {
            "range": attributes.get("range", "all"),
            "sort": attributes.get("sort", [])
        }

        # Add body
        data = {
            "query": attributes.get("query", {})
        }

        try:
            return requests.post(req, params=params, json=data,
                                 proxies=self.proxies, auth=self.auth,
                                 verify=self.cert)

        except requests.exceptions.RequestException as theException:
            raise TheHiveException("Error: {}".format(theException))

class TheHiveConnector:
    'TheHive connector'

    def __init__(self, cfg):
        self.logger = logging.getLogger('workflows.' + __name__)
        self.cfg = cfg

        self.theHiveApi = self.connect()

    def connect(self):
        """ This returns a hive connection """

        self.logger.info('%s.connect starts', __name__)

        url = self.cfg.get('TheHive', 'url')
        apiKey = self.cfg.get('TheHive', 'api_key')

        return TheHiveExtendedApi(url, apiKey)

    def findFirstMatchingTemplate(self, searchstring):

        query = Eq("status", "Ok")
        allTemplates = self.theHiveApi.find_case_templates(query=query)
        if allTemplates.status_code != 200:
            raise ValueError("Couldn't find matching template!")

        for template in allTemplates.json():
            if searchstring in template['name']:
                return template

        return None

    def searchCaseByDescription(self, string):
        #search case with a specific string in description
        #returns the ES case ID

        self.logger.info('%s.searchCaseByDescription starts', __name__)

        query = dict()
        query['_string'] = 'description:"{}"'.format(string)
        range = 'all'
        sort = []
        response = self.theHiveApi.find_cases(query=query, range=range, sort=sort)

        if response.status_code != 200:
            error = dict()
            error['message'] = 'search case failed'
            error['query'] = query
            error['payload'] = response.json()
            self.logger.error('Query to TheHive API did not return 200')
            raise ValueError(json.dumps(error, indent=4, sort_keys=True))

        if len(response.json()) == 1:
            #one case matched
            esCaseId = response.json()[0]['id']
            return esCaseId
        elif len(response.json()) == 0:
            #no case matched
            return None
        else:
            #unknown use case
            raise ValueError('unknown use case after searching case by description')


    def craftCase(self, title, description):
        self.logger.info('%s.craftCase starts', __name__)

        case = Case(title=title,
            tlp=2,
            tags=['Synapse'],
            description=description,
            )

        return case

    def createCase(self, case):
        self.logger.info('%s.createCase starts', __name__)

        response = self.theHiveApi.create_case(case)

        if response.status_code == 201:
            esCaseId =  response.json()['id']
            createdCase = self.theHiveApi.case(esCaseId)
            return createdCase
        else:
            self.logger.error('Case creation failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))

    def assignCase(self, case, assignee):
        self.logger.info('%s.assignCase starts', __name__)

        esCaseId = case.id
        case.owner = assignee
        self.theHiveApi.update_case(case)

        updatedCase = self.theHiveApi.case(esCaseId)
        return updatedCase

    def craftCommTask(self):
        self.logger.info('%s.craftCommTask starts', __name__)

        commTask = CaseTask(title='Communication',
            status='InProgress',
            owner='synapse')

        return commTask

    def createTask(self, esCaseId, task):
        self.logger.info('%s.createTask starts', __name__)

        response = self.theHiveApi.create_case_task(esCaseId, task)

        if response.status_code == 201:
            esCreatedTaskId = response.json()['id']
            return esCreatedTaskId
        else:
            self.logger.error('Task creation failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))

    def craftAlertArtifact(self, **attributes):
        self.logger.info('%s.craftAlertArtifact starts', __name__)

        alertArtifact = AlertArtifact(dataType=attributes["dataType"], message=attributes["message"], data=attributes["data"])

        return alertArtifact

    def craftTaskLog(self, textLog):
        self.logger.info('%s.craftTaskLog starts', __name__)

        log = CaseTaskLog(message=textLog)

        return log

    def addTaskLog(self, esTaskId, textLog):
        self.logger.info('%s.addTaskLog starts', __name__)

        response = self.theHiveApi.create_task_log(esTaskId, textLog)

        if response.status_code == 201:
            esCreatedTaskLogId = response.json()['id']
            return esCreatedTaskLogId
        else:
            self.logger.error('Task log creation failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))

    def getTaskIdByTitle(self, esCaseId, taskTitle):
        self.logger.info('%s.getTaskIdByName starts', __name__)

        response = self.theHiveApi.get_case_tasks(esCaseId)
        for task in response.json():
            if task['title'] == taskTitle:
                return task['id']

        #no <taskTitle> found
        return None

    def addFileObservable(self, esCaseId, filepath, comment):
        self.logger.info('%s.addFileObservable starts', __name__)

        file_observable = CaseObservable(dataType='file',
            data=[filepath],
            tlp=2,
            ioc=False,
            tags=['Synapse'],
            message=comment
        )

        response = self.theHiveApi.create_case_observable(
            esCaseId, file_observable)

        if response.status_code == 201:
            esObservableId = response.json()['id']
            return esObservableId
        else:
            self.logger.error('File observable upload failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))

    def craftAlert(self, title, description, severity, date, tags, tlp, status, type, source,
        sourceRef, artifacts, caseTemplate):
        self.logger.info('%s.craftAlert starts', __name__)

        alert = Alert(title=title,
            description=description,
            severity=severity,
            date=date,
            tags=tags,
            tlp=tlp,
            type=type,
            source=source,
            sourceRef=sourceRef,
            artifacts=artifacts,
            caseTemplate=caseTemplate)

        return alert

    def promoteAlertIdToCase(self, alertId):
        """ Given an alertid, try and promote the alert to a case """

        self.logger.info('%s.promoteAlertIdToCase starts', __name__)

        response = self.theHiveApi.promote_alert_to_case(alertId)

        if response.status_code == 201:
            return response.json()
        else:
            self.logger.error('Alert promotion failed (%s) %s',
                              response.status_code, response.text)
            raise ValueError('Alert promotion failed (%s) %s' %
                             (response.status_code, response.text))

    def promoteAlertToCase(self, alert):
        """ Given an Alert model, try and promote to case """
        return self.promoteAlertIdToCase(alert.id)

    def createAlert(self, alert):
        self.logger.info('%s.createAlert starts', __name__)

        response = self.theHiveApi.create_alert(alert)

        if response.status_code == 201:
            return response.json()
        else:
            self.logger.error('Alert creation failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))

    def findAlert(self, q):
        """
            Search for alerts in TheHive for a given query

            :param q: TheHive query
            :type q: dict

            :return results: list of dict, each dict describes an alert
            :rtype results: list
        """

        self.logger.info('%s.findAlert starts', __name__)

        response = self.theHiveApi.find_alerts(query=q)
        if response.status_code == 200:
            results = response.json()
            return results
        else:
            self.logger.error('findAlert failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))
