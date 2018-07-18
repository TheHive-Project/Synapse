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

![](docs/img/big-picture.png)

For detailed explanation on each workflows, have a look at the [workflows page](docs/workflows/README.md).   

*The QRadar connector is under development and the related workflows are not available yet.*   

## How to use

Have a look at the detailed [user guide](docs/user_guide.md), but in short:

   1. Install dependecies
   2. Fill in the config file
   3. Execute: ```python3 app.py```

While all OS running python3 can be used for Synapse, we recommend the use of Ubuntu.   

## Roadmap

   * Alert creation from QRadar offense
   * Closing QRadar offense after closing TheHive case or alert
   * Scheduler to periodically execute workflows

## Special thanks

Kudos to Erik Cederstrand for his amazing work on Exchangelib.   
Check his others projects [here](https://github.com/ecederstrand).   
