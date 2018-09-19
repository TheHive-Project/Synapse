import unittest

import json

from workflows.QRadar2Alert import *

class MockQRadarAPI:

    def __init__(self, offenses = [{ "id": 12345, 'offense_type': 22 }],
                       offense_type = "Unknown"):
        self.offense_data = offenses
        self.offense_type = offense_type

    def getOffenses(self, test):
        return self.offense_data

    def getOffenseTypeStr(self, someint):
        return self.offense_type

    def getSourceIPs(self, offense):
        return []

    def getLocalDestinationIPs(self, offense):
        return []

    def getOffenseLogs(self, offense):
        return [{"utf8_payload":"sample log"}]

class MockHiveAPI:

    def craftAlert(self, title, description, severity, date, tags, tlp, status, type, source,
        sourceRef, artifacts, caseTemplate):

        from thehive4py.models import Case, CaseTask, CaseTaskLog, CaseObservable, Alert

        alert = Alert(title=title,
            description=description,
            severity=severity,
            date=date,
            tags=tags,
            tlp=tlp,
            type=type,
            source=source,
            sourceRef=sourceRef,
            artifacts=artifacts,
            caseTemplate=caseTemplate)

        return alert

    def craftAlertArtifact(self, **attributes):
        from thehive4py.models import AlertArtifact

        alertArtifact = AlertArtifact(dataType = attributes["dataType"], message = attributes["message"], data=attributes["data"])

        return alertArtifact

class TestBasicOffenseRetrieval(unittest.TestCase):
    sample_offense = { "id": 27, "offense_type": 3, "description":"test", "offense_source": "mock", "destination_networks":"foo", "source_network":"bar", "severity":2, "start_time":0 }

    def test_basic_retrieval(self):
        mockQRadar = MockQRadarAPI()
        offenses = getEnrichedOffenses(mockQRadar, 1)
        self.assertEqual(len(offenses), 1)

    def test_basic_enrichment(self):
        mockQRadar = MockQRadarAPI(offense_type="Offense Type")
        enriched = enrichOffense(mockQRadar, self.sample_offense)

        self.assertEqual(enriched['offense_type_str'], "Offense Type")
        self.assertTrue('logs' in enriched)

    def test_sev_mapping(self):
        mockQRadar = MockQRadarAPI()
        mockHiveAPI = MockHiveAPI()
        theHiveAlert = qradarOffenseToHiveAlert(mockHiveAPI, enrichOffense(mockQRadar, self.sample_offense))
        self.assertEqual(theHiveAlert.severity, 1)

    def test_username_source(self):

        sample_username_string = '''{"username_count":1,"description":"[UC-1234] Test Dispatched Event","rules":[{"id":100352,"type":"CRE_RULE"}],"event_count":6,"flow_count":0,"assigned_to":null,"security_category_count":2,"follow_up":false,"source_address_ids":[1],"source_count":1,"inactive":false,"protected":false,"closing_user":null,"destination_networks":["Net-10-172-192.Net_192_168_0_0"],"source_network":"other","category_count":2,"close_time":null,"remote_destination_count":0,"start_time":1536854703878,"magnitude":3,"last_updated_time":1536854706272,"credibility":4,"id":1,"categories":["SSH Login Failed","Access Denied"],"severity":6,"policy_category_count":0,"closing_reason_id":null,"device_count":2,"offense_type":3,"relevance":0,"domain_id":0,"offense_source":"foobar","local_destination_address_ids":[1],"local_destination_count":1,"status":"OPEN"}'''
        sample_username = json.loads(sample_username_string)
        mockQRadar = MockQRadarAPI([sample_username], "Username")
        mockHiveAPI = MockHiveAPI()

        theHiveAlert = qradarOffenseToHiveAlert(mockHiveAPI, enrichOffense(mockQRadar, self.sample_offense))
        self.assertEqual(len(theHiveAlert.artifacts), 1)
        

if __name__ == '__main__':
    unittest.main()
