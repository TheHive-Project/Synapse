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
| 500             | Failed to create an alert from offense | ```{```<br>&nbsp;&nbsp;&nbsp;```"message": "[Errno 13] Permission denied: Failed to create alert from offense",```<br>    ```"offenses": [],```<br>    ```"success": false```<br>```}``` |

| Status | Response  |
| ------ | --------- |
| 200    | `json`                          |
|        | `   {`                          |
|        | ` "id": 10,`                    |
|        | ` "username": "alanpartridge",` |
|        | ` more code...`                 |
|        | `}`                             |
| 400    |                                 |

<table>
<tr>
<th>
Status
</th>
<th>
Response
</th>
</tr>

<tr>

<td>
<pre>
<br/><br/><br/>200<br/><br/><br/><br/><br/>400<br/>
</pre>
</td>

<td>
<pre>
json
  {
    "id": 10,
    "username": "alanpartridge",
    "email": "alan@alan.com",
    "password_hash": "$2a$10$uhUIUmVWVnrBWx9rrDWhS.CPCWCZsyqqa8./whhfzBZydX7yvahHS",
    "password_salt": "$2a$10$uhUIUmVWVnrBWx9rrDWhS.",
    "created_at": "2015-02-14T20:45:26.433Z",
    "updated_at": "2015-02-14T20:45:26.540Z"
}
</pre>
</td>

</tr>
</table>

##### Responses Samples

```
{
    "message": "[Errno 13] Permission denied: Failed to create alert from offense",
    "offenses": [],
    "success": false
}
```

## Version

### GET ```/version```

#### Description

Get Synapse's version.


#### Success & Error Responses

| Responses Codes | Description | Responses Samples |
| --------------- | ----------- | ----------------- |
| 200             | Get Synapse's version | ```{"version":"1.0"}``` |
