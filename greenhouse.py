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
from luma.core.virtual import viewport
from luma.core.interface.serial import spi
from luma.oled.device import ssd1306

flowers1_string = "C"
flowers2_string = "A"
flowers2_string = "z"
text_string = "I love you, mom!"


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

def main(num_iterations=sys.maxsize):
    device = ssd1306(spi(device=0, port=0, gpio_DC=23, gpio_RST=24))
    dh = device.height
    dw = device.width

    class Text:
        def __init__(self, text, font):
            self.text = text
            self.font = font
            with canvas(device) as draw:
                self.w, self.h = draw.textsize(text=text, font=font)
        def paint(self):
            return {'text':self.text, 'font':self.font, 'fill':"white"}

    flower_font = make_font(flower_font_file, 44)
    butterfly_font = make_font(butterfly_font_file, 44)
    status_font = make_font(status_font_file, 20)
    font = make_font(font_file, 30)


    degrees = sensor.read_temperature()
    humidity = sensor.read_humidity()
    #stat = Text('{0:0.1f}ºF, {1:0.1f}%'.format((degrees*9/5+32), humidity), status_font)
    stat = Text('{0} {1:0.1f}ºF, {2:0.1f}%'.format(time.strftime('%H:%M:%S'), (degrees*9/5+32), humidity), status_font)
    flowers1 = Text(flowers1_string, butterfly_font)
    flowers2 = Text(flowers2_string, flower_font)
    text = Text(text_string, font)
    mw = flowers1.w + text.w + flowers2.w #+ dw

    i = 0L
    virtual = viewport(device, width=mw+dw*2, height=dh)
    while True:
        stat.text = '{0} {1:0.1f}ºF, {2:0.1f}%'.format(time.strftime('%H:%M:%S'), (degrees*9/5+32), humidity)
        with canvas(virtual) as draw:

            if i % (dw + stat.w) == 0:
                stat_left = 0 - stat.w
            else:
                stat_left = 0 - stat.w + (i % (dw + stat.w))
                #stat_left = dw - (i%(stat.w+dw))
            stat_left=0
            """

            if i % (dw + flowers1.w + flowers2.w + text.w) == 0:
                msg_left = dw
            else:
                msg_left = dw - (i % (dw + flowers1.w + flowers2.w + text.w))
                """
            msg_left=dw

            #draw.text((stat_left, 0), **stat.paint())
            draw.text((msg_left, dh - flowers1.h), **flowers1.paint() )
            draw.text((msg_left + flowers1.w, dh - text.h), **text.paint() )

            """
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

"""
            draw.text((msg_left + flowers1.w + text.w, dh - text.h), **flowers2.paint())
        virtual.set_position((i % (mw + dw), 0))
        i += 2


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
