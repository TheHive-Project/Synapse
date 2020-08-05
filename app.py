#!/usr/bin/env python3
# -*- coding: utf8 -*-

import os
import sys
import logging, logging.handlers
from flask import Flask, request, jsonify

from core.functions import getConf, loadUseCases
from modules.EWS.integration import connectEws
from modules.QRadar.integration import allOffense2Alert
from modules.ELK.integration import ml2Alert,logstash2Alert
from core.managewebhooks import manageWebhook

app_dir = os.path.dirname(os.path.abspath(__file__))
cfg = getConf()

#create logger
logger = logging.getLogger()
logger.setLevel(logging.getLevelName(cfg.get('api', 'log_level')))
#log format as: 2013-03-08 11:37:31,411 : : WARNING :: Testing foo
formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')
#handler writes into, limited to 1Mo in append mode
if not cfg.getboolean('api', 'dockerized'):
    if not os.path.exists('logs'):
        #create logs directory if does no exist (typically at first start)
        os.makedirs('logs')
    pathLog = app_dir + '/logs/synapse.log'
    file_handler = logging.handlers.RotatingFileHandler(pathLog, 'a', 1000000, 1)
    #level debug
    #file_handler.setLevel(logging.DEBUG)
    #using the format defined earlier
    file_handler.setFormatter(formatter)
    #Adding the file handler
    logger.addHandler(file_handler)
else:
    #Logging to stdout
    out_hdlr = logging.StreamHandler(sys.stdout)
    out_hdlr.setFormatter(logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s'))
    logger.addHandler(out_hdlr)

#Load use cases
use_cases = loadUseCases()
use_case_list = []
for ucs in use_cases['use_cases']:
    use_case_list.append(ucs)
#use_case_list = ",".join(use_case_list)
logger.info("Loaded the following use cases: {}".format(use_case_list))

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
            workflowReport = manageWebhook(webhook, cfg, use_cases)
            if workflowReport['success']:
                return jsonify(workflowReport), 200
            else:
                return jsonify(workflowReport), 500
         except Exception as e:
             logger.error('Failed to listen or action webhook: %s' % e, exc_info=True)
             return jsonify({'success':False}), 500

    else:
        return jsonify({'success':False, 'message':'Not JSON'}), 400

@app.route('/ews2case', methods=['GET'])
def ews2case():
    workflowReport = connectEws()
    if workflowReport['success']:
        return jsonify(workflowReport), 200
    else:
        return jsonify(workflowReport), 500

@app.route('/QRadar2alert', methods=['POST'])
def QRadar2alert():
    if request.is_json:
        content = request.get_json()
        if 'timerange' in content:
            workflowReport = allOffense2Alert(content['timerange'])
            if workflowReport['success']:
                return jsonify(workflowReport), 200
            else:
                return jsonify(workflowReport), 500
        else:
            logger.error('Missing <timerange> key/value')
            return jsonify({'sucess':False, 'message':"timerange key missing in request"}), 500
    else:
        logger.error('Not json request')
        return jsonify({'sucess':False, 'message':"Request didn't contain valid JSON"}), 400

@app.route('/ELK2alert', methods=['POST'])
def ELK2alert():
    logger.info("Received ELK2Alert request")
    logger.debug('request: %s' % request.get_data())
    if request.is_json:
        content = request.get_json()
        if content['type'] == 'asml':
            workflowReport = ml2Alert(content)
        else:
            workflowReport = logstash2Alert(content)
        if workflowReport['success']:
            return jsonify(workflowReport), 200
        else:
            return jsonify(workflowReport), 500
    else:
        logger.error('Not json request: %s' % request.get_data())
        return jsonify({'sucess':False, 'message':"Request didn't contain valid JSON"}), 400

@app.route('/version', methods=['GET'])
def getSynapseVersion():
    return jsonify({'version': '1.1.1'}), 200

if __name__ == '__main__':
    app.run(debug=cfg.getboolean('api', 'debug_mode'),
        host=cfg.get('api', 'host'),
        port=cfg.get('api', 'port'),
        threaded=cfg.get('api', 'threaded')
    )
