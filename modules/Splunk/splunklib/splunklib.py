# vim: sw=4:ts=4:et

import datetime
import json
import logging
import re
import requests
import time
import traceback
import warnings
import xml.etree.ElementTree as ET

#logging.getLogger("requests").setLevel(logging.WARNING)

def create_timedelta(timespec):
    """Utility function to translate DD:HH:MM:SS into a timedelta object."""
    duration = timespec.split(':')
    seconds = int(duration[-1])
    minutes = 0
    hours = 0
    days = 0

    if len(duration) > 1:
        minutes = int(duration[-2])
    if len(duration) > 2:
        hours = int(duration[-3])
    if len(duration) > 3:
        days = int(duration[-4])

    return datetime.timedelta(days=days, seconds=seconds, minutes=minutes, hours=hours)

class SplunkQueryObject(object):
    """Basic query functionality for splunk."""
    
    def __init__(self, 
        uri=None, 
        username=None, 
        password=None, 
        max_result_count=1000,
        relative_duration_before="00:00:15",
        relative_duration_after="00:00:05",
        query_timeout="00:30:00",
        network_timeout=30,
        http_proxy=None,
        https_proxy=None,
        *args, **kwargs):

        super(SplunkQueryObject, self).__init__(*args, **kwargs)

        self.uri = uri
        self.username = username
        self.password = password
        self.max_result_count = max_result_count

        self.proxies = {}
        if http_proxy:
            self.proxies['http'] = http_proxy
        if https_proxy:
            self.proxies['https'] = https_proxy

        # default relative time frames for searches
        self.relative_duration_before = relative_duration_before
        self.relative_duration_after = relative_duration_after

        # how long until a query should time out
        self.query_timeout = query_timeout

        # how long until a network request times out
        self.network_timeout = network_timeout

        self.session_key = None # temp authentication token
        self.search_id = None # search id

        # the resulting search results are stored here once a query has been executed
        self.search_results = None

        # statistics
        self.query_start_time = None
        self.query_end_time = None

        # controls shutdown or cancellation
        self.query_cancelled = False

    def __getitem__(self, key):
        return self.search_results[key]

    def cancel(self):
        """Cancels an existing query."""
        self.query_cancelled = True

    def query_relative(self, query, event_time=None, relative_duration_before=None, relative_duration_after=None):
        """Perform the query and calculate the time range based on the relative values."""
        assert event_time is None or isinstance(event_time, datetime.datetime)
        assert relative_duration_before is None or isinstance(relative_duration_before, str)
        assert relative_duration_after is None or isinstance(relative_duration_after, str)

        if event_time is None:
            # use now as the default 
            event_time = datetime.datetime.now()

        # use preconfigured defaults
        if relative_duration_before is None:
            relative_duration_before = self.relative_duration_before

        if relative_duration_after is None:
            relative_duration_after = self.relative_duration_after
        
        time_start = event_time - create_timedelta(relative_duration_before)
        time_end = event_time + create_timedelta(relative_duration_after)
        return self.query_with_time(query, time_start, time_end)

    def query_with_time(self, query, time_start, time_end):
        assert isinstance(query, str)
        assert isinstance(time_start, datetime.datetime)
        assert isinstance(time_end, datetime.datetime)

        # searches need to start with search
        if not query.lstrip().lower().startswith('search'):
            logging.debug('adding missing search to begining of search string')
            query = 'search {0}'.format(query)

        splunk_time_end = ''
        if time_end is not None:
            splunk_time_end = time_end.strftime('%m/%d/%Y:%H:%M:%S')
            # insert this after the search keyword
            query = re.sub(r'^\s*search', 'search latest={0}'.format(splunk_time_end), query, 1, re.I)

        splunk_time_start = ''
        if time_start is not None:
            splunk_time_start = time_start.strftime('%m/%d/%Y:%H:%M:%S')
            # insert this after the search keyword
            query = re.sub(r'^\s*search', 'search earliest={0}'.format(splunk_time_start), query, 1, re.I)

        return self.query(query)

    def query_with_index_time(self, query, time_start, time_end):
        assert isinstance(query, str)
        assert isinstance(time_start, datetime.datetime)
        assert isinstance(time_end, datetime.datetime)

        # searches need to start with search
        if not query.lstrip().lower().startswith('search'):
            logging.debug('adding missing search to begining of search string')
            query = 'search {0}'.format(query)

        splunk_time_end = ''
        if time_end is not None:
            splunk_time_end = time_end.strftime('%m/%d/%Y:%H:%M:%S')
            # insert this after the search keyword
            query = re.sub(r'^\s*search', 'search _index_latest={0}'.format(splunk_time_end), query, 1, re.I)

        splunk_time_start = ''
        if time_start is not None:
            splunk_time_start = time_start.strftime('%m/%d/%Y:%H:%M:%S')
            # insert this after the search keyword
            query = re.sub(r'^\s*search', 'search _index_earliest={0}'.format(splunk_time_start), query, 1, re.I)

        return self.query(query)

    def query(self, query):
        assert isinstance(query, str)

        timeout_date = datetime.datetime.now() + create_timedelta(self.query_timeout)

        # log into splunk and get the token
        if not self.authenticate():
            return False

        # use the token to perform a query
        if not self.execute_query(query):
            return False

        self.query_start_time = datetime.datetime.now()
        
        # keep asking splunk if the query is done
        while not self.query_cancelled:
            job_completed = self.is_job_completed()
            if job_completed is None:
                return False

            if job_completed:
                self.query_end_time = datetime.datetime.now()
                logging.debug("query time = {0}".format(self.query_end_time - self.query_start_time))
                break

            if datetime.datetime.now() > timeout_date:
                logging.error("splunk query {0} timed out".format(query))
                return False

            time.sleep(1)

        # download the results of the query
        if not self.query_cancelled:
            self.download_search_results()
        # delete the search from splunk TODO

        return True

    def authenticate(self):
        try:
            logging.debug("logging into {0} as user {1}".format(self.uri, self.username))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = requests.post(
                    '{0}/servicesNS/admin/search/auth/login'.format(self.uri),
                    data = { 'username': self.username, 'password': self.password },
                    verify = False, # XXX take this out!
                    timeout = self.network_timeout,
                    proxies=self.proxies )
            if r.status_code != 200:
                logging.fatal("unable to log into slunk: response code {0} reason {1}".format(
                    r.status_code, r.reason))
                return False

            root = ET.fromstring(r.text)
            self.session_key = root.find('sessionKey').text

            logging.debug("got session key {0}".format(self.session_key))
            # TODO cache this and use it again until it times out
            return True

        except Exception as e:
            logging.error("unable to authenticate to splunk: {0}".format(str(e)))
            return False

    def execute_query(self, query):
        try:
            # searches need to start with search
            if not query.lstrip().lower().startswith('search'):
                logging.debug('adding missing search to begining of search string')
                query = 'search {0}'.format(query)

            logging.debug("performing splunk query [{0}] against {1}".format(query, self.uri))

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = requests.post(
                    '{0}/servicesNS/admin/search/search/jobs'.format(self.uri),
                    verify = False, # XXX take this out!
                    headers = {
                        'Authorization': 'Splunk {0}'.format(self.session_key)
                    },
                    data = {
                        'search': query,
                        #'output_mode': 'csv',
                        'max_count': str(self.max_result_count),
                        #'earliest_time': splunk_time_start,
                        #'latest_time': splunk_time_end
                    },
                    timeout = self.network_timeout,
                    proxies=self.proxies)

            if r.status_code != 201:
                logging.error("splunk search failed: response code {0} reason {1}".format(
                    r.status_code, r.reason))
                return False

            # and now we get a search id
            root = ET.fromstring(r.text)
            self.search_id = root.find('sid').text

            logging.debug("got search id {0}".format(self.search_id))
            return True

        except Exception as e:
            logging.error("attempt to perform splunk query failed: {0}".format(str(e)))
            traceback.print_exc()
            return False

    def is_job_completed(self):
        try:
            logging.debug("querying status of search job {0}".format(self.search_id))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = requests.get(
                    '{0}/servicesNS/admin/search/search/jobs/{1}'.format(self.uri, self.search_id),
                    headers = {
                        'Authorization': 'Splunk {0}'.format(self.session_key)
                    }, 
                    verify = False, # XXX take this out!
                    timeout = self.network_timeout,
                    proxies=self.proxies
                )

            if r.status_code != 200:
                logging.error("unable to get status of search job {0}: response code {1} reason {2}".format(
                    self.search_id, r.status_code, r.reason))
                return None

            m = re.search(r'<s:key name="isDone">([01])</s:key>', r.text, re.M)
            if not m:
                logging.error("could not parse response for isDone value for search job {0}".format(
                    self.search_id))
                return False

            is_done = m.group(1) == '1'
            if is_done:
                logging.debug("search job {0} has completed".format(self.search_id))
                return True

            logging.debug("search job {} still running (run time {})".format(self.search_id, datetime.datetime.now() - self.query_start_time))
            return False

        except Exception as e:
            logging.error("unable to query status of search job {0}: {1}".format(
                self.search_id, str(e)))
            return None

    def download_search_results(self):
        try:
            logging.debug("downloading search results for job {0}".format(self.search_id))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = requests.get(
                    '{0}/servicesNS/admin/search/search/jobs/{1}/results'.format(self.uri, self.search_id),
                    headers = {
                        'Authorization': 'Splunk {0}'.format(self.session_key)
                    }, 
                    params = {
                        'count': "0", # get all of the results
                        'output_mode': 'json_rows' # get the results in json format
                    },
                    verify = False, # XXX take this out!
                    timeout = self.network_timeout,
                    proxies=self.proxies
                )

            if r.status_code != 200:
                logging.error("unable to download results for search job {0}: response code {1} reason {2}".format(
                    self.search_id, r.status_code, r.reason))
                return False

            try:
                self.search_results = json.loads(r.text)
                logging.debug("downloaded {0} rows of results".format(len(self.search_results['rows'])))
            except Exception as e:
                logging.error("unable to parse the json returned by splunk for search {0}: {1}".format(
                    self.search_id, str(e)))
                traceback.print_exc()
                return False

            return True

        except Exception as e:
            logging.debug("unable to download search results for job {0}: {1}".format(
                self.search_id, str(e)))

    def json(self):
        """Returns the search results as a list of JSON objects."""
        if self.search_results is None:
            return None

        result = []
        for row in self.search_results['rows']:
            obj = {}
            for index in range(0, len(self.search_results['fields'])):
                obj[self.search_results['fields'][index]] = row[index]
            result.append(obj)

        return result
