from .model import Model


class Job(Model):

    def __init__(self, data):
        defaults = {
            'id': None,
            'organization': None,
            'analyzerId': None,
            'responderId': None,
            'analyzerDefinitionId': None,
            'analyzerName': None,
            'status': None,
            'dataType': None,
            'tlp': 1,
            'data': None,
            'parameters': {},
            'message': None,
            'startDate': None,
            'endDate': None,
            'date': None
        }

        if data is None:
            data = dict(defaults)

        self.__dict__ = {k: v for k, v in data.items() if not k.startswith('_')}
