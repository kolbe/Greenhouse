#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2014-18 Richard Hull and contributors
# See LICENSE.rst for details.
# PYTHON_ARGCOMPLETE_OK

from __future__ import unicode_literals

from decimal import *
import os
import sys
import json
import random
import datetime
import signal
import threading
from multiprocessing import Process, Array
import time
import traceback

from PIL import Image, ImageDraw, ImageFont

import RPi.GPIO as GPIO
import Adafruit_SHT31 as SHT
import Adafruit_DHT as DHT
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient, AWSIoTMQTTShadowClient

from luma.core.render import canvas
from luma.core.interface.serial import spi
from luma.oled.device import ssd1306

unbuffered = os.fdopen(sys.stdout.fileno(), 'w', 0)
sys.stdout = unbuffered

tempAlarmMin = Decimal('40.0')
tempAlarmMax = Decimal('100.0')

device = ssd1306(spi(device=0, port=0, gpio_DC=23, gpio_RST=24), rotate=0)
dw = device.width
dh = device.height

sensorSHT = SHT.SHT31(address=0x44)
sensorDHT = DHT.AM2302
sensorDHTpin = 27

green_pin = 17
black_pin = 18

def awsiotmessage(client, userdata, message):
    print 'AWS IoT Feed {0} received new value: {1}'.format(message.topic, message.payload)
    if message.topic == 'Greenhouse/Cmds':
        execCmd(message.payload)


class Every(threading.Thread):
    def __init__(self, delay, task):
        threading.Thread.__init__(self)
        self.daemon = True
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
        self.active = False

    def alarm(self):
        self.active = True
        self.thread = threading.Thread(target=self.run, args=())
        self.thread.daemon = True
        self.alarmPwm = GPIO.PWM(self.alarmPin, 4000)
        self.thread.start()
        del self.thread

    def run(self):
        self.alarmPwm.start(50)
        start = time.time()
        while time.time() < start + self.duration:
            for dc in [4000, 5500]:
                self.alarmPwm.ChangeFrequency(dc)
                time.sleep(0.5)
        self.alarmPwm.stop()
        self.active = False

class ServiceExit(Exception):
    pass

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
fonts["status"] = make_font(status_font_file, 32)
fonts["font"] = make_font(font_file, 32)
fonts["butterfly"] = make_font('butterfly.ttf', 32)

class MessageChar(object):
    def __init__(self, c, font, w, h):
        self.c = c
        self.font = font
        self.w = w
        ascent, descent = font.getmetrics()
        self.h = ascent + descent

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
            draw.text((x, -5), c.c, font=c.font, fill=255)
            x -= c.w

def updateMsg(msg_parts):
    msg.reset()
    for string in msg_parts:
        if string["font"] in fonts:
            f = fonts[string["font"]]
        else:
            try:
                f = make_font(string["font"], 32)
            except:
                print "Could not load font {}".format(string["font"])
                f = fonts["font"]
        msg.append(Text(string["msg"], f))

def execCmd(cmd_json):
    global msg
    try:
        cmd = json.loads(cmd_json)
    except ValueError as err:
        sys.stderr.write('Could not parse JSON: {}'.format(err))
        return
    if cmd["cmd"] == "message":
        updateMsg(cmd["value"])

def shadowUpdate(payload, responseStatus, token):
    if responseStatus == 'timeout':
        pass
    if responseStatus == 'accepted':
        data = json.loads(payload)
    if responseStatus == 'rejected':
        pass

def handleShadow(state):
    print "handling shadow state message: {}".format(state)
    if "message" in state:
        print "new message: {}".format(state["message"])
        updateMsg(state["message"])

def shadowGet(payload, responseStatus, token):
    print "shadowDeltaGet responseStatus: {}".format(responseStatus)
    j = json.loads(payload)
    print "Shadow State (version {}): {}".format(j["version"], j["state"])
    handleShadow(j["state"]["desired"])

def shadowDelta(payload, responseStatus, token):
    print "shadowDelta responseStatus: {}".format(responseStatus)
    j = json.loads(payload)
    print "Shadow Delta (version {}): {}".format(j["version"], j["state"])
    handleShadow(j["state"])

def pollSensor(result):
    while True:
        def readDHT():
            humidity, temperature = DHT.read_retry(sensorDHT, sensorDHTpin, delay_seconds=0.2, retries=5)
            if humidity is not None and temperature is not None:
                temperature = temperature * 9/5 + 32
                #print "Got new stats! Temp {} and humidity {}".format(temperature, humidity)
                return temperature, humidity
            else:
                sys.stderr.write("Could not read temperature and humidity from DHT sensor!\n")
                return None, None

        def readSHT():
            temperature = sensorSHT.read_temperature() * 9/5 + 32
            humidity = sensorSHT.read_humidity()
            return temperature, humidity

        try:
            degrees, humidity = readDHT()
            # print "Read {} and {} from DHT".format(degrees, humidity)
        except:
            sys.stderr.write("Could not read from DHT sensor.")
            degrees = None
            humidity = None

        if degrees != None and humidity != None:
            result[0] = degrees
            result[1] = humidity

        #try:
        #    degrees, humidity = readSHT()
        #    print "Read {} and {} from SHT".format(degrees, humidity)
        #except:
        #    sys.stderr.write("Could not read from DHT sensor.")

        time.sleep(10)

