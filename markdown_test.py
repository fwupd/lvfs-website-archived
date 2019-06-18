#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=no-self-use,protected-access

import unittest
from lxml import etree as ET
from app.util import _markdown_from_root, _xml_from_markdown, _get_update_description_problems

class MarkdownTest(unittest.TestCase):

    def test_appstream_convert(self):

        markup = """
<p>CHANGES IN THIS RELEASE</p>
<p>Version 11.8.55.3510</p>
<p>[Important updates]</p>
<p></p>
<ul>
<li>Nothing.</li>
<li></li>
</ul>
<p>[New functions &amp; enhancements]</p>
<ul>
<li>Nothing.</li>
<li>Nothing more.</li>
</ul>
<p>[Problem fixes]</p>
<ul>
<li>Nothing.</li>
</ul>
"""
        markdown = _markdown_from_root(ET.fromstring('<xxx>' + markup + '</xxx>'))
        print('`'+markdown+'`')

        # convert from markdown back to XML
        root = _xml_from_markdown(markdown)
        xml = ET.tostring(root, pretty_print=True)
        print('`'+xml.decode()+'`')

        # show problems
        for problem in _get_update_description_problems(root):
            print(' * %s' % problem.description)

if __name__ == '__main__':
    unittest.main()
