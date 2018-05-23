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
from Adafruit_IO import *

from luma.core.render import canvas
from luma.core.interface.serial import spi
from luma.oled.device import ssd1306

default_cmd_json = '{"cmd":"message","value":[{"font":"butterfly_font", "msg":"A"},{"font":"font","msg":"I love you, mom!"},{"font":"flower_font","msg":"A"}]}'

device = ssd1306(spi(device=0, port=0, gpio_DC=23, gpio_RST=24))

aio_key = 'cd202c9bdc424c498eb586e81a2eeafb'
aio = Client(aio_key)
client = MQTTClient('kmksea', aio_key)

def connected(client):
    print('Connected to Adafruit IO!  Listening for Greenhouse Commands...')
    client.subscribe('GreenhouseCmds')
def disconnected(client):
    # Disconnected function will be called when the client disconnects.
    print('Disconnected from Adafruit IO!')
    sys.exit(1)
def message(client, feed_id, payload, retain):
    global message
    print('Feed {0} received new value: {1}'.format(feed_id, payload))
    if feed_id == 'GreenhouseCmds':
        execCmd(payload)


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
    def __init__(self, text, draw, font):
        self.draw = draw
        self.text = text
        self.font = font
        self.w, self.h = draw.textsize(text=text, font=font)
    def paint(self, x, y):
        self.draw.text((x,y), text=self.text, font=self.font, fill="white")

butterfly_font_file="ButterFly.ttf"
flower_font_file="JandaFlowerDoodles.ttf"
status_font_file="LiberationMono-Bold.ttf"
font_file="Something Looks Natural Regular.otf"

sensor = SHT31(address = 0x44)

def make_font(name, size):
    font_path = os.path.abspath(os.path.join(
    #    os.path.dirname(__file__)
    '/usr/local/share/fonts/', name))
    return ImageFont.truetype(font_path, size)

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
        self.dw = device.width
        self.dh = device.height
        self.width = 0

    def append(self,msg):
        draw = ImageDraw.Draw(Image.new(self.device.mode, self.device.size))
        self.strings.append(msg)
        for j, c in enumerate(msg.text):
            char_width, char_height = draw.textsize(c, font=msg.font)
            char = MessageChar(c, msg.font, char_width, char_height)
            self.width += char.w

    def paint(self, msg_left):
        x = msg_left
        for string in self.strings:
            for j, c in enumerate(string.text):
                # Stop drawing if off the right side of screen.
                char_width, char_height = string.draw.textsize(c, font=string.font)
                if x > self.dw - char_width :
                    break
                # Calculate width but skip drawing if off the left side of screen.
                if x < char_width:
                    x += char_width
                    continue
                # Calculate offset from sine wave.
                # y = offset+math.floor(amplitude*math.sin(x/float(width)*2.0*math.pi))
                # Draw text.
                string.draw.text((x, self.dh - string.h), c, font=string.font, fill=100)
                # Increment x position based on chacacter width.
                x += char_width

    def width(self):
        w = 0
        for string in self.strings:
            w += string.w
        return w

class SHTresult:
    def __init__(self):
        self.degrees = 0.0
        self.humidity = 0.0

def execCmd(cmd_json):
    global message
    cmd = json.loads(cmd_json)
    if cmd["cmd"] == "message":
        message = cmd["value"]


def main(num_iterations=sys.maxsize):
    global message
    dh = device.height
    dw = device.width

    sht = SHTresult()
    running = 1

    fonts = {}
    fonts["flower_font"] = make_font(flower_font_file, 44)
    fonts["butterfly_font"] = make_font(butterfly_font_file, 44)
    fonts["status_font"] = make_font(status_font_file, 20)
    fonts["font"] = make_font(font_file, 44)

    def updateSHT31():
        sht.degrees = sensor.read_temperature() * 9/5 + 32
        sht.humidity = sensor.read_humidity()
        client.publish('GreenhouseTemp', sht.degrees)
        client.publish('GreenhouseHumidity', sht.humidity)
        print "Read temp of {} and humidity of {}".format(sht.degrees,sht.humidity)

    signal.signal(signal.SIGTERM, service_shutdown)
    signal.signal(signal.SIGINT, service_shutdown)

    try:
	SHT31Thread = Every(5, updateSHT31)

	client.connect()
	client.loop_background()
	client.on_connect    = connected
	client.on_disconnect = disconnected
	client.on_message    = message
        
        last_cmd = str(aio.receive('GreenhouseCmds').value)
        if last_cmd:
            print "Read previous GreenhouseCmd of {}".format(last_cmd)
            execCmd(last_cmd)
        else:
            execCmd(default_json_cmd)

	SHT31Thread.start()

	i = 0L
	while True:
	    with canvas(device) as draw:
		stat = Text('{0:0.1f}ºF, {1:0.1f}%'.format(sht.degrees, sht.humidity), draw, fonts["status_font"])

                msg = MessageString(device)
                for string in message:
                    msg.append(Text(string["msg"], draw, fonts[string["font"]]))

		if i % (dw + stat.w) == 0:
		    stat_left = 0 - stat.w
		else:
		    stat_left = 0 - stat.w + (i % (dw + stat.w))

		if i % (dw + msg.width) == 0:
		    msg_left = dw
		else:
		    msg_left = dw - (i % (dw + msg.width))

		stat.paint(stat_left, 0)
                msg.paint(msg_left)

		i += 2
    #except ServiceExit:
    finally:
        SHT31Thread.shutdown_flag.set()
        SHT31Thread.join()
        client.disconnect()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
