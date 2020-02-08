import os, sys
import logging
# ADDED: Importing time for SourceRef unique ID generation and re for searching Intrusion Type in the Mail-Body as seen in Demo
import time
import re

current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = current_dir + '/..'
sys.path.insert(0, current_dir)

from common.common import getConf
from objects.EwsConnector import EwsConnector
from objects.TheHiveConnector import TheHiveConnector
from objects.TempAttachment import TempAttachment

# CHANGE: Renaming the Function as to not collide with app.py defs
def alertConnectEws():
	logger = logging.getLogger(__name__)
	logger.info('%s.connectEws starts', __name__)

	report = dict()
	report['success'] = bool()

	try:
		cfg = getConf()
		ewsConnector = EwsConnector(cfg)
		folder_name = cfg.get('EWS', 'folder_name')
		unread = ewsConnector.scan(folder_name)
		theHiveConnector = TheHiveConnector(cfg)

		for msg in unread:

			# The Variables for configuration start here, please do not change anything else unless you know what you are doing.
			# ------------------------------------------------------------------------------------------------------------------

			title = msg.subject
			description = msg.text_body
			severity = 2

			# DEV-NOTE: I have personally not gotten "date" to accept anything other than Unix Epoch-Timestamps with milliseconds, hence the "* 1000"
			date = time.time() * 1000

			tags = "YourTag1","YourTag2"
			tlp = 2
			status = "New"
			type = "YourTypeHere"
			source = "YourSourceHere"
			sourceRef = "YourSourceRefHere"
			artifacts = ""
			caseTemplate = ""

			# Configuration ends here, please do not change anything beyond this point unless you know what you are doing.
			# ------------------------------------------------------------------------------------------------------------------

			# calling .craftAlert to prepare the Alert for ingesting via .createAlert
			alert = theHiveConnector.craftAlert(title, description, severity, date, tags, tlp, status, type, source, sourceRef, artifacts, caseTemplate)
			theHiveConnector.createAlert(alert)
			# marking all handled EMails as read in the Mailbox
			readMsg = ewsConnector.markAsRead(msg)

		report['success'] = True
		return report

	except Exception as e:
		logger.error('Failed to create case from email', exc_info=True)
		report['success'] = False
		return report

if __name__ == '__main__':
    connectEws()
