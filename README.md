# Synapse

Synapse is a middleware application that allows you to connect TheHive with other security devices.   
It leverages TheHive API to automate case and alert creation.   

Case creation from email or alert creation from SIEM event are casual usecase for Synapse.   

## Big Picture

Most of the time, a usecase implies several actions and conditions.  
Synapse gathers those into workflows.   

In order to have the most user-friendly app possible, we decided to put an API on top of workflows.   
That way, you would only execute the workflow you are interrested in by "hitting" the corresponding API endpoint.   

Workflows implemented at the moment are:
   * Case creation from email thanks to Exchange Web Service
   * Alert creation from QRadar offenses

![](docs/img/big-picture.png)

For detailed explanation on each workflows, have a look at the [workflows page](docs/workflows/README.md).   

## How to use

Have a look at the detailed [user guide](docs/user_guide.md), but in short:

   1. Install dependecies
   2. Fill in the config file
   3. Execute: ```python3 app.py```

While all OS running python3 can be used for Synapse, we recommend the use of Ubuntu.   

## Running in Docker

   1. Build Image: ```docker build -t synapse .```
   2. Run Container: ```docker run -d --name synapse -p 5000:5000 synapse```
   
   You can also mount the config file for easier adjustments
   ```docker run -d --name synapse -v ${pwd}/conf/synapse.conf:/opt/synapse/conf/synapse.conf -p 5000:5000 synapse```

## Roadmap

   * Alert creation from QRadar offense
   * Closing QRadar offense after closing TheHive case or alert
   * Scheduler to periodically execute workflows

## Special thanks

Kudos to Erik Cederstrand for his amazing work on Exchangelib.   
Check his others projects [here](https://github.com/ecederstrand).   

Kudos to IBM teams for providing a python QRadar API client to the community.   
Check it [here](https://github.com/ibm-security-intelligence/api-samples).   
