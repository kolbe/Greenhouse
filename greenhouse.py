#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2014-18 Richard Hull and contributors
# See LICENSE.rst for details.
# PYTHON_ARGCOMPLETE_OK

from __future__ import unicode_literals

import os
import sys
import json
import threading
import signal
from multiprocessing import Process, Array
import time
import traceback

from PIL import Image, ImageDraw, ImageFont

import RPi.GPIO as GPIO
from Adafruit_SHT31 import *
import Adafruit_DHT
from Adafruit_IO import *
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

from luma.core.render import canvas
from luma.core.interface.serial import spi
from luma.oled.device import ssd1306

device = ssd1306(spi(device=0, port=0, gpio_DC=23, gpio_RST=24))
dw = device.width
dh = device.height

sensorSHT = SHT31(address=0x44)
sensorDHT = Adafruit_DHT.AM2302
sensorDHTpin = 27

aio_key = os.environ['AIO_KEY']
aio_user = os.environ['AIO_USER']

default_cmd_json = '{"cmd":"message","value":[{"font":"butterfly.ttf", "msg":"A"},{"font":"arista_light.ttf","msg":"I love you, mom!"},{"font":"jandaflowerdoodles.ttf","msg":"A"}]}'

def connected(client):
    print 'Connected to Adafruit IO!  Listening for Greenhouse Commands...'
    client.subscribe('GreenhouseCmds')
def disconnected(client):
    # Disconnected function will be called when the client disconnects.
    print 'Disconnected from Adafruit IO!'
    sys.exit(1)
def message(client, feed_id, payload, retain):
    print 'Adafruit IO Feed {0} received new value: {1}'.format(feed_id, payload)
    if feed_id == 'GreenhouseCmds':
        execCmd(payload)

def awsiotmessage(client, userdata, message):
    print 'AWS IoT Feed {0} received new value: {1}'.format(message.topic, message.payload)
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

class Alarm(object):
    alarmPin = 21
    def __init__(self, duration=5):
        GPIO.setup(self.alarmPin, GPIO.OUT)
        self.duration = duration
        self.thread = threading.Thread(target=self.run, args=())
        self.thread.daemon = True
        self.alarmPwm = GPIO.PWM(self.alarmPin, 4000)

    def run(self):
        self.alarmPwm.start(50)
        start = time.time()
        while time.time() < start + self.duration:
            for dc in [4000, 5500]: #range(3000, 7000, 200):
                self.alarmPwm.ChangeFrequency(dc)
                time.sleep(0.5)
        self.alarmPwm.stop()


class ServiceExit(Exception): pass

def service_shutdown(signum, frame):
    print 'Caught signal {}'.format(signum)
    raise ServiceExit

class Text(object):
    def __init__(self, text, font):
        self.text = text
        self.font = font
#        self.w, self.h = draw.textsize(text=text, font=font)
#    def paint(self, x, y):
#        self.draw.text((x,y), text=self.text, font=self.font, fill="white")

status_font_file = "cqmono.otf"
font_file = "somethinglooksnatural.otf"

def make_font(name, size):
    font_path = os.path.abspath(os.path.join(
        '/usr/local/share/fonts/', name))
    return ImageFont.truetype(font_path, size)

fonts = {}
fonts["status"] = make_font(status_font_file, 20)
fonts["font"] = make_font(font_file, 44)

class MessageChar(object):
    def __init__(self, c, font, w, h):
        self.c = c
        self.font = font
        self.w = w
        self.h = h

class MessageString(object):
    def __init__(self, device):
        self.strings = []
        self.chars = []
        self.device = device
        self.w = 0

    def reset(self):
        self.strings = []
        self.chars = []
        self.w = 0

    def append(self, msg):
        draw = ImageDraw.Draw(Image.new(self.device.mode, self.device.size))
        self.strings.append(msg)
        for _, c in enumerate(msg.text):
            char_width, char_height = draw.textsize(c, font=msg.font)
            char = MessageChar(c, msg.font, char_width, char_height)
            self.chars.append(char)
            self.w += char.w

class MainMessage(MessageString):
    def paint(self, draw, i):
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
    def paint(self, draw, i):
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

def pollSensor(result):
    while True:
        def readDHT():
            humidity, temperature = Adafruit_DHT.read_retry(sensorDHT, sensorDHTpin, delay_seconds=0.2, retries=5)
            if humidity is not None and temperature is not None:
                temperature = temperature * 9/5 + 32
                print "Got new stats! Temp {} and humidity {}".format(temperature, humidity)
                return temperature, humidity
            else:
                sys.stderr.write("Could not read temperature and humidity from DHT sensor!\n")
                return None, None

        def readSHT():
            temperature = sensorSHT.read_temperature() * 9/5 + 32
            humidity = sensorSHT.read_humidity()
            return temperature, humidity

        degrees, humidity = readDHT()
        if degrees != None and humidity != None:
            result[0] = degrees
            result[1] = humidity
        time.sleep(5)


def main():
    global msg
    msg = MainMessage(device)

    aiorest = Client(aio_key)
    aiomqtt = MQTTClient(aio_user, aio_key)

    awsiot = AWSIoTMQTTClient("BaskGreenhouse", useWebsocket=True)
    awsiot.configureEndpoint(os.environ['AWSIOT_ENDPOINT'], 443)
    awsiot.configureCredentials("/usr/local/share/ca-certificates/awsiot.pem")

    awsiot.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
    awsiot.configureDrainingFrequency(2)  # Draining: 2 Hz
    awsiot.configureConnectDisconnectTimeout(10)  # 10 sec
    awsiot.configureMQTTOperationTimeout(5)  # 5 sec

    stat = StatusMessage(device)

    envResult = Array('d', 2)
    sensorProc = Process(target=pollSensor, args=[envResult])
    sensorProc.start()

    tempAlarm = Alarm()

    def readSensor():
        degrees = envResult[0]
        humidity = envResult[1]
        if degrees < 40.0 and not tempAlarm.thread.is_alive():
            tempAlarm.thread.start()
        aiomqtt.publish('GreenhouseTemp', degrees)
        aiomqtt.publish('GreenhouseHumidity', humidity)
        awsiot.publish('Greenhouse/Stats', json.dumps({"temperature":degrees, "humidity":humidity}, separators=(',', ':')), 0)
        print "Read temp of {} and humidity of {}".format(degrees, humidity)
        stat.reset()
        stat.append(Text('{0:0.1f}ºF, {1:0.1f}%'.format(degrees, humidity), fonts["status"]))

    signal.signal(signal.SIGTERM, service_shutdown)
    signal.signal(signal.SIGINT, service_shutdown)

    try:
        sensorThread = Every(5, readSensor)

        aiomqtt.connect()
        aiomqtt.loop_background()
        aiomqtt.on_connect = connected
        aiomqtt.on_disconnect = disconnected
        aiomqtt.on_message = message

        awsiot.connect()
        awsiot.subscribe(str("Greenhouse/Cmds"), 1, awsiotmessage)

        sensorThread.start()

        last_cmd = str(aiorest.receive('GreenhouseCmds').value)
        if last_cmd:
            print "Read previous GreenhouseCmd of {}".format(last_cmd)
            execCmd(last_cmd)
        else:
            execCmd(default_cmd_json)

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
