#!/usr/bin/env python3
# -*- coding: utf8 -*-

import logging
import json

from thehive4py.api import TheHiveApi
from thehive4py.models import Case, CaseTask, CaseTaskLog, CaseObservable, AlertArtifact, Alert
from thehive4py.query import Eq

class TheHiveConnector:
    'TheHive connector'

    def __init__(self, cfg):
        self.logger = logging.getLogger('workflows.' + __name__)
        self.cfg = cfg

        self.theHiveApi = self.connect()

    def connect(self):
        self.logger.debug('%s.connect starts', __name__)

        url = self.cfg.get('TheHive', 'url')
        api_key = self.cfg.get('TheHive', 'api_key')

        return TheHiveApi(url, api_key)

    def searchCaseByDescription(self, string):
        #search case with a specific string in description
        #returns the ES case ID

        self.logger.debug('%s.searchCaseByDescription starts', __name__)

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
            
    def getCase(self, caseid):
        self.logger.debug('%s.getCase starts', __name__)

        response = self.theHiveApi.get_case(caseid)

        if response.status_code == 200:
            return response.json()
        else:
            self.logger.error('Case not found')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))
            
    def getCaseObservable(self, artifactid):
        self.logger.debug('%s.getCaseObservable starts', __name__)

        response = self.theHiveApi.get_case_observable(artifactid)

        if response.status_code == 200:
            return response.json()
        else:
            self.logger.error('Artifact not found')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))

    def getCaseObservables(self, caseid):
        self.logger.debug('%s.getCaseObservables starts', __name__)

        response = self.theHiveApi.get_case_observables(caseid)

        if response.status_code == 200:
            return response
        else:
            self.logger.error('Case not found')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))
            
    def getCaseTasks(self, caseid):
        self.logger.debug('%s.getCaseTasks starts', __name__)

        response = self.theHiveApi.get_case_tasks(caseid)

        if response.status_code == 200:
            return response
        else:
            self.logger.error('Case not found')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))

    def craftCase(self, title, description):
        self.logger.debug('%s.craftCase starts', __name__)

        case = Case(title=title,
            tlp=2,
            tags=['Synapse'],
            description=description,
            )

        return case

    def createCase(self, case):
        self.logger.debug('%s.createCase starts', __name__)

        response = self.theHiveApi.create_case(case)

        if response.status_code == 201:
            esCaseId =  response.json()['id']
            createdCase = self.theHiveApi.case(esCaseId)
            return createdCase
        else:
            self.logger.error('Case creation failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))
            
    def promoteCaseToAlert(self, alert_id):
        self.logger.debug('%s.createCaseFromAlert starts', __name__)

        response = self.theHiveApi.promote_alert_to_case(alert_id)

        if response.status_code == 201:
            esCaseId =  response.json()['id']
            createdCase = self.theHiveApi.case(esCaseId)
            return createdCase
        else:
            self.logger.error('Case creation failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))
            
    def updateCase(self, case, fields):
        self.logger.debug('%s.updateCase starts', __name__)

        response = self.theHiveApi.update_case(case,fields)

        if response.status_code == 200:
            return response
        else:
            self.logger.error('Case update failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))

    def closeCase(self, caseid):
        self.logger.debug('%s.closeCase starts', __name__)
        #Create a Case object
        case = Case()
        case.id = caseid
        fields = ['status']
        case.status = "Resolved"
        #Update the case
        self.updateCase(case,fields)

    def assignCase(self, case, assignee):
        self.logger.debug('%s.assignCase starts', __name__)

        esCaseId = case.id
        case.owner = assignee
        self.theHiveApi.update_case(case)

        updatedCase = self.theHiveApi.case(esCaseId)
        return updatedCase

    def craftCommTask(self):
        self.logger.debug('%s.craftCommTask starts', __name__)

        commTask = CaseTask(title='Communication',
            status='InProgress',
            owner='synapse')

        return commTask

    def createTask(self, esCaseId, task):
        self.logger.debug('%s.createTask starts', __name__)

        response = self.theHiveApi.create_case_task(esCaseId, task)

        if response.status_code == 201:
            esCreatedTaskId = response.json()['id']
            return esCreatedTaskId
        else:
            self.logger.error('Task creation failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))

    def craftAlertArtifact(self, **attributes):
        self.logger.debug('%s.craftAlertArtifact starts', __name__)

        alertArtifact = AlertArtifact(dataType=attributes["dataType"], message=attributes["message"], data=attributes["data"], tags=attributes['tags'], tlp=attributes['tlp'])

        return alertArtifact

    def craftTaskLog(self, textLog):
        self.logger.debug('%s.craftTaskLog starts', __name__)

        log = CaseTaskLog(message=textLog)

        return log

    def addTaskLog(self, esTaskId, textLog):
        self.logger.debug('%s.addTaskLog starts', __name__)

        response = self.theHiveApi.create_task_log(esTaskId, textLog)

        if response.status_code == 201:
            esCreatedTaskLogId = response.json()['id']
            return esCreatedTaskLogId
        else:
            self.logger.error('Task log creation failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))

    def getTaskIdByTitle(self, esCaseId, taskTitle):
        self.logger.debug('%s.getTaskIdByName starts', __name__)

        response = self.theHiveApi.get_case_tasks(esCaseId)
        for task in response.json():
            if task['title'] == taskTitle:
                return task['id']

        #no <taskTitle> found
        return None

    def addFileObservable(self, esCaseId, filepath, comment):
        self.logger.debug('%s.addFileObservable starts', __name__)

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
        self.logger.debug('%s.craftAlert starts', __name__)

        alert = Alert(title=title,
            description=description,
            severity=severity,
            date=date,
            tags=tags,
            tlp=tlp,
            status=status,
            type=type,
            source=source,
            sourceRef=sourceRef,
            artifacts=artifacts,
            caseTemplate=caseTemplate)

        return alert

    def createAlert(self, alert):
        self.logger.debug('%s.createAlert starts', __name__)

        response = self.theHiveApi.create_alert(alert)

        if response.status_code == 201:
            return response.json()
        else:
            self.logger.error('Alert creation failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))
            
    def updateAlert(self, alertid, alert, fields=[]):
        self.logger.debug('%s.updateAlert starts', __name__)

        response = self.theHiveApi.update_alert(alertid, alert, fields=fields)

        if response.status_code == 200:
            return response.json()
        else:
            self.logger.error('Alert update failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))

    def markAlertAsRead(self, alert_id):
        
        self.logger.debug('%s.markAlertAsRead starts', __name__)

        response = self.theHiveApi.mark_alert_as_read(alert_id)

        if int(response.status_code) in {200,201,202,203,204,205}:
            return response.json()
        else:
            self.logger.error('Could not set alert as read')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))

    def getAlert(self, alert_id):
        self.logger.debug('%s.getAlert starts', __name__)

        response = self.theHiveApi.get_alert(alert_id)

        if response.status_code == 200:
            return response.json()
        else:
            self.logger.error('Case not found')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))
    
    def findAlert(self, q):
        """
            Search for alerts in TheHive for a given query

            :param q: TheHive query
            :type q: dict

            :return results: list of dict, each dict describes an alert
            :rtype results: list
        """

        self.logger.debug('%s.findAlert starts', __name__)

        response = self.theHiveApi.find_alerts(query=q)
        if response.status_code == 200:
            results = response.json()
            return results
        else:
            self.logger.error('findAlert failed')
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))

    def findFirstMatchingTemplate(self, searchstring):
        self.logger.debug('%s.findFirstMatchingTemplate starts', __name__)

        query = Eq('status', 'Ok')
        allTemplates = self.theHiveApi.find_case_templates(query=query)
        if allTemplates.status_code != 200:
            raise ValueError('Could not find matching template !')

        for template in allTemplates.json():
            if searchstring in template['name']:
                return template

        return None
        
    def runAnalyzer(self, cortex_server, observable, analyzer):
        self.logger.debug('%s.runAnalyzer starts', __name__)

        response = self.theHiveApi.run_analyzer(cortex_server, observable, analyzer)

        if response.status_code == 200:
            return response.json()
        else:
            self.logger.error('Running Analyzer %s failed' % analyzer)
            raise ValueError(json.dumps(response.json(), indent=4, sort_keys=True))
