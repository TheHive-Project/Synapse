import ipaddress
import itertools
import logging
import re
from core.functions import getConf
from datetime import datetime, timezone, timedelta
from jinja2 import Template, Environment, meta

class Main():
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cfg = getConf()

    def tagExtractor(self, dict, field_names, extraction_regexes):
        self.logger.debug('%s.tagExtractor starts', __name__)
        self.matches = []
        for field_name in field_names:
            for extraction_regex in extraction_regexes:
                self.regex = re.compile(extraction_regex)
                self.logger.debug("offense: %s" % dict[field_name])
                self.matches.extend(self.regex.findall(str(dict[field_name])))
        if len(self.matches) > 0:
            self.logger.debug("matches: %s" % self.matches)
            return self.matches
        else:
            return []

    def check_if_updated(self, current_a, new_a):
        # Function to check if the alert that has been created contains new/different data in comparison to the alert that is present
        self.logger.debug("Current alert %s" % current_a)
        self.logger.debug("New alert %s" % new_a)
        for item in sorted(new_a):
            # Skip values that are not required for the compare
            if item == "date":
                continue
            # Artifacts require special attention as these are all separate objects in an array for a new alert. The current alert is a array of dicts
            if item == "artifacts":
                # If the array is of different size an update is required
                if not len(current_a[item]) == len(new_a[item]):
                    self.logger.info("Length mismatch detected: old length:%s, new length: %s" % (len(current_a[item]), len(new_a[item])))
                    return True

                # loop through the newly created alert array to extract the artifacts and add them so a separate variable
                for i in range(len(new_a[item])):
                    self.vars_current_artifacts = current_a[item][i]
                    self.vars_new_artifacts = vars(new_a[item][i])

                    # For each artifact loop through the attributes to check for differences
                    for attribute in self.vars_new_artifacts:
                        if self.vars_current_artifacts[attribute] != self.vars_new_artifacts[attribute]:
                            self.logger.debug("Change detected for %s, new value: %s" % (self.vars_current_artifacts[attribute], self.vars_new_artifacts[attribute]))
                            self.logger.debug("old: %s, new: %s" % (self.vars_current_artifacts, self.vars_new_artifacts))
                            return True

                # loop through the newly created alert array to extract the artifacts and add them so a separate variable
                # self.diff = list(itertools.filterfalse(lambda x: x in vars(new_a['artifacts']), current_a['artifacts']))
                # if len(self.diff) > 0:
                #     self.logger.debug("Found diff in artifacts: %s" % self.diff)
                #     return True

            if item == "tags":
                # loop through the newly created alert array to extract the tags and add them so a separate variable
                self.diff = list(itertools.filterfalse(lambda x: x in new_a['tags'], current_a['tags']))
                self.diff = self.diff + list(itertools.filterfalse(lambda x: x in current_a['tags'], new_a['tags']))
                if len(self.diff) > 0:
                    self.logger.debug("Found diff in tags: %s" % self.diff)
                    return True

            # Match other items of the new alert to the current alert (string based)
            # if str(current_a[item]) != str(new_a[item]):
                # self.logger.debug("Change detected for %s, new value: %s" % (item,str(new_a[item])))
                # return True
        return False

    def checkObservableTLP(self, artifacts):
        self.artifacts = []

        if self.cfg.get('Automation', 'tlp_modifiers', fallback=None):
            for artifact in self.artifacts:
                for tlp, tlp_config in self.cfg.get('Automation', 'tlp_modifiers').items():

                    self.tlp_table = {
                        "white": 0,
                        "green": 1,
                        "amber": 2,
                        "red": 3
                    }

                    self.tlp_int = self.tlp_table[tlp]

                    for observable_type, observable_type_config in tlp_config.items():
                        if observable_type == 'ip':
                            for entry in observable_type_config:
                                # Initial values
                                self.match = False
                                observable_ip = ipaddress.ip_address(artifact['data'])

                                # Match ip with CIDR syntax
                                if entry[-3:] == "/32":
                                    self.tlp_list_entry = ipaddress.ip_address(entry[:-3])
                                    self.match = observable_ip == self.tlp_list_entry
                                # Match ip without CIDR syntax
                                elif "/" not in entry:
                                    self.tlp_list_entry = ipaddress.ip_address(entry)
                                    self.match = observable_ip == self.tlp_list_entry
                                # Capture actual network entries
                                else:
                                    self.tlp_list_entry = ipaddress.ip_network(entry, strict=False)
                                    self.match = observable_ip in self.tlp_list_entry

                                # If matched add it to new entries to use outside of the loop
                                if self.match:
                                    self.logger.debug("Observable {} has matched {} through {} of the TLP modifiers list. Adjusting TLP...".format(artifact['data'], tlp, entry))
                                    artifact['tlp'] = self.tlp_int
                        else:
                            for extraction_regex in observable_type_config:
                                self.regex = re.compile(extraction_regex)
                                if self.regex.match(artifact['data']):
                                    self.logger.debug("Observable {} has matched {} through {} of the TLP modifiers list. Adjusting TLP...".format(artifact['data'], tlp, entry))
                                    artifact['tlp'] = self.tlp_int
               
                # Add artifact to an array again
                self.artifacts.append(artifact)

            return self.artifacts
        else:
            return artifacts
