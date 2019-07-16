#!/usr/bin/python3 -u
# coding: utf-8

import os
import time
import json
import logging
import traceback
import mysql.connector as mariadb
from botocore.credentials import InstanceMetadataProvider, InstanceMetadataFetcher
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

# Configure logging
logger = logging.getLogger("AWSIoTPythonSDK.core")
logger.setLevel(logging.DEBUG)
streamHandler = logging.StreamHandler()
formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

db = mariadb.connect(user='greenhouse', password='', database='greenhouse')
cursor = db.cursor()
ins = "insert into sensorReadings (t, temp, humidity) values (from_unixtime(%(ts)s), %(d)s, %(h)s)"

awsiot = AWSIoTMQTTClient("BaskGreenhouseListener", useWebsocket=True)
awsiot.configureEndpoint(os.environ['AWSIOT_ENDPOINT'], 443)
awsiot.configureCredentials("/usr/share/ca-certificates/extra/AmazonRootCA1.pem")

provider = InstanceMetadataProvider(iam_role_fetcher=InstanceMetadataFetcher(timeout=1000, num_attempts=2))


def mqttConnect():
    creds = provider.load()
    awsiot.configureIAMCredentials(creds.access_key, creds.secret_key, creds.token)
    awsiot.connect()
    awsiot.subscribe("Greenhouse/Stats", 1, newMessage)
    print("Subscribed!")


def newMessage(client, userdata, message):
    global cursor
    j = json.loads(message.payload.decode('utf-8'))
    data = {'ts':j['ts'], 'd':j['d'], 'h':j['h']}
    while True:
        try:
            cursor.execute(ins, data)
            db.commit()
        except mariadb.errors.DataError as e:
            print("DataError: {} ... skipping.".format(e))
            traceback.print_exc()
        except mariadb.errors.DatabaseError as e:
            print("DatabaseError: {} ... reconnecting.".format(e))
            db.reconnect(attempts=99999, delay=1)
            cursor = db.cursor()
            continue
        except Exception as e:
            print("Error handling new sensor message!")
            traceback.print_exc()
        #print("{}: inserted new reading at {} of {}ºF and {}%".format(message.topic, time.ctime(j['ts']), j['d'], j['h']))
        break

awsiot.onOffline = mqttConnect
mqttConnect()

while True:
    #if not awsiot._mqtt_core._internal_async_client._paho_client._thread or not awsiot._mqtt_core._internal_async_client._paho_client._thread.is_alive():
    time.sleep(1)
