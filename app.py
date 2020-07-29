#!/usr/bin/env python3
# -*- coding: utf8 -*-

import os
import sys
import logging, logging.handlers
from flask import Flask, request, jsonify

from modules.generic.functions import getConf, loadUseCases
from integrations.EWS.Ews2Case import connectEws
from integrations.QRadar.QRadar2Alert import allOffense2Alert
from integrations.ELK.ELK2Alert import ml2Alert,logstash2Alert
from core.ManageWebhooks import manageWebhook

app_dir = os.path.dirname(os.path.abspath(__file__))
cfg = getConf()

#create logger
wflogger = logging.getLogger('workflows')
if not wflogger.handlers:
    wflogger.setLevel(logging.getLevelName(cfg.get('api', 'log_level')))
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
        wflogger.addHandler(file_handler)
    else:
        #Logging to stdout
        out_hdlr = logging.StreamHandler(sys.stdout)
        out_hdlr.setFormatter(logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s'))
        wflogger.addHandler(out_hdlr)

#create logger
app2alogger = logging.getLogger('app2a')
if not app2alogger.handlers:
    app2alogger.setLevel(logging.getLevelName(cfg.get('api', 'log_level')))
    #log format as: 2013-03-08 11:37:31,411 : : WARNING :: Testing foo
    formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')
    #handler writes into, limited to 1Mo in append mode
    if not cfg.getboolean('api', 'dockerized'):
        if not os.path.exists('logs'):
            #create logs directory if does no exist (typically at first start)
            os.makedirs('logs')
        pathLog = app_dir + '/logs/synapse-app2a.log'
        file_handler = logging.handlers.RotatingFileHandler(pathLog, 'a', 1000000, 1)
        #level debug
        #file_handler.setLevel(logging.DEBUG)
        #using the format defined earlier
        file_handler.setFormatter(formatter)
        #Adding the file handler
        app2alogger.addHandler(file_handler)
    else:
        #Logging to stdout
        out_hdlr = logging.StreamHandler(sys.stdout)
        out_hdlr.setFormatter(logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s'))
        app2alogger.addHandler(out_hdlr)


#Load use cases
use_cases = loadUseCases()
use_case_list = []
for ucs in use_cases['use_cases']:
    use_case_list.append(ucs)
#use_case_list = ",".join(use_case_list)
wflogger.info("Loaded the following use cases: {}".format(use_case_list))

app = Flask(__name__)

@app.before_first_request
def initialize():
    wflogger = logging.getLogger('workflows')

@app.route('/webhook', methods=['POST'])
def listenWebhook():
    if request.is_json:
         try:
            webhook = request.get_json()
            wflogger.debug("Webhook: %s" % webhook)
            workflowReport = manageWebhook(webhook, cfg, use_cases)
            if workflowReport['success']:
                return jsonify(workflowReport), 200
            else:
                return jsonify(workflowReport), 500
         except Exception as e:
             wflogger.error('Failed to listen or action webhook: %s' % e, exc_info=True)
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
            wflogger.error('Missing <timerange> key/value')
            return jsonify({'sucess':False, 'message':"timerange key missing in request"}), 500
    else:
        wflogger.error('Not json request')
        return jsonify({'sucess':False, 'message':"Request didn't contain valid JSON"}), 400

@app.route('/ELK2alert', methods=['POST'])
def ELK2alert():
    wflogger.info("Received ELK2Alert request")
    wflogger.debug('request: %s' % request.get_data())
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
        wflogger.error('Not json request: %s' % request.get_data())
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
