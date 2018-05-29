#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2014-18 Richard Hull and contributors
# See LICENSE.rst for details.
# PYTHON_ARGCOMPLETE_OK

from __future__ import unicode_literals

import os
import sys
import random
import json
import threading, signal
import time, traceback

from PIL import Image, ImageDraw, ImageFont

from Adafruit_SHT31 import *
import Adafruit_DHT
from Adafruit_IO import *
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

from luma.core.render import canvas
from luma.core.interface.serial import spi
from luma.oled.device import ssd1306

default_cmd_json = '{"cmd":"message","value":[{"font":"butterfly.ttf", "msg":"A"},{"font":"arista_light.ttf","msg":"I love you, mom!"},{"font":"jandaflowerdoodles.ttf","msg":"A"}]}'

device = ssd1306(spi(device=0, port=0, gpio_DC=23, gpio_RST=24))
dw = device.width
dh = device.height

aio_key = os.environ['AIO_KEY']
aiorest = Client(aio_key)
aiomqtt = MQTTClient(os.environ['AIO_USER'], aio_key)

awsiot = AWSIoTMQTTClient("BaskGreenhouse", useWebsocket=True)
awsiot.configureEndpoint(os.environ['AWSIOT_ENDPOINT'], 443)
awsiot.configureCredentials("/usr/local/share/ca-certificates/awsiot.pem")

awsiot.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
awsiot.configureDrainingFrequency(2)  # Draining: 2 Hz
awsiot.configureConnectDisconnectTimeout(10)  # 10 sec
awsiot.configureMQTTOperationTimeout(5)  # 5 sec


def connected(client):
    print('Connected to Adafruit IO!  Listening for Greenhouse Commands...')
    client.subscribe('GreenhouseCmds')
def disconnected(client):
    # Disconnected function will be called when the client disconnects.
    print('Disconnected from Adafruit IO!')
    sys.exit(1)
def message(client, feed_id, payload, retain):
    print('Adafruit IO Feed {0} received new value: {1}'.format(feed_id, payload))
    if feed_id == 'GreenhouseCmds':
        execCmd(payload)

def awsiotmessage(client, userdata, message):
    print('AWS IoT Feed {0} received new value: {1}'.format(message.topic, message.payload))
    if message.topic == 'Greenhouse/Cmds':
        execCmd(message.payload)


class Every(threading.Thread):
    def __init__(self, delay, task):
        threading.Thread.__init__(self)
        self.shutdown_flag = threading.Event()

        self.delay = delay
        self.task = task

    def run(self):
      next_time = time.time() + self.delay
      while not self.shutdown_flag.is_set():
        try:
          self.task()
        except Exception:
          traceback.print_exc()
        time.sleep(max(0, next_time - time.time()))
        # skip tasks if we are behind schedule:
        next_time += (time.time() - next_time) // self.delay * self.delay + self.delay

class ServiceExit(Exception): pass


def service_shutdown(signum, frame):
    print('Caught signal %d' % signum)
    raise ServiceExit

class Text:
    def __init__(self, text, font):
        self.text = text
        self.font = font
#        self.w, self.h = draw.textsize(text=text, font=font)
#    def paint(self, x, y):
#        self.draw.text((x,y), text=self.text, font=self.font, fill="white")

status_font_file="cqmono.otf"
font_file="somethinglooksnatural.otf"

sensorSHT = SHT31(address = 0x44)
sensorDHT = Adafruit_DHT.AM2302
sensorDHTpin = 27



def make_font(name, size):
    font_path = os.path.abspath(os.path.join(
    #    os.path.dirname(__file__)
    '/usr/local/share/fonts/', name))
    return ImageFont.truetype(font_path, size)

fonts = {}
fonts["status"] = make_font(status_font_file, 20)
fonts["font"] = make_font(font_file, 44)

class MessageChar():
    def __init__(self, c, font, w, h):
        self.c = c
        self.font = font
        self.w = w
        self.h = h

class MessageString():
    def __init__(self, device):
        self.strings = []
        self.chars = []
        self.device = device
        self.w = 0

    def reset(self):
        self.strings = []
        self.chars = []
        self.w = 0

    def append(self,msg):
        draw = ImageDraw.Draw(Image.new(self.device.mode, self.device.size))
        self.strings.append(msg)
        for j, c in enumerate(msg.text):
            char_width, char_height = draw.textsize(c, font=msg.font)
            char = MessageChar(c, msg.font, char_width, char_height)
            self.chars.append(char)
            self.w += char.w

