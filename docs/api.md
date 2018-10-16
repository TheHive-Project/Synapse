# API Documentation

+ [Workflows](#workflows)
    + [/ews2case](#get-ews2case)
    + [/QRadar2alert](#post-qradar2alert)
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

### POST ```/QRadar2alert```

#### Description

Creating alert from QRadar offenses.

#### Parameters


| Parameter | Data Type | Description | Sample |
| --------------- | ----------- | ----------------- | ----------------- |
| "timerange"     | long        | Offenses created during the last <timerange> minutes will be imported as alert. | ```{"timerange"}:10``` |

#### Success & Error Responses


<table>
  <tr>
  <th>
    Responses Codes
  </th>
  <th>
    Description
  </th>
  <th>
    Responses Samples
  </th>
  </tr>
  
  <tr>
  <td>
    <p>
      200
    </p>
  </td>
  
  <td>
    <p>
      Overall success, all offenses have been imported as alert.
    </p>
  </td>
  
  <td>
    <pre>
{
    "offenses": [
        {
            "qradar_offense_id": 211,
            "raised_alert_id": "10329654dfbfbb49095c286db78604f0",
            "success": true
        },
        {
            "qradar_offense_id": 210,
            "raised_alert_id": "d6fb8965494eeff6fc04c0d07fb8d0ca",
            "success": true
        },
        {
            "qradar_offense_id": 209,
            "raised_alert_id": "42cee5a001675a519ee673b6a979e5a1",
            "success": true
        }
    ],
    "success": true
}
    </pre>
  </td>
  </tr>

  <tr>
  <td>
    <p>
      500
    </p>
  </td>
  
  <td>
    <p>
      Overall failure, all offenses have failed to be imported as alert.
    </p>
  </td>
  
  <td>
    <pre>
{
    "message": "[Errno 13] Permission denied: Failed to create alert from offense",
    "offenses": [],
    "success": false
}
    </pre>
  </td>
  </tr>

  <tr>
  <td>
    <p>
      500
    </p>
  </td>
  
  <td>
    <p>
      Partial failure, at least one offense failed to be imported as alert.
    </p>
  </td>
  
  <td>
    <pre>
{
    "offenses": [
        {
            "qradar_offense_id": 216,
            "raised_alert_id": "6e268713800b14793078a9930adcb89c",
            "success": true
        },
        {
            "message": "[alert][6103f34c02118f401983f69aef718927]: version conflict, document already exists (current version [1])",
            "offense_id": 213,
            "success": false
        }
    ],
    "success": false
}
    </pre>
  </td>
  </tr>
</table>

## Version

### GET ```/version```

#### Description

Get Synapse's version.


#### Success & Error Responses

| Responses Codes | Description | Responses Samples |
| --------------- | ----------- | ----------------- |
| 200             | Get Synapse's version | ```{"version":"1.1"}``` |
