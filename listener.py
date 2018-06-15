#!/usr/bin/python
# coding: utf-8

import os
import time
import json
from botocore.credentials import InstanceMetadataProvider, InstanceMetadataFetcher


from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

provider = InstanceMetadataProvider(iam_role_fetcher=InstanceMetadataFetcher(timeout=1000, num_attempts=2))
creds = provider.load()

awsiot = AWSIoTMQTTClient("BaskGreenhouseListener", useWebsocket=True)
awsiot.configureEndpoint(os.environ['AWSIOT_ENDPOINT'], 443)
awsiot.configureCredentials("/usr/local/share/ca-certificates/awsiot.pem")
awsiot.configureIAMCredentials(creds.access_key, creds.secret_key, creds.token)

def newMessage(client, userdata, message):
    j = json.loads(message.payload)
    print "{}: new reading at {} of {}ºF and {}%".format(message.topic, time.ctime(j['ts']), j['d'], j['h'])

awsiot.connect()
awsiot.subscribe("Greenhouse/Stats", 1, newMessage)
print "Subscribed!"

while True:
    time.sleep(1)