class sensorResult:
    def __init__(self):
        self.degrees = 0.0
        self.humidity = 0.0

class MainMessage(MessageString):
    def paint (self, draw, i):
        if i % (dw + self.w) == 0:
            x = dw
        else:
            x = dw - (i % (dw + self.w))

        for c in self.chars:
            # Stop drawing if off the right side of screen.
            if x > dw:
                break
            # Calculate width but skip drawing if off the left side of screen.
            if x < -c.w:
                x += c.w
                continue
            # Calculate offset from sine wave.
            # y = offset+math.floor(amplitude*math.sin(x/float(width)*2.0*math.pi))
            # Draw text.
            draw.text((x, dh - c.h), c.c, font=c.font, fill=255)
            # Increment x position based on chacacter width.
            x += c.w

class StatusMessage(MessageString):
    def paint (self, draw, i):
        if i % (dw + self.w) == 0:
            x = 0 
        else:
            x = i % (dw + self.w)
        #print "i: {}, x: {}".format(i,x) 

        for c in reversed(self.chars):
            # Stop drawing if off the left side of the screen
            if x < -c.w:
                break
                #continue
            # Calculate width but skip drawing if off the right side of the screen
            if x > dw:
                x -= c.w
                continue
            draw.text((x, 0), c.c, font=c.font, fill=255)
            x -= c.w


def execCmd(cmd_json):
    global msg
    try:
        cmd = json.loads(cmd_json)
    except ValueError as err:
        sys.stderr.write('Could not parse JSON: {}'.format(err)) 
        return
        
    if cmd["cmd"] == "message":
        msg.reset()
        msg_parts = cmd["value"]
        for string in msg_parts:
            if string["font"] in fonts:
                f = fonts[string["font"]]
            else:
                try: 
                    f = make_font(string["font"], 44)
                except:
                    print "Could not load font {}".format(string["font"])
                    f = fonts["font"]
            msg.append(Text(string["msg"], f))


def main(num_iterations=sys.maxsize):
    global msg
    msg = MainMessage(device)

    sht = sensorResult()
    running = 1

    stat = StatusMessage(device)

    def pollSensor():

        def readDHT():
            humidity, temperature = Adafruit_DHT.read_retry(sensorDHT, sensorDHTpin, delay_seconds=0.2, retries=5)
            if humidity is not None and temperature is not None:
                return temperature * 9/5 + 32, humidity
            else:
                sys.stderr.write("Could not read temperature and humidity from DHT sensor!\n")

        def readSHT():
            sht.degrees = sensorSHT.read_temperature() * 9/5 + 32
            sht.humidity = sensorSHT.read_humidity()

        sht.degrees, sht.humidity = readDHT()
        aiomqtt.publish('GreenhouseTemp', sht.degrees)
        aiomqtt.publish('GreenhouseHumidity', sht.humidity)
        awsiot.publish('Greenhouse/Stats', json.dumps({"temperature":sht.degrees,"humidity":sht.humidity},separators=(',',':')),0)
        print "Read temp of {} and humidity of {}".format(sht.degrees,sht.humidity)
        stat.reset()
        stat.append(Text('{0:0.1f}ºF, {1:0.1f}%'.format(sht.degrees, sht.humidity), fonts["status"]))

    signal.signal(signal.SIGTERM, service_shutdown)
    signal.signal(signal.SIGINT, service_shutdown)

    try:
	sensorThread = Every(5, pollSensor)

	aiomqtt.connect()
	aiomqtt.loop_background()
	aiomqtt.on_connect    = connected
	aiomqtt.on_disconnect = disconnected
	aiomqtt.on_message    = message

        awsiot.connect()
        awsiot.subscribe(str("Greenhouse/Cmds"), 1, awsiotmessage)
        
	sensorThread.start()

        last_cmd = str(aiorest.receive('GreenhouseCmds').value)
        if last_cmd:
            print "Read previous GreenhouseCmd of {}".format(last_cmd)
            execCmd(last_cmd)
        else:
            execCmd(default_json_cmd)

	i = 0L
	while True:
	    with canvas(device) as draw:
		stat.paint(draw, i)
                msg.paint(draw, i)
		i += 1
    #except ServiceExit: pass
    except: 
        #sys.stderr.write('ERROR: %sn' % str(err))
        raise

    finally:
        sensorThread.shutdown_flag.set()
        if sensorThread.isAlive(): sensorThread.join() 
        aiomqtt.disconnect()
        awsiot.disconnect()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
