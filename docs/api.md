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
      <pre>
        500
      </pre>
    </td>

    <td>
      <pre>
        Failed to create alert for a QRadar offense.
      </pre>
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
</table>


## Version

### GET ```/version```

#### Description

Get Synapse's version.


#### Success & Error Responses

| Responses Codes | Description | Responses Samples |
| --------------- | ----------- | ----------------- |
| 200             | Get Synapse's version | ```{"version":"1.0"}``` |
