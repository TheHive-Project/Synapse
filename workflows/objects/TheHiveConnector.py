#!/usr/bin/env python3
# -*- coding: utf8 -*-

import logging
import json

from thehive4py.client import TheHiveApi
from thehive4py.client import TheHiveApi
from thehive4py.errors import TheHiveError
from thehive4py.helpers import now_to_ts
from thehive4py.query.filters import Eq
from thehive4py.query.sort import Asc
from thehive4py.types.alert import OutputAlert
from thehive4py.types.case import (
    CaseStatus,
    ImpactStatus,
    InputBulkUpdateCase,
    InputUpdateCase,
    OutputCase,
)
from thehive4py.types.observable import InputObservable
from thehive4py.types.share import InputShare


class TheHiveConnector:
    'TheHive connector'

    def __init__(self, cfg):
        self.logger = logging.getLogger('workflows.' + __name__)
        self.cfg = cfg

        self.theHiveApi = self.connect()

    def connect(self):
        self.logger.info('%s.connect starts', __name__)

        url = self.cfg.get('TheHive', 'url')
        api_key = self.cfg.get('TheHive', 'api_key')

        return TheHiveApi(url, api_key)

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
        json_case = {'title':title,'description':description,'tags':['Synapse'],'severity':1}
        return json_case

    def createCase(self, case):
        self.logger.info('%s.createCase starts', __name__)
        created_case = self.theHiveApi.case.create(case)
        fetched_case = self.theHiveApi.case.get(created_case["_id"])
        if created_case == fetched_case:
            return created_case
        else:
            self.logger.error('Case creation failed')
            raise ValueError(json.dumps({'message':'Failed to Create a new Case !'}))

    def assignCase(self, case, assignee):
        self.logger.info('%s.assignCase starts', __name__)
        update_fields: InputUpdateCase = {'assignee':assignee}
        updatedCase = self.theHiveApi.case.update(case_id=case['_id'], case=update_fields)
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


    def craftTaskLog(self, textLog):
        self.logger.info('%s.craftTaskLog starts', __name__)

        log = CaseTaskLog(message=textLog)

        return log

    def addTaskLog(self, esTaskId, textLog):
        self.logger.info('%s.addTaskLog starts', __name__)
        response = self.theHiveApi.task_log.create(task_id=esTaskId,task_log={"message": textLog})
        fetched_log = self.theHiveApi.task_log.get(task_log_id=response["_id"])
        if response == fetched_log:
            return response
        else:
            self.logger.error('Task log creation failed')
            raise ValueError(json.dumps({'message':'Task log creation failed'}))

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
        json_alert = {
            "type": type,
            "source": source,
            "sourceRef": sourceRef,
            "title": title,
            "description": description,
            "severity": severity,
            "date": date,
            "status": "New",
            "tags": tags,
            "tlp": tlp,
            "caseTemplate": caseTemplate,
            "observables": artifacts}

        return json_alert

    def createAlert(self, alert):
        self.logger.info('%s.createAlert starts', __name__)
        self.logger.info(alert)
        try:
            response = self.theHiveApi.alert.create(alert)
        except Exception as e:
            if 'CreateError' in str(e):
                self.logger.info('%s.createAlert starts failed', __name__)
            else:
                return response


    def findAlert(self, q):
        """
            Search for alerts in TheHive for a given query

            :param q: TheHive query
            :return : JSON
        """

        self.logger.info('%s.findAlert starts', __name__)

        response = self.theHiveApi.alert.find(q)
        self.logger.info(q)
        self.logger.info(response)
        if len(response) > 0:
            response = response[0]
            results = response
            return results
        else:
            self.logger.error('findAlert failed')
            return 0

    def findFirstMatchingTemplate(self, searchstring):
        self.logger.info('%s.findFirstMatchingTemplate starts', __name__)

        query = Eq('status', 'Ok')
        allTemplates = self.theHiveApi.find_case_templates(query=query)
        if allTemplates.status_code != 200:
            raise ValueError('Could not find matching template !')

        for template in allTemplates.json():
            if searchstring in template['name']:
                return template

        return None