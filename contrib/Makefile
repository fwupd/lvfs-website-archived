# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# SPDX-License-Identifier: GPL-2.0+

all: blocklist.cab

clean:
	rm -rf ./tmp
	rm -rf ./htmlcov

blocklist.bin:
	echo "DO NOT SHIP" > $@

blocklist.dfu: blocklist.bin
	dfu-tool convert dfu $^ $@

blocklist.cab: blocklist.dfu blocklist.metainfo.xml
	gcab --create --nopath $@ $^
