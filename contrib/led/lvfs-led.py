#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+

import sys
import json
import time

import requests
import serial

LED_REFRESH_DELAY = 100 # ms
LVFS_REFRESH_DELAY = 5000 # ms

def _led_update(dev):

    # no log in required
    session = requests.Session()
    try:
        ser = serial.Serial(dev, 38400)
        ser.write_timeout = 5
    except serial.serialutil.SerialException as e:
        print('failed to write: {}'.format(e))
        return 2

    idx = 0
    cnt_last = 0
    cnt_new = 0
    while True:

        # hit the public endpoint
        if idx == 0:
            try:
                rv = session.get('https://www.fwupd.org/lvfs/metrics', timeout=5)
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.ReadTimeout) as e:
                print(str(e))
                cnt_new = 0
                display = 'Conn Err\n'
            else:
                if rv.status_code != 200:
                    cnt_new = 0
                    display = 'StAtuS {}\n'.format(rv.status_code)
                else:
                    # parse JSON data
                    try:
                        item = json.loads(rv.content.decode())
                    except ValueError as e:
                        print('No JSON object could be decoded: {}'.format(str(e)))
                        cnt_new = 0
                        display = 'JSOn bAd\n'
                    else:
                        cnt_last = cnt_new
                        cnt_new = int(item['ClientCnt'])

        # linearly interpolate between the old and new values
        if cnt_new and cnt_last:
            cnt_diff = cnt_new - cnt_last
            pc = (LED_REFRESH_DELAY / LVFS_REFRESH_DELAY) * idx
            display = 'dL{: >10}\n'.format(int(cnt_last + (cnt_diff * pc)))

        # we only have the initial value
        elif cnt_new:
            display = 'dL{: >10}\n'.format(cnt_new)

        # send to serial port
        try:
            ser.write(display.encode())
        except serial.serialutil.SerialException as e:
            print('failed to write: {}'.format(e))
            return 1

        # wait a bit
        time.sleep(LED_REFRESH_DELAY / 1000)

        # increment the counter, resetting if it gets high enough
        idx += 1
        if idx == LVFS_REFRESH_DELAY / LED_REFRESH_DELAY:
            idx = 0

if __name__ == '__main__':
    try:
        _dev = '/dev/{}'.format(sys.argv[1])
    except IndexError as _:
        _dev = '/dev/ttyUSB0'
    _led_update(_dev)
