# Copyright (C) 2019 Richard Hughes <richard@hughsie.com>
# SPDX-License-Identifier: GPL-2.0+

all: blocklist.cab chipsec.cab

clean:
	rm -rf ./tmp
	rm -rf ./htmlcov

blocklist.bin:
	echo "DO NOT SHIP" > $@

blocklist.dfu: blocklist.bin
	dfu-tool convert dfu $^ $@

blocklist.cab: blocklist.dfu blocklist.metainfo.xml
	gcab --create --nopath $@ $^

CFLAGS = -I/usr/include/efi \
	-I/usr/include/efi/x64/ \
	-I/usr/include/efi/protocol \
	-fno-stack-protector \
	-fpic \
	-fshort-wchar \
	-mno-red-zone \
	-Wall \
	-DEFI_FUNCTION_WRAPPER
LDFLAGS = -nostdlib \
	-znocombreloc \
	-T /usr/lib64/gnuefi/elf_x64_efi.lds \
	-shared -Bsymbolic \
	-L /usr/lib64/gnuefi \
	-L /usr/lib64 /usr/lib64/gnuefi/crt0-efi-x64.o

chipsec.so: chipsec.o
	ld $(LDFLAGS) chipsec.o -o $@ -lefi -lgnuefi

chipsec.exe: chipsec.so
	objcopy -j .text \
		-j .sdata \
		-j .data \
		-j .dynamic \
		-j .dynsym \
		-j .rel \
		-j .rela \
		-j .reloc \
		--strip-all \
		--target=efi-app-x86_64 $^ $@

cert.pem:
	openssl req -newkey rsa:2048 -nodes \
		-keyout secret.key \
		-x509 -days 365 -out $@

chipsec-signed.exe: chipsec.exe cert.pem
	osslsigncode sign \
		-certs cert.pem \
		-key secret.key \
		-pass password \
		-n "Test" \
		-i http://www.hughski.com/ \
		-in chipsec.exe -out $@

chipsec.fvh: chipsec-signed.exe
	./build-firmware.py $^ $@

chipsec.pfs: chipsec.fvh
	./build-firmware.py $^ $@

chipsec.zlib: chipsec.pfs
	openssl zlib -e < $^ > $@

chipsec.cap: chipsec.zlib
	./build-firmware.py $^ $@

chipsec.cab: chipsec.cap chipsec.metainfo.xml
	gcab --create --nopath $@ $^
