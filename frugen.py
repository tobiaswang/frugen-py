#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2019 - 2029 Byosoft Limited.

from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

import os
import sys
import getopt
import struct
import itertools
import json
from datetime import datetime

__version__ = '0.1.0'


def read_config(json_file):
    with open(json_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    if config.get('internal', {}).get('file'):
        internal_file = os.path.join(
            os.path.dirname(json_file), config['internal']['file']
        )
        try:
            with open(internal_file, 'rb') as f:
                config['internal']['data'] = f.read()
        except FileNotFoundError:
            message = 'Internal info area file {} not found.'
            raise ValueError(message.format(internal_file))
    if 'file' in config.get('internal', {}):
        del(config['internal']['file'])
    if 'internal' in config and not config['internal'].get('data'):
        del(config['internal'])
    return config


def gen_blob(data_type, data):
    out = bytes()

    if data_type == 'binary':
        value = bytes.fromhex(data)
        out += struct.pack('B%ds' % len(value), len(value) & 0x3F, value)
    elif data_type == 'bcd-plus':
        print("[INFO] type:%s, data:%s" % (data_type, data))
    elif data_type == '6bit-ascii':
        print("[INFO] type:%s, data:%s" % (data_type, data))
    elif data_type == 'ascii-latin1':
        value = data.encode('ascii')
        out += struct.pack('B%ds' % len(value),
                           len(value) | 0xC0, value)
    else:
        print('[ERROR] unsupported type: %s' % data_type)
    return out


def gen_internal(data):
    out = bytes()
    # internal use format version: current is 0x01
    # internal use data:
    data_bytes = bytes.fromhex(data['data'])
    out = struct.pack('B%ds' % len(data_bytes), 0x01, data_bytes)
    # add padding bytes
    while len(out) % 8 != 0:
        out += struct.pack('B', 0)
    return out


def gen_chassis(data):
    out = bytes()

    if 'type' in data:
        out += struct.pack('B', data.get('type', 0))

    fields = ['part-number', 'serial-number']
    for key in fields:
        if data.get(key):
            out += gen_blob('ascii-latin1', data[key])
        else:
            out += struct.pack('B', 0)

    if 'custom' in data:
        for c in data['custom']:
            out += gen_blob(c['type'], c['data'])

    # add 0xC1 to indicate no more info fields
    out += struct.pack('B', 0xC1)

    # padding space
    while len(out) % 8 != 5:
        out += struct.pack('B', 0)

    # chassis header
    out = struct.pack(
        'BB',
        0x01, # version
        (len(out) + 3) // 8, #length
    ) + out

    # add zero checksum
    out += struct.pack('B', (0 - sum(bytearray(out))) & 0xff)
    return out


def gen_board(data):
    out = bytes()

    out += struct.pack('B', data.get('language', 0))

    date_str = data.get('manufacturer-date', 0)
    t1 = datetime.strptime(date_str, '%Y/%m/%d %H:%M:%S')
    t2 = datetime.strptime('1996/1/1 0:0:0', '%Y/%m/%d %H:%M:%S')
    time_diff = (t1 - t2).days * 24 * 60 + (t1 - t2).seconds // 60
    out += struct.pack(
        'BBB',
        (time_diff & 0xFF),
        (time_diff & 0xFF00) >> 8,
        (time_diff & 0xFF0000) >> 16,
    )

    fields = ['manufacturer', 'product-name',
              'serial-number', 'part-number', 'file-id']

    for key in fields:
        if data.get(key):
            out += gen_blob('ascii-latin1', data[key])
        else:
            out += struct.pack('B', 0)

    if 'custom' in data:
        for c in data['custom']:
            out += gen_blob(c['type'], c['data'])

    out += struct.pack('B', 0xC1)

    while len(out) % 8 != 5:
        out += struct.pack('B', 0)

    out = struct.pack(
        'BB',
        0x01,
        (len(out)+3) // 8,
    ) + out

    # add zero checksum
    out += struct.pack('B', (0 - sum(bytearray(out))) & 0xff)
    return out


def gen_product(data):
    out = bytes()

    out += struct.pack('B', data.get('language', 0))

    fields = ['manufacturer', 'product-name', 'part-number',
              'product-version', 'serial-number', 'asset-tag', 'file-id']

    for key in fields:
        if data.get(key):
            out += gen_blob('ascii-latin1', data[key])
        else:
            out += struct.pack('B', 0)

    if 'custom' in data:
        for c in data['custom']:
            out += gen_blob(c['type'], c['data'])

    out += struct.pack('B', 0xC1)

    # add padding
    while len(out) % 8 != 5:
        out += struct.pack('B', 0)

    out = struct.pack(
        'BB',
        0x01,
        (len(out) + 3) // 8,
    ) + out

    # add zero checksum
    out += struct.pack('B', (0 - sum(bytearray(out))) & 0xff)
    return out


def gen_multirecord(data):
    out = bytes()
    for r in data:
        value = bytes.fromhex(r['data'])
        record_id = bytes.fromhex(r['record-id'])
        record_version = bytes.fromhex(r['record-version'])
        out += struct.pack('BBB', record_id[0], record_version[0], len(value))
        # record checksum
        out += struct.pack('B', (0 - sum(bytearray(value))) & 0xff)
        # record header checksum
        out += struct.pack('B', (0 - sum(bytearray(out))) & 0xff)
        out += value
    return out


def gen_fru_bin(data):
    internal = bytes()
    chassis = bytes()
    board = bytes()
    product = bytes()
    multirecord = bytes()

    internal_offset = 0
    chassis_offset = 0
    board_offset = 0
    product_offset = 0
    multirecord_offset = 0

    if 'internal' in data:
        internal = gen_internal(data['internal'])
    if 'chassis' in data:
        chassis = gen_chassis(data['chassis'])
    if 'board' in data:
        board = gen_board(data['board'])
    if 'product' in data:
        product = gen_product(data['product'])
    if 'multirecord' in data:
        multirecord = gen_multirecord(data['multirecord'])

    pos = 1
    if len(internal):
        internal_offset = pos
        pos += len(internal) // 8
    if len(chassis):
        chassis_offset = pos
        pos += len(chassis) // 8
    if len(board):
        board_offset = pos
        pos += len(board) // 8
    if len(product):
        product_offset = pos
        pos += len(product) // 8
    if len(multirecord):
        multirecord_offset = pos

    # generate fru header
    out = struct.pack(
        'BBBBBBB',
        0x01,
        internal_offset,
        chassis_offset,
        board_offset,
        product_offset,
        multirecord_offset,
        0x00
    )

    # add zero checksum
    out += struct.pack('B', (0 - sum(bytearray(out))) & 0xff)

    out += internal + chassis + board + product + multirecord
    return out


def run(json_file, bin_file):
    try:
        config = read_config(json_file)
        blob = gen_fru_bin(config)
    except ValueError as error:
        print(error.__context__)
    else:
        with open(bin_file, 'wb') as f:
            f.write(blob)


def usage():
    print("Usage: frugen.py [OPTIONS...]")
    print("OPTIONS:")
    print("\t-h --help\t\tThis help text")
    print("\t-v --version\t\tPrint version and exit")
    print("\t-c --config=FILE\tFRU config file in json format")
    print("\t-o --output=FILE\tOutput FRU data filename")


def version():
    print("frugen.py version %s" % __version__)
    print("Copyright 2019-2029 Byosoft.")


if __name__ == '__main__':
    config_file = ""
    output_file = ""

    if len(sys.argv) < 2:
        usage()

    try:
        options, args = getopt.getopt(sys.argv[1:], "hvc:o:", [
            "help", "version", "config=", "output="])
    except getopt.GetoptError:
        sys.exit()

    for name, value in options:
        if name in ("-h", "--help"):
            usage()
            sys.exit()
        if name in ("-v", "--version"):
            version()
            sys.exit()
        if name in ("-c", "--config"):
            config_file = value
        if name in ("-o", "--output"):
            output_file = value

    if config_file != "" and output_file != "":
        run(config_file, output_file)