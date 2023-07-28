# Trigger <QRadar2alert> FUNC (Change the token with the a valid token in conf/synpase.conf)
curl -H "Content-Type: application/json" -XPOST -d '{"timerange":10,"token":"CHANGE_ME"}'  http://127.0.0.1:5000/QRadar2alert
