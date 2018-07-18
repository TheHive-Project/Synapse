# User Guide

This guide will go through installation and basic configuration for Synapse.   

+ [Installation](#installation)
    + [Dependecies](#dependecies)
+ [Configuration](#configuration)
    + [Synapse user](#synapse-user)
    + [api section](#api-section)
    + [TheHive section](#thehive-section)
+ [Start the app](#start-the-app)
+ [Deployment to Production](#deployment-to-production)

## Installation

### Dependecies

```
sudo pip3 install -r requirements.txt
```

## Configuration

### Synapse user
Before filling in the configuration file, create a new user in TheHive for Synapse with the following details:

```
Login:                     synapse
Full name:                 synapse
Roles:                     read, write
Additional Permissions:    ✓ Allow alerts creation
```

And create an API Key.   

Now edit the configuration file located at ```Synapse/conf/synapse.conf```.

### [api] section

The ```[api]``` section is related to the flask API settings. You can keep it as it is for ```debug```, ```host```, ```threaded``` value. You may want to change the default port ```5000```.

#### Example

```
[api]
debug:False
host:0.0.0.0
port:5000
threaded:True
```

### [TheHive] section

In this section, put in TheHive's url and the API Key previously created.

#### Example

```
[TheHive]
url:http://127.0.0.1:9000
user:synapse
api_key:r4n0O8SvEll/VZdOD8r0hZneOWfOmth6
```

Basic configuration for Synapse is done.   
To configure workflows, head to the [workflows page](workflows/README.md).

## Start the app

To start Synapse, run:

```
python3 app.py
```

## Deployment to Production

If you'd like to go live with Synapse, it is advised to use a WSGI server.
Have a look at the excellent tutorial from Miguel Grinberg [here](https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-xvii-deployment-on-linux-even-on-the-raspberry-pi) and especially the section named "Setting Up Gunicorn and Supervisor".
