from .model import Model


class JobArtifact(Model):

    def __init__(self, data):
        defaults = {
            'id': None,
            'tlp': None,
            'dataType': None,
            'data': None
        }

        if data is None:
            data = dict(defaults)

        self.__dict__ = {k: v for k, v in data.items() if not k.startswith('_')}