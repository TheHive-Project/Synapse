#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import requests
import warnings

from .exceptions import *
from .controllers.organizations import OrganizationsController
from .controllers.users import UsersController
from .controllers.jobs import JobsController
from .controllers.analyzers import AnalyzersController
from .controllers.responders import RespondersController


class Api(object):
    """This is the main class for communicating with the Cortex API. As this is a new major version, authentication is
    only possible through the api key. Basic auth with user/pass is deprecated."""
    def __init__(self, url, api_key, **kwargs):
        if not isinstance(url, str) or not isinstance(api_key, str):
            raise TypeError('URL and API key are required and must be of type string.')

        # Drop a warning for python2 because reasons
        if int(sys.version[0]) < 3:
            warnings.warn('You are using Python 2.x. That can work, but is not supported.')

        self.__api_key = api_key
        self.__url = url
        self.__base_url = '{}/api/'.format(url)
        self.__proxies = kwargs.get('proxies', {})
        self.__verify_cert = kwargs.get('verify_cert', kwargs.get('cert', True))

        self.organizations = OrganizationsController(self)
        self.users = UsersController(self)
        self.jobs = JobsController(self)
        self.analyzers = AnalyzersController(self)
        self.responders = RespondersController(self)

    @staticmethod
    def __recover(exception):

        if isinstance(exception, requests.exceptions.HTTPError):
            if exception.response.status_code == 404:
                raise NotFoundError("Resource not found") from exception
            elif exception.response.status_code == 401:
                raise AuthenticationError("Authentication error") from exception
            elif exception.response.status_code == 403:
                raise AuthorizationError("Authorization error") from exception
            else:
                raise InvalidInputError("Invalid input exception") from exception
        elif isinstance(exception, requests.exceptions.ConnectionError):
            raise ServiceUnavailableError("Cortex service is unavailable") from exception
        elif isinstance(exception, requests.exceptions.RequestException):
            raise ServerError("Cortex request exception") from exception
        else:
            raise CortexError("Unexpected exception") from exception

    def do_get(self, endpoint, params={}):
        headers = {
            'Authorization': 'Bearer {}'.format(self.__api_key)
        }

        try:
            response = requests.get('{}{}'.format(self.__base_url, endpoint),
                                    headers=headers,
                                    params=params,
                                    proxies=self.__proxies,
                                    verify=self.__verify_cert)

            response.raise_for_status()
            return response
        except Exception as ex:
            self.__recover(ex)

    def do_file_post(self, endpoint, data, **kwargs):
        headers = {
            'Authorization': 'Bearer {}'.format(self.__api_key)
        }

        try:
            response = requests.post('{}{}'.format(self.__base_url, endpoint),
                                     headers=headers,
                                     proxies=self.__proxies,
                                     data=data,
                                     verify=self.__verify_cert,
                                     **kwargs)
            response.raise_for_status()
            return response
        except Exception as ex:
            self.__recover(ex)

    def do_post(self, endpoint, data, params={}, **kwargs):
        headers = {
            'Authorization': 'Bearer {}'.format(self.__api_key),
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post('{}{}'.format(self.__base_url, endpoint),
                                     headers=headers,
                                     proxies=self.__proxies,
                                     json=data,
                                     params=params,
                                     verify=self.__verify_cert,
                                     **kwargs)
            response.raise_for_status()
            return response
        except Exception as ex:
            self.__recover(ex)

    def do_patch(self, endpoint, data, params={}):
        headers = {
            'Authorization': 'Bearer {}'.format(self.__api_key),
            'Content-Type': 'application/json'
        }

        try:
            response = requests.patch('{}{}'.format(self.__base_url, endpoint),
                                      headers=headers,
                                      proxies=self.__proxies,
                                      json=data,
                                      params=params,
                                      verify=self.__verify_cert)
            response.raise_for_status()
            return response
        except Exception as ex:
            self.__recover(ex)

    def do_delete(self, endpoint):
        headers = {
            'Authorization': 'Bearer {}'.format(self.__api_key)
        }

        try:
            response = requests.delete('{}{}'.format(self.__base_url, endpoint),
                                       headers=headers,
                                       proxies=self.__proxies,
                                       verify=self.__verify_cert)
            response.raise_for_status()
            return True
        except Exception as ex:
            self.__recover(ex)
        pass

    def status(self):
        return self.do_get('status')

    """
    Method for backward compatibility 
    """
    def get_analyzers(self, data_type=None):
        warnings.warn(
            'api.get_analyzers() is considered deprecated. Use api.analyzers.get_by_[id|name|type]() instead.',
            DeprecationWarning
        )
        if data_type is not None:
            return self.analyzers.find_all()
        else:
            return self.analyzers.get_by_type(data_type)

    def run_analyzer(self, analyzer_id, data_type, tlp, observable):
        warnings.warn(
            'api.run_analyzer() is considered deprecated. '
            'Use api.analyzers.run_by_name() or api.analyzers.run_by_id() instead.',
            DeprecationWarning
        )
        options = {
            'data': observable,
            'tlp': tlp,
            'dataType': data_type
        }
        return self.analyzers.run_by_name(analyzer_id, options)

    def get_job_report(self, job_id, timeout='Inf'):
        warnings.warn(
            'api.get_job_report() is considered deprecated. Use api.jobs.get_report() instead.',
            DeprecationWarning
        )
        return self.jobs.get_report_async(job_id, timeout)        

    def delete_job(self, job_id):
        warnings.warn(
            'api.delete_job() is considered deprecated. Use api.jobs.delete() instead.',
            DeprecationWarning
        )
        return self.jobs.delete(job_id)

