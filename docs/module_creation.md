# User Guide

This guide will go through installation and basic configuration for Synapse.   

+ [Introduction](#introduction)
    + [Structure](#structure)
+ [Developing](#developing)
    + [Configuration](#configuration)
    + [Creating an Integration](#creating-an-integration)
    + [Connector](#connector)

## Introduction
As of Synapse 2.0 a module based approach is used. These modules allow the core structure of Synapse to remain untouched while making new integrations and automation very easy.
A module is defined for every 3rd party application that will be integrated with. Every module consists of a set of files that define the support for that specific 3rd party application.
These modules are loaded dynamically based on their presence and/or configuration within the Synapse configuration file and can be easily exchanged by community members to aid eachother in their automation processes. No one wants to do build anything that is already built somewhere else right?

### Structure
All modules are stored in the modules folder from where they will be loaded. The required configuration comes from the Synapse configuration file which will contain sections per module.

To facilitate the modular approach the following set of files is created:
- automation.py
    - This file is used to define automation that is preferred based on the 3rd party application. For example closing QRadar cases automatically when the case is closed.
- automator.py
    - The automator file contains all tasks that can be used in the automation configuration for the 3rd party application. For example checkSiem from QRadar to perform aql queries
- connector.py
    - The connector file is used to define all create unified functions to retrieve data from the 3rd party application. These can be used in the other files or even within other modules. For example facilitating the retrieval of the QRadar search results for checkSIEM. This requires a large amount of steps and the function is used both in the integration.py and in the automator.py to retrieve data
- integration.py
    - This file defines the actual integration code that is required to sync alerts from the 3rd party application to The Hive as an alert or case. For example, creating alerts from QRadar offenses

### Enabling modules
A module is loaded in various ways depending on the configuration and features.

#### Integration
When integration is supported the configuration item `enabled` defines if the integration is activated and `endpoint` defines the final result of the url to post to.
When it is enabled you can post a request to `<synapse url>/integration/<endpoint value>`. This will start the process defined in `integration.py`.

#### Automator
Automator modules are loaded in on presence of the automator.py file. The automation tasks can be referred to by the following syntax in the automation configuration: `<module name>.<function name>`. There is currently no restriction on imported tasks, so every python function that is present in `automator.py` will be callable in the automation configuration. 

#### Automation
The automation part of a module is loaded when the setting `automation_enabled` is set to true in the module configuration. From there on it will perform the automation tasks defined in this file

## Developing
As mentioned earlier developing a new module should be as easy as possible without interfering with the core of Synapse. Two flows will be described, which will be most common, to provide insights on how the development process should look like and what the modules should conform to.

### Configuration
If you create a new module then you will probably need to configure it. As mentioned earlier this configuration can be placed in the Synapse configuration file. The following sample shows a minimal set of values:

```
ELK:
  #Enables or disables the configuration
  enabled: false
  
  #Enabled or disables the module based automation (automation.py)
  automation_enabled: false
  
  #Provides the last part of the url required to send the alert to or send the request  to start the alert synchronization
  synapse_endpoint: /elk2th

  #Connection details to connect to the 3rd party application
  server: elk.stargazer.org
  port: 9200
  api_key: <key>
```

When you only require automation tasks there is only configuration required when the task asks for it. For example when sending a notification to Slack. The channel url should be present. But when you want to do a host name lookup for an observable no configuration is required.

### Creating an Integration
Creating an integration consists of understanding a few steps in the road to an alert in The Hive
- How does the raw data looks like when queried or received from the 3rd party application?
- What fields do you require for the alert in The Hive?
    - Is the raw data sufficient or do I need to perform addtional queries to gather all the required information
- How will the alert look like? Especially in terms of:
    - Field mapping
    - Description generation
    - Observables
    - Custom fields

Things to know before starting:
- Configuration can be loaded as follows: `cfg.get('<module>', '<configuration item>')`
- 

When you have all these items sorted out you can start building the integration by creating the `integration.py`. There is one mandatory function that needs to be present in this file and it is called `validateRequest`. The main file (app.py) uses this function to validate the incoming API call and send the data to the correct function within `integration.py` for further processing. So this is the part where you can validate the incoming data to your requirements, for example it being a POST with a json body containing a specific key/value

```
def validateRequest(request):
    if request.is_json:
        content = request.get_json()
        if 'timerange' in content:
            workflowReport = allOffense2Alert(content['timerange'])
            if workflowReport['success']:
                return json.dumps(workflowReport), 200
            else:
                return json.dumps(workflowReport), 500
        else:
            logger.error('Missing <timerange> key/value')
            return json.dumps({'sucess':False, 'message':"timerange key missing in request"}), 500
    else:
        logger.error('Not json request')
        return json.dumps({'sucess':False, 'message':"Request didn't contain valid JSON"}), 400
```

Then, by creating the `connector.py` you can start working on the retrieval of the 3rd party applicatin data. Add the function that will retrieve the data required from the 3rd party application and prepare it so the return function will return a clean dictionary which can be used to parse the alert(s). 

```
def getOffenses(self, timerange):
        """
            Returns all offenses within a list

            :param timerange: timerange in minute (get offense
                                for the last <timerange> minutes)
            :type timerange: int

            :return response_body: list of offenses, one offense being a dict
            :rtype response_body: list
        """

        self.logger.debug('%s.getOffenses starts', __name__)

        try:
            if timerange == "all":
                query = 'siem/offenses?filter=status%3DOPEN'
            else:
                #getting current time as epoch in millisecond
                now = int(round(time.time() * 1000))
            
                #filtering by time for offenses
                #timerange is in minute while start_time in QRadar is in millisecond since epoch
                #converting timerange in second then in millisecond
                timerange = int(timerange * 60 * 1000)
            
                #timerange is by default 1 minutes
                #so timeFilter is now minus 1 minute
                #this variable will be use to query QRadar for every offenses since timeFilter
                timeFilter = now - timerange
            
                # moreover we filter on OPEN offenses only
                query = 'siem/offenses?filter=last_updated_time%3E' + str(timeFilter) + '%20and%20last_updated_time%3C' + str(now) + '%20and%20status%3DOPEN'
            
            self.logger.debug(query)
            response = self.client.call_api(
                query, 'GET')
        
            try:
                response_text = response.read().decode('utf-8')
                response_body = json.loads(response_text)

                if (response.code == 200):
                    return response_body
                else:
                    raise ValueError(json.dumps(
                        response_body,
                        indent=4,
                        sort_keys=True))

            except ValueError as e:
                self.logger.error('%s.getOffenses failed, api call returned http %s',
                    __name__, str(response.code))
                raise

        except Exception as e:
            self.logger.error('getOffenses failed', exc_info=True)
            raise
```

You can create addtional functions to be able to enrich this data later on within `integration.py`

```
def getSourceIPs(self, offense):
    if not "source_address_ids" in offense:
        return []

    queue = Queue()
    proc = Process(target=self.getAddressesFromIDs, args=("source_addresses", "source_ip", offense["source_address_ids"], queue,))
    proc.start()
    try:
        res = queue.get(timeout=int(self.cfg.get('QRadar', 'api_timeout')))
        proc.join()
        return res
    except:
        proc.terminate()
        self.logger.error('%s.getSourceIPs took too long, aborting', __name__, exc_info=True)
        return []
```

When you have the data prepared it is time to continue on the `integration.py`. Start with calling the functions from `connector.py` to collect the data.

```
offensesList = qradarConnector.getOffenses(timerange)
```

Then use the models from TheHive4Py to transform the collected data into the Alert you want to have in The Hive.

```
def qradarOffenseToHiveAlert(offense):

    def getHiveSeverity(offense):
        #severity in TheHive is either low, medium or high
        #while severity in QRadar is from 1 to 10
        #low will be [1;4] => 1
        #medium will be [5;6] => 2
        #high will be [7;10] => 3
        if offense['severity'] < 5:
            return 1
        elif offense['severity'] < 7:
            return 2
        elif offense['severity'] < 11:
            return 3

        return 1

    #
    # Creating the alert
    #

    # Setup Tags
    tags = ['QRadar', 'Offense', 'Synapse']
    
    #Check if the automation ids need to be extracted
    if cfg.getboolean('QRadar', 'extract_automation_identifiers'):
        
        #Run the extraction function and add it to the offense data
        #Extract automation ids
        tags_extracted = tagExtractor(offense, cfg.get('QRadar', 'automation_fields'), cfg.get('QRadar', 'tag_regexes'))
        #Extract any possible name for a document on a knowledge base
        offense['use_case_names'] = tagExtractor(offense, cfg.get('QRadar', 'automation_fields'), cfg.get('QRadar', 'uc_kb_name_regexes'))
        if len(tags_extracted) > 0:
            tags.extend(tags_extracted)
        else:
            logger.info('No match found for offense %s', offense['id'])
    
    #Check if the mitre ids need to be extracted
    if cfg.getboolean('QRadar', 'extract_mitre_ids'):
        #Extract mitre tactics
        offense['mitre_tactics'] = tagExtractor(offense, ["rules"], ['[tT][aA]\d{4}'])
        if 'mitre_tactics' in offense:
            tags.extend(offense['mitre_tactics'])

        #Extract mitre techniques
        offense['mitre_techniques'] = tagExtractor(offense, ["rules"], ['[tT]\d{4}'])
        if 'mitre_techniques' in offense:
            tags.extend(offense['mitre_techniques'])

    if "categories" in offense:
        for cat in offense['categories']:
            tags.append(cat)

    defaultObservableDatatype = ['autonomous-system',
                                'domain',
                                'file',
                                'filename',
                                'fqdn',
                                'hash',
                                'ip',
                                'mail',
                                'mail_subject',
                                'other',
                                'regexp',
                                'registry',
                                'uri_path',
                                'url',
                                'user-agent']

    artifacts = []
    for artifact in offense['artifacts']:
        if artifact['dataType'] in defaultObservableDatatype:
            hiveArtifact = theHiveConnector.craftAlertArtifact(dataType=artifact['dataType'], data=artifact['data'], message=artifact['message'], tags=artifact['tags'])
        else:
            artifact_tags = list()
            artifact_tags.append('type:' + artifact['dataType'])
            hiveArtifact = theHiveConnector.craftAlertArtifact(dataType='other', data=artifact['data'], message=artifact['message'], tags=tags)
        artifacts.append(hiveArtifact)

    #Retrieve the configured case_template
    qradarCaseTemplate = cfg.get('QRadar', 'case_template')
        
    # Build TheHive alert
    alert = theHiveConnector.craftAlert(
        "{}, {}".format(offense['id'], offense['description']),
        craftAlertDescription(offense),
        getHiveSeverity(offense),
        offense['start_time'],
        tags,
        2,
        'Imported',
        'internal',
        'QRadar_Offenses',
        str(offense['id']),
        artifacts,
        qradarCaseTemplate)
```

Feel free to look at other modules to see how this can be achieved. I always try to use functions here to keep the main function readable and easy to understand, but this is not obligated. Standards still have to be written on this matter.

When you have an Alert model that contains all the right data you can use TheHive module `connector.py` to import the function that can create the Alert.

```
theHiveEsAlertId = theHiveConnector.createAlert(theHiveAlert)['id']
```

Finally you can work on the response the API request will receive. This can be returned in the function that is triggered by the `validateRequest` function. within the `validateRequest` function the return value should be parsed through `json.dumps()` and in the following format: `json.dumps(<return info>), <HTTP status code>`. You can refer to the QRadar example in this document. 

After this step, the module is more or less finished and can be used. There are options to extend the module to also synchronize changes through Alert updates, but this is optional.

### Creating Automation Tasks
