from typing import List
from .abstract import AbstractController
from ..models import Job, JobArtifact


class JobsController(AbstractController):
    def __init__(self, api):
        AbstractController.__init__(self, 'job', api)

    def find_all(self, query, **kwargs) -> List[Job]:
        return self._wrap(self._find_all(query, **kwargs), Job)

    def find_one_by(self, query, **kwargs) -> Job:
        return self._wrap(self._find_one_by(query, **kwargs), Job)

    def get_by_id(self, org_id) -> Job:
        return self._wrap(self._get_by_id(org_id), Job)

    def get_report(self, job_id) -> Job:
        return self._wrap(self._api.do_get('job/{}/report'.format(job_id)).json(), Job)

    def get_report_async(self, job_id, timeout='Inf') -> Job:
        return self._wrap(self._api.do_get('job/{}/waitreport?atMost={}'.format(job_id, timeout)).json(), Job)

    def get_artifacts(self, job_id) -> List[JobArtifact]:
        return self._wrap(self._api.do_get('job/{}/artifacts'.format(job_id)).json(), JobArtifact)

    def delete(self, job_id) -> bool:
        return self._api.do_delete('job/{}'.format(job_id))
