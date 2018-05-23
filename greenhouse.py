#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2014-18 Richard Hull and contributors
# See LICENSE.rst for details.
# PYTHON_ARGCOMPLETE_OK

from __future__ import unicode_literals

import os
import sys
import random
import threading, signal
import time, traceback

from PIL import ImageFont

from Adafruit_SHT31 import *
from Adafruit_IO import *

from luma.core.render import canvas
from luma.core.interface.serial import spi
from luma.oled.device import ssd1306

flowers1_string = "C"
flowers2_string = "A"
flowers2_string = "z"
text_string = "I love you, mom!"

client = MQTTClient('kmksea','cd202c9bdc424c498eb586e81a2eeafb')

def connected(client):
    print('Connected to Adafruit IO!  Listening for Greenhouse Commands...')
    client.subscribe('GreenhouseCmds')
def disconnected(client):
    # Disconnected function will be called when the client disconnects.
    print('Disconnected from Adafruit IO!')
    sys.exit(1)
def message(client, feed_id, payload, retain):
    global text_string
    print('Feed {0} received new value: {1}'.format(feed_id, payload))
    if feed_id == 'GreenhouseCmds':
        text_string=payload

class Every(threading.Thread):
    def __init__(self, delay, task):
        threading.Thread.__init__(self)
        self.shutdown_flag = threading.Event()

        self.delay = delay
        self.task = task

    def run(self):
      next_time = time.time() + self.delay
      while not self.shutdown_flag.is_set():
        time.sleep(max(0, next_time - time.time()))
        try:
          self.task()
        except Exception:
          traceback.print_exc()
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

flower_font = make_font(flower_font_file, 44)
butterfly_font = make_font(butterfly_font_file, 44)
status_font = make_font(status_font_file, 20)
font = make_font(font_file, 44)



def main(num_iterations=sys.maxsize):
    device = ssd1306(spi(device=0, port=0, gpio_DC=23, gpio_RST=24))
    dh = device.height
    dw = device.width

    degrees = 0.0
    humidity = 0.0
    running = 1

    def updateSHT31():
        degrees = sensor.read_temperature() * 9/5 + 32
        humidity = sensor.read_humidity()
        client.publish('GreenhouseTemp', degrees)
        client.publish('GreenhouseHumidity', humidity)
        print "Read temp of {} and humidity of {}".format(degrees,humidity)

    signal.signal(signal.SIGTERM, service_shutdown)
    signal.signal(signal.SIGINT, service_shutdown)

    try:
	SHT31Thread = Every(1, updateSHT31)

	client.connect()
	client.loop_background()
	client.on_connect    = connected
	client.on_disconnect = disconnected
	client.on_message    = message

	SHT31Thread.start()

	i = 0L
	while True:
	    with canvas(device) as draw:
		#stat = Text('{0} {1:0.1f}ºF, {2:0.1f}%'.format(time.strftime('%b %d, %Y %H:%M:%S'), (degrees*9/5+32), humidity), draw, status_font)
		stat = Text('{0:0.1f}ºF, {1:0.1f}%'.format(degrees, humidity), draw, status_font)
		flowers1 = Text(flowers1_string, draw, butterfly_font)
		flowers2 = Text(flowers2_string, draw, flower_font)
		text = Text(text_string, draw, font)


		if i % (dw + stat.w) == 0:
		    stat_left = 0 - stat.w
		else:
		    stat_left = 0 - stat.w + (i % (dw + stat.w))
		    #stat_left = dw - (i%(stat.w+dw))

		if i % (dw + flowers1.w + flowers2.w + text.w) == 0:
		    msg_left = dw
		else:
		    msg_left = dw - (i % (dw + flowers1.w + flowers2.w + text.w))

		stat.paint(stat_left, 0)
		flowers1.paint(msg_left, dh - flowers1.h)

		#text.paint(msg_left + flowers1.w, dh - text.h)

		x = msg_left + flowers1.w
		for j, c in enumerate(text.text):
		    # Stop drawing if off the right side of screen.
		    char_width, char_height = draw.textsize(c, font=text.font)
		    if x > dw :
			break
		    # Calculate width but skip drawing if off the left side of screen.
		    if x < -char_width:
			x += char_width
			continue
		    # Calculate offset from sine wave.
		    # y = offset+math.floor(amplitude*math.sin(x/float(width)*2.0*math.pi))
		    # Draw text.
		    draw.text((x, dh - text.h), c, font=font, fill=255)
		    # Increment x position based on chacacter width.
		    x += char_width

		flowers2.paint(msg_left + flowers1.w + text.w, dh - text.h)
		i += 2
    except ServiceExit:
        SHT31Thread.shutdown_flag.set()
        SHT31Thread.join()
        client.disconnect()



if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
