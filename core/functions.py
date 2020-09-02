#!/usr/bin/env python3
# -*- coding: utf8 -*-

import logging
import os
import yaml
from configparser import ConfigParser

logger = logging.getLogger(__name__)
currentPath = os.path.dirname(os.path.abspath(__file__))
app_dir = currentPath + '/..'

def getYamlFiles(dir_name):
    dir_list = os.listdir(dir_name)
    yaml_files = list()
    for item in dir_list:
        file_path = os.path.join(dir_name, item)
        #If path is a directory, retrigger the function to get the contents of this directory
        if os.path.isdir(file_path):
            yaml_files = yaml_files + getYamlFiles(file_path)
        else:
            #Only add file when it is a yaml file
            if os.path.splitext(file_path)[1] == '.yml':
                yaml_files.append(file_path)
    return yaml_files

def readYamlFile(file_name):
    #Load any yaml file with safe load
    with open(file_name, 'r') as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            logger.error('%s', __name__, exc_info=True)

def getConf():
    logger.debug('%s.getConf starts', __name__)

    #cfg = ConfigParser()
    confPath = app_dir + '/conf/synapse.conf'
    try:
        cfg = readYamlFile(confPath)
        return cfg
    except Exception as e:
        logger.error('%s', __name__, exc_info=True)

def loadAutomationConfiguration(path=None):
    autom_config = { 'automation_ids': {} }
    
    #Load automation configuration
    if path:
        automation_config_loc = path
    else:
        automation_config_loc = app_dir + "/conf/automation"
    
    #Lookup all files in use cases folder
    autom_files = getYamlFiles(automation_config_loc)

    #Read use case files one by one and add them to the configuration variable
    for autom_file in autom_files:
        logger.info('autom_file: {}'.format(autom_file))
        autom_yml_file = readYamlFile(autom_file)
        #Add new values to the dict as a dict
        autom_config['automation_ids'] = {**uc_config['automation_ids'], **autom_yml_file}
    
    return uc_config