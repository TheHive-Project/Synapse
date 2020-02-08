# Ews2Alert


+ [Demo](#demo)
    + [Automatic alert creation](#automatic-alert-creation)
+ [Configuration](#configuration)
    + [Exchange server](#exchange-server)
    + [ews2Alert config](#ews2Alert-config)
+ [Links and Information](#links-and-information)
    + [Cronjob](#cronjob)
    + [REGEX](#regex)

```Ews2Alert``` is a modification of ```Ews2Case``` to facilitate Alert creation (instead of Cases) from Microsoft Exchange emails.

This workflow is intended for all IDS E-Mail Notifications or security relevant E-Mails that are not automatically "Case-Worthy", but rather should be looked at as an alert and made into cases on an "alert-by-alert" basis by a Team-Member.

Key differences to Ews2Case:

- You can't use the "Assign via Category" functionality due to how alert creation works
- Alerts created will not update themselves "out of the box".
- Ews2Alert is intentionally left highly self configurable due to how many different Use-Cases for E-Mail imports exist

### Demo

Our fictional Company is using a Sophos UTM Firewall with Packet Inspection (SNORT) aktive.

Whenever SNORT detects potentially malicious activity, it reports said activity to a Mailbox called IT-Sicherheit

![](../img/ews2alert/1-intrusion-notification.PNG)

In our case, this Mail gets auto-sorted into the folder "TheHive" based on rules set in the Mailbox itself.

![](../img/ews2alert/2-mailbox-TheHive.PNG)

Now, either a Team-Member can manualy trigger the Workflow by either using Curl:

```curl some.fictionaldomain.com/ews2alert
{"success":true}```

Or, like in our Demo, by setting up a Cronjob on the TheHive server to do this automatically in a set time interval.

'''* * * * * curl --silent http://localhost:5000/ews2alert```

This particular Cronjob triggers the ews2alert workflow every minute of every hour for every day.

In case an alert creation fails, the logs to troubleshoot the issue are located at ```Synaspe/logs/synapse.log```.

TheHive UI now shows a new created Alert.

![](../img/ews2alert/3-created-alert-ui.PNG)

Due to the way this particular Demo was configured, the ```title``` was Populated with the actual intrusion type instead of for example the subject of the E-Mail.
In the case of our Demo-Company and its SNORT setup, this is to prevent all created Alerts from only displaying "[any.domain.de][CRIT-852] Intrusion Prevention Alert (Packet dropped)" as a ```title```, making intresting reports not immediatly visible. This is because this Companys SNORT Alerts do not come with their own unique identifier in the subject.

![](../img/ews2alert/4-alert-info.PNG)

As you can see, the description and other fields of the Alert have been populated

### Configuration

For configuration of the EWS module, please see the documentation of "Ews2Case", specifically the point "Exchange server"

Ews2Alert creates alerts based of the basic alert variables which you can read up on HERE.

You can configure the ews2Alert workflow by navigating to your Synapse workflow folder and using nano.

```cd YourPathToSynapse/Synapse/workflows```
```sudo nano ews2Alert.py```

The default configuration part looks like this:

```title = msg.subject
description = msg.text_body
severity = 2
date = time.time() * 1000
tags = "YourTag1","YourTag2"
tlp = 2
status = "New"
type = "YourTypeHere"
source = "YourSourceHere"
sourceRef = "Snort Export, ID " + str(date)
artifacts = ""
caseTemplate = ""```

Explanations:

```title = msg.subject```: the default title of the alert is the E-Mail subject

If you want to change the title of your alert to something more like shown in the Demo, you can use Pythons ```regex``` to for example search for specific strings in the Mail-Body.

In the case of the Demo, we used
```title = re.search('(?<=Message........: )(.*)(?=\n)', msg.text_body).group(1)```
to search for everything behind ```Message........: ``` and before the next new line. In case of the Demos SNORT alerts, this will yield the intrusion type as a title.

For more information on how to use ```regex``` and a builder for your custom string, please see the "Links and Information" chapter at the end of this document

```description = msg.text_body```
The default description of the alert is the Mail-Body (This was used in the Demo).

```severity = 2```
The default severity (This was used in the Demo).

```date = time.time() * 1000```
The date when the alert was created, which in this case is the time of import into TheHive

```tags = "YourTag1","YourTag2"```
The default tags, seperated by comma (The Demo used "IDS","SNORT").

```tlp = 2```
The default tlp (This was used in the Demo).

```status = "New"```
The default status (This was used in the Demo).

```type = "YourTypeHere"```
The default type (The Demo used "Intrusion Detection").

```source = "YourSourceHere"```
The default source (The Demo used "SNORT").

```sourceRef = "YourSourceRefHere"```
The default sourceRef. For the Demo, we generated a Unique ID for the ```sourceRef``` variable by appending the ```date``` variable behind a string:
```"Snort Export, ID " + str(date)```

```artifacts = ""```
The default artifacts, in this case empty

```caseTemplate = ""```
The default case Template, in this case empty
