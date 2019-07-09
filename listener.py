#!/usr/bin/python3 -u
# coding: utf-8

import os
import time
import json
import traceback
import mysql.connector as mariadb
from botocore.credentials import InstanceMetadataProvider, InstanceMetadataFetcher
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient


db = mariadb.connect(user='greenhouse', password='', database='greenhouse')
cursor = db.cursor()
ins = "insert into sensorReadings (t, temp, humidity) values (from_unixtime(%(ts)s), %(d)s, %(h)s)"

provider = InstanceMetadataProvider(iam_role_fetcher=InstanceMetadataFetcher(timeout=1000, num_attempts=2))
creds = provider.load()

awsiot = AWSIoTMQTTClient("BaskGreenhouseListener", useWebsocket=True)
awsiot.configureEndpoint(os.environ['AWSIOT_ENDPOINT'], 443)
#awsiot.configureCredentials("/usr/local/share/ca-certificates/awsiot.pem")
awsiot.configureCredentials("/usr/share/ca-certificates/extra/AmazonRootCA1.pem")
awsiot.configureIAMCredentials(creds.access_key, creds.secret_key, creds.token)

def newMessage(client, userdata, message):
    try:
        j = json.loads(message.payload.decode('utf-8'))
        data = {'ts':j['ts'], 'd':j['d'], 'h':j['h']}
        #print("{}: new reading at {} of {}ºF and {}%".format(message.topic, time.ctime(j['ts']), j['d'], j['h']))
        cursor.execute(ins, data)
        db.commit()
    except Exception as e:
        print("Error handling new sensor message!")
        traceback.print_exc()


awsiot.connect()
awsiot.subscribe("Greenhouse/Stats", 1, newMessage)
print("Subscribed!")

while True:
    time.sleep(1)
