from .model import Model


class Organization(Model):

    def __init__(self, data):
        defaults = {
            'id': None,
            'name': None,
            'description': None,
            'status': None
        }

        if data is None:
            data = dict(defaults)

        self.__dict__ = {k: v for k, v in data.items() if not k.startswith('_')}
