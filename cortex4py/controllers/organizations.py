from typing import List

from .abstract import AbstractController
from ..models import Organization, Analyzer, User


class OrganizationsController(AbstractController):
    def __init__(self, api):
        AbstractController.__init__(self, 'organization', api)

    def find_all(self, query, **kwargs) -> List[Organization]:
        return self._wrap(self._find_all(query, **kwargs), Organization)

    def find_one_by(self, query, **kwargs) -> Organization:
        return self._wrap(self._find_one_by(query, **kwargs), Organization)

    def get_by_id(self, org_id) -> Organization:
        return self._wrap(self._get_by_id(org_id), Organization)

    def get_users(self, organization_id, query, **kwargs):
        url = 'organization/{}/user/_search'.format(organization_id)
        params = dict((k, kwargs.get(k, None)) for k in ('sort', 'range'))

        return self._wrap(self._api.do_post(url, {'query': query or {}}, params).json(), User)

    def count(self, query) -> int:
        return self._count(query)

    def get_analyzers(self) -> List[Analyzer]:
        url = 'analyzer'

        return self._wrap(self._api.do_get(url).json(), Analyzer)

    def create(self, data) -> Organization:

        if isinstance(data, dict):
            data = Organization(data).json()
        elif isinstance(data, Organization):
            data = data.json()

        response = self._api.do_post('organization', data).json()

        return Organization(response)

    def update(self, org_id, data, fields=None) -> Organization:
        if isinstance(data, Organization):
            data = data.json()

        url = 'organization/{}'.format(org_id)
        patch = AbstractController._clean_changes(data, ['description', 'status'], fields)
        return self._wrap(self._api.do_patch(url, patch).json(), Organization)

    def delete(self, org_id) -> bool:
        return self._api.do_delete('organization/{}'.format(org_id))
