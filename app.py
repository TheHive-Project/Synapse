#!/usr/bin/env python3
# -*- coding: utf8 -*-

#load python modules
import os
import sys
import logging, logging.handlers
from flask import Flask, request, jsonify

#Load custom modules
from core.functions import getConf, loadAutomationConfiguration

app_dir = os.path.dirname(os.path.abspath(__file__))
cfg = getConf()

#create logger
logger = logging.getLogger()
logger.setLevel(logging.getLevelName(cfg.get('api', 'log_level')))
#log format as: 2013-03-08 11:37:31,411 : : WARNING :: Testing foo
formatter = logging.Formatter('%(asctime)s :: %(name)s :: %(levelname)s :: %(message)s')
#handler writes into, limited to 1Mo in append mode
if not cfg.getboolean('api', 'dockerized'):
    if not os.path.exists('logs'):
        #create logs directory if does no exist (typically at first start)
        os.makedirs('logs')
    pathLog = app_dir + '/logs/synapse.log'
    file_handler = logging.handlers.RotatingFileHandler(pathLog, 'a', 1000000, 1)
    #using the format defined earlier
    file_handler.setFormatter(formatter)
    #Adding the file handler
    logger.addHandler(file_handler)
else:
    #Logging to stdout
    out_hdlr = logging.StreamHandler(sys.stdout)
    out_hdlr.setFormatter(formatter)
    logger.addHandler(out_hdlr)

from core.managewebhooks import manageWebhook

#Load automation config
automation_config = loadAutomationConfiguration(cfg.get('Automation', 'automation_config_dir', fallback=None))
automation_list = []
for a_id in automation_config['automation_ids']:
    automation_list.append(a_id)
logger.info("Loaded the following automation identifiers: {}".format(automation_list))

from core.loader import moduleLoader
loaded_modules = moduleLoader("integration")

app = Flask(__name__)

@app.before_first_request
def initialize():
    logger = logging.getLogger(__name__)

@app.route('/webhook', methods=['POST'])
def listenWebhook():
    if request.is_json:
         try:
            webhook = request.get_json()
            logger.debug("Webhook: %s" % webhook)
            workflowReport = manageWebhook(webhook, cfg, automation_config)
            if workflowReport['success']:
                return jsonify(workflowReport), 200
            else:
                return jsonify(workflowReport), 500
         except Exception as e:
             logger.error('Failed to listen or action webhook: %s' % e, exc_info=True)
             return jsonify({'success':False}), 500

    else:
        return jsonify({'success':False, 'message':'Not JSON'}), 400

#loop through all configured sections and create a mapping for the endpoints
modules = {}
for cfg_section in cfg.sections():
    endpoint = cfg.get(cfg_section, 'synapse_endpoint', fallback=None)
    if endpoint:
        logger.info("Enabling integration for {}: {}".format(cfg_section, endpoint))
        modules[endpoint] = cfg_section

#Use a dynamic route to receive integration based request and send them to the appropriate module found through the configuration
@app.route('/integration/<integration>', methods=['GET', 'POST', 'PUT'])
def endpoint(integration):
    try:
        response = loaded_modules[modules[integration]].validateRequest(request)
        return response
    except KeyError as e:
        logger.warning('Integration module not found: {}'.format(integration))

@app.route('/version', methods=['GET'])
def getSynapseVersion():
    return jsonify({'version': '2.0.0'}), 200

if __name__ == '__main__':
    app.run(debug=cfg.getboolean('api', 'debug_mode'),
        host=cfg.get('api', 'host'),
        port=cfg.get('api', 'port'),
        threaded=cfg.get('api', 'threaded')
    )
