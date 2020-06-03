import os

import magic
import json
from typing import List

from cortex4py.query import *
from .abstract import AbstractController
from ..models import Analyzer, Job, AnalyzerDefinition

class RespondersController(AbstractController):
    def __init__(self, api):
        AbstractController.__init__(self, 'analyzer', api)

    # def find_all(self, query, **kwargs) -> List[Analyzer]:
    #     return self._wrap(self._find_all(query, **kwargs), Analyzer)

    # def find_one_by(self, query, **kwargs) -> Analyzer:
    #     return self._wrap(self._find_one_by(query, **kwargs), Analyzer)

    # def get_by_id(self, analyzer_id) -> Analyzer:
    #     return self._wrap(self._get_by_id(analyzer_id), Analyzer)

    # def get_by_name(self, name) -> Analyzer:
    #     return self._wrap(self._find_one_by(Eq('name', name)), Analyzer)

    # def get_by_type(self, data_type) -> List[Analyzer]:
    #     return self._wrap(self._api.do_get('analyzer/type/{}'.format(data_type)).json(), Analyzer)

    # def definitions(self) -> List[AnalyzerDefinition]:
    #     return self._wrap(self._api.do_get('analyzerdefinition').json(), AnalyzerDefinition)

    # def enable(self, analyzer_name, config) -> Analyzer:
    #     url = 'organization/analyzer/{}'.format(analyzer_name)
    #     config['name'] = analyzer_name

    #     return self._wrap(self._api.do_post(url, config).json(), Analyzer)

    # def update(self, analyzer_id, config) -> Analyzer:
    #     url = 'analyzer/{}'.format(analyzer_id)
    #     config.pop('name', None)

    #     return self._wrap(self._api.do_patch(url, config).json(), Analyzer)

    # def disable(self, analyzer_id) -> bool:
    #     return self._api.do_delete('analyzer/{}'.format(analyzer_id))

    def run_by_id(self, responder_id, data, **kwargs) -> Job:
        tlp = data.get('tlp', 2)
        data_type = data.get('dataType', None)

        post = {
            'dataType': data_type,
            'tlp': tlp
        }

        params = {}
        if 'force' in kwargs:
            params['force'] = kwargs.get('force', 1)

        # add additional details
        for key in ['message', 'parameters']:
            if key in data:
                post[key] = data.get(key, None)
        
        post['data'] = data.get('data')

        return self._wrap(self._api.do_post('responder/{}/run'.format(responder_id), post, params).json(), Job)
