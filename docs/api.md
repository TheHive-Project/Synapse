# API Documentation

+ [Workflows](#workflows)
    + [/ews2case](#get-ews2case)
+ [Version](#version)
    + [/version](#get-version)

## Workflows

### GET ```/ews2case```

#### Description

Creating case from Microsoft Exchange emails.

#### Success & Error Responses

| Responses Codes | Description | Responses Samples |
| --------------- | ----------- | ----------------- |
| 200             | Successfully created a case from email | ```{"success":true}``` |
| 500             | Failed to create a case from email     | ```{"success":false}``` |

### GET ```/QRadar2alert```

#### Description

Creating alert from QRadar offenses.

#### Success & Error Responses

| Responses Codes | Description | Responses Samples |
| --------------- | ----------- | ----------------- |
| 500             | Failed to create an alert from offense | ```{```<br>   ```"message": "[Errno 13] Permission denied: Failed to create alert from offense",```<br>    ```"offenses": [],```<br>    ```"success": false```<br>```}``` |


## Version

### GET ```/version```

#### Description

Get Synapse's version.


#### Success & Error Responses

| Responses Codes | Description | Responses Samples |
| --------------- | ----------- | ----------------- |
| 200             | Get Synapse's version | ```{"version":"1.0"}``` |
