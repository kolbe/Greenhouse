#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2014-18 Richard Hull and contributors
# See LICENSE.rst for details.
# PYTHON_ARGCOMPLETE_OK

from __future__ import unicode_literals

import os
import sys
import random
from PIL import ImageFont

from Adafruit_SHT31 import *

from luma.core.render import canvas
#from luma.core.sprite_system import framerate_regulator
from luma.core.interface.serial import spi
from luma.oled.device import ssd1306

class Text:
    def __init__(self, text, draw, font):
        self.draw = draw
        self.text = text
        self.font = font
        self.w, self.h = draw.textsize(text=text, font=font)
    def paint(self, x, y):
        self.draw.text((x,y), text=self.text, font=self.font, fill="white")


#font_file="fontawesome-webfont.ttf"
#font_file="Gardening With Sue.ttf"
font_file="CFPlantsandFlowers-Regular.ttf"
font_file="PlantType.ttf"
font_file="Something Looks Natural Regular.otf"

butterfly_font_file="ButterFly.ttf"
flower_font_file="JandaFlowerDoodles.ttf"
status_font_file="LiberationMono-Bold.ttf"

codes = [
        'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P'
        ]


sensor = SHT31(address = 0x44)

def make_font(name, size):
    font_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'fonts', name))
    return ImageFont.truetype(font_path, size)


def infinite_shuffle(arr):
    copy = list(arr)
    while True:
        random.shuffle(copy)
        for elem in copy:
            yield elem


def main(num_iterations=sys.maxsize):
    device = ssd1306(spi(device=0, port=0, gpio_DC=23, gpio_RST=24))
    dh = device.height
    dw = device.width
    #regulator = framerate_regulator(fps=0)
    flower_font = make_font(flower_font_file, 44)
    butterfly_font = make_font(butterfly_font_file, 44)
    font = make_font(font_file, 44)
    status_font = make_font(status_font_file, 20)

    flowers1_string = "z"
    flowers2_string = "A"
    flowers2_string = "C"
    text_string = "I love you, mom!"
    i = 0L
    while True:
        with canvas(device) as draw:
                degrees = sensor.read_temperature()
                humidity = sensor.read_humidity()
    #    with regulator:
                #stat = Text('{0} {1:0.1f}ºF, {2:0.1f}%'.format(time.strftime('%b %d, %Y %H:%M:%S'), (degrees*9/5+32), humidity), draw, status_font)
                stat = Text('{0:0.1f}ºF, {1:0.1f}%'.format((degrees*9/5+32), humidity), draw, status_font)
                flowers1 = Text(flowers1_string, draw, flower_font)
                flowers2 = Text(flowers2_string, draw, butterfly_font)
                text = Text(text_string, draw, font)
                if i % (dw+stat.w) == 0:
                    stat_left = dw
                else:
                    stat_left = dw - (i%(stat.w+dw))

                if i % (dw + flowers1.w + flowers2.w + text.w) == 0:
                    msg_left = 0 - flowers1.w - flowers2.w - text.w
                else:
                    msg_left = -flowers1.w - flowers2.w - text.w + (i%(text.w + flowers1.w + flowers2.w + dw))
                    
                stat.paint(stat_left, 0)
                flowers1.paint(msg_left, dh - flowers1.h)
                text.paint(msg_left + flowers1.w, dh - text.h)
                flowers2.paint(msg_left + flowers1.w + text.w, dh - text.h)
                i = i+1


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
