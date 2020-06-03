from .model import Model


class AnalyzerDefinition(Model):

    def __init__(self, data):
        defaults = {
            'id': None,
            'name': None,
            'analyzerDefinitionId': None,
            'description': None,
            'version': None,
            'author': None,
            'url': None,
            'license': None,
            'basicConfig': None,
            'dataTypeList': [],
            'configurationItems': []
        }

        if data is None:
            data = dict(defaults)

        self.__dict__ = {k: v for k, v in data.items() if not k.startswith('_')}