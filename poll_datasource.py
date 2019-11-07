#!/usr/bin/python
import os
import time
import json
import datetime
import urlparse
import mysql.connector as mariadb
db = mariadb.connect(user='greenhouse', password='', database='greenhouse')
cursor = db.cursor()

stmt = "select grp*60 ts, round(avg(temp),1) d, round(avg(humidity),1) h from sensorReadings where grp > %s/60 group by grp"
#stmt = "select unix_timestamp(t), temp, humidity from sensorReadings where t > %s"

qs = urlparse.parse_qs(os.environ.get('QUERY_STRING',''))

startTime = time.time() - 30*24*3600;
if 'startTime' in qs:
   startTime = qs['startTime'][0]

cursor.execute( stmt, (startTime, ) )

data = []

for row in cursor:
    data.append([datetime.datetime.fromtimestamp(row[0]), float(row[1]), float(row[2])])

class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)

print "Content-type: application/json"
print
print json.dumps(data, cls=DateTimeEncoder)