def black_button_press(channel):
    print "Black button pressed"

def green_button_press(channel):
    print "Green button pressed!"
    msg.append(Text(chr(random.randrange(97, 122)), fonts['butterfly']))


def main():
    global msg
    msg = MainMessage(device)

    awsClientId = "BaskGreenhouseDevice"
    awsThingId = "BaskGreenhouse"
    awsiotRootCAPath = "/usr/local/share/ca-certificates/awsiot.pem"
    awsiot = AWSIoTMQTTClient(awsClientId, useWebsocket=True)
    awsiot.configureEndpoint(os.environ['AWSIOT_ENDPOINT'], 443)
    awsiot.configureCredentials(awsiotRootCAPath)

    awsiot.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
    awsiot.configureDrainingFrequency(2)  # Draining: 2 Hz
    awsiot.configureConnectDisconnectTimeout(10)  # 10 sec
    awsiot.configureMQTTOperationTimeout(5)  # 5 sec

    awsiotShadow = AWSIoTMQTTShadowClient(awsClientId+"Shadow", useWebsocket=True)
    awsiotShadow.configureEndpoint(os.environ['AWSIOT_ENDPOINT'], 443)
    awsiotShadow.configureCredentials(awsiotRootCAPath)

    awsiotShadow.configureAutoReconnectBackoffTime(1, 32, 20)
    awsiotShadow.configureConnectDisconnectTimeout(10)  # 10 sec
    awsiotShadow.configureMQTTOperationTimeout(5)  # 5 sec

    GPIO.setup(green_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(black_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    GPIO.add_event_detect(green_pin, GPIO.RISING, callback=green_button_press, bouncetime=300)
    GPIO.add_event_detect(black_pin, GPIO.RISING, callback=black_button_press, bouncetime=300)

    stat = StatusMessage(device)

    envResult = Array('d', 2)
    sensorProc = Process(target=pollSensor, args=[envResult])
    sensorProc.daemon = True
    sensorProc.start()

    tempAlarm = Alarm()

    class SensorReading(object):
        getcontext().prec = 5
        quant = Decimal('.01')
        def __init__(self, degrees='0.00', humidity='0.00'):
            self.d = Decimal(degrees)
            self.h = Decimal(humidity)
            self.ds = ''
            self.hs = ''
        def update(self, degrees, humidity):
            self.d = Decimal(degrees).quantize(self.quant)
            self.h = Decimal(humidity).quantize(self.quant)
            self.ds = str(self.d)
            self.di = int(round(self.d,0))
            self.hs = str(self.h)
            self.hi = int(round(self.h,0))

    sen = SensorReading()

    datafile = open('/home/pi/sensor.data', 'a', 1)
    def readSensor():
        sen.update(*envResult)
        if (sen.di == 0 and sen.hi == 0):
            print "Temperature and Humidity are both 0, skipping!"
            return
        if (sen.d < tempAlarmMin or sen.d > tempAlarmMax) and not tempAlarm.active:
            print "Alarming! {} between {} and {}".format(sen.d, tempAlarmMin, tempAlarmMax)
            #tempAlarm.alarm()
        awsiot.publish('Greenhouse/Stats', json.dumps({"ts":time.time(), "d":sen.ds, "h":sen.hs}, separators=(',', ':')), 0)
        datafile.write('\t'.join([ datetime.datetime.now().isoformat(), sen.ds, sen.hs ]) + '\n')
        #print "Read temp of {} and humidity of {}".format(sen.ds, sen.hs)
        stat.reset()
        stat.append(Text('{}ºF, {}%'.format(sen.di, sen.hi), fonts["status"]))

    signal.signal(signal.SIGTERM, service_shutdown)
    signal.signal(signal.SIGINT, service_shutdown)

    try:
        sensorThread = Every(5, readSensor)

        sensorThread.start()

        awsiot.connect()
        awsiot.subscribe(str("Greenhouse/Cmds"), 1, awsiotmessage)

        awsiotShadow.connect()
        deviceShadowHandler = awsiotShadow.createShadowHandlerWithName(awsThingId, True)
        deviceShadowHandler.shadowGet(shadowGet, 5)
        deviceShadowHandler.shadowRegisterDeltaCallback(shadowDelta)

        i = 0L
        while True:
            with canvas(device) as draw:
                stat.paint(draw, i)
                msg.paint(draw, i)
                i += 1

    except ServiceExit:
        return 0
    except Exception as e:
        raise
    finally:
        sensorThread.shutdown_flag.set()
        if sensorThread.isAlive(): sensorThread.join()
        #awsiot.disconnect()
        #awsiotShadow.disconnect()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
