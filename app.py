#!/usr/bin/env python3
# -*- coding: utf8 -*-

import os
import logging, logging.handlers
from flask import Flask, request, jsonify

from workflows.common.common import getConf
from workflows.Ews2Case import connectEws
from workflows.QRadar2Alert import offense2Alert

from pprint import pprint

app_dir = os.path.dirname(os.path.abspath(__file__))

#create logger
logger = logging.getLogger('workflows')
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    #log format as: 2013-03-08 11:37:31,411 : : WARNING :: Testing foo
    formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')
    #handler writes into, limited to 1Mo in append mode
    if not os.path.exists('logs'):
        #create logs directory if does no exist (typically at first start)
        os.makedirs('logs')
    pathLog = app_dir + '/logs/synapse.log'
    file_handler = logging.handlers.RotatingFileHandler(pathLog, 'a', 1000000, 1)
    #level debug
    file_handler.setLevel(logging.DEBUG)
    #using the format defined earlier
    file_handler.setFormatter(formatter)
    #Adding the file handler
    logger.addHandler(file_handler)

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def listenWebhook():
    if request.is_json:
        webhook = request.get_json()
        pprint(webhook)

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
            workflowReport = offense2Alert(content['timerange'])
            if workflowReport['success']:
                return jsonify(workflowReport), 200
            else:
                return jsonify(workflowReport), 500
        else:
            logger.error('Missing <timerange> key/value')
            return jsonify({'sucess':False}), 500
    else:
        logger.error('Not json request')
        return jsonify({'sucess':False}), 500

@app.route('/version', methods=['GET'])
def getSynapseVersion():
    return jsonify({'version': '1.0'}), 200

if __name__ == '__main__':
    cfg = getConf()
    app.run(debug=cfg.getboolean('api', 'debug'),
        host=cfg.get('api', 'host'),
        port=cfg.get('api', 'port'),
        threaded=cfg.get('api', 'threaded')
    )
