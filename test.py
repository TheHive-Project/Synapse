import unittest

from workflows.QRadar2Alert import *

class MockQRadarAPI:

    def getOffenses(self, test):
        return [{ "id": 12345, 'offense_type': 22 }]

    def getOffenseTypeStr(self, someint):
        return "Offense Type"

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

class TestBasicOffenseRetrieval(unittest.TestCase):
    sample_offense = { "id": 27, "offense_type": 3, "description":"test", "offense_source": "mock", "destination_networks":"foo", "source_network":"bar", "severity":2, "start_time":0 }

    def test_basic_retrieval(self):
        mockQRadar = MockQRadarAPI()
        offenses = getEnrichedOffenses(mockQRadar, 1)
        self.assertEqual(len(offenses), 1)

    def test_basic_enrichment(self):
        mockQRadar = MockQRadarAPI()
        enriched = enrichOffense(mockQRadar, self.sample_offense)

        self.assertEqual(enriched['offense_type_str'], "Offense Type")
        self.assertTrue('logs' in enriched)

    def test_sev_mapping(self):
        mockQRadar = MockQRadarAPI()
        mockHiveAPI = MockHiveAPI()
        theHiveAlert = qradarOffenseToHiveAlert(mockHiveAPI, enrichOffense(mockQRadar, self.sample_offense))
        self.assertEqual(theHiveAlert.severity, 1)

if __name__ == '__main__':
    unittest.main()
