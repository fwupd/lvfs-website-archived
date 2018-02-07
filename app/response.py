#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from flask import Response
from werkzeug.datastructures import Headers

class SecureResponse(Response):
    def __init__(self, response, **kwargs):

        # ensure headers always exist
        if kwargs['headers'] is None:
            kwargs['headers'] = Headers()
        headers = kwargs['headers']

        # Prevent browsers from incorrectly detecting non-scripts as scripts
        # https://wiki.mozilla.org/Security/Guidelines/Web_Security#X-Content-Type-Options
        headers.add('X-Content-Type-Options', 'nosniff')

        # Prevents external sites from embedding this site in an iframe
        # https://wiki.mozilla.org/Security/Guidelines/Web_Security#X-Frame-Options
        headers.add('X-Frame-Options', 'DENY')

        # Block pages from loading when they detect reflected XSS attacks
        # https://wiki.mozilla.org/Security/Guidelines/Web_Security#X-XSS-Protection
        headers.add('X-XSS-Protection', '1', mode='block')

        # Never send the Referer header to preserve the users privacy
        # https://wiki.mozilla.org/Security/Guidelines/Web_Security#Referrer_Policy
        headers.add('Referrer-Policy', 'no-referrer')

        # Block site from being framed with X-Frame-Options
        # https://wiki.mozilla.org/Security/Guidelines/Web_Security#X-Frame-Options
        headers.add('X-Frame-Options', 'DENY')

        # Only connect to this site via HTTPS
        # https://wiki.mozilla.org/Security/Guidelines/Web_Security#HTTP_Strict_Transport_Security
        args = {}
        args['max-age'] = 63072000
        args['includeSubDomains'] = None
        args['preload'] = None
        headers.add('Strict-Transport-Security', None, **args)

        # Block pages from loading when they detect reflected XSS attacks
        # https://wiki.mozilla.org/Security/Guidelines/Web_Security#Content_Security_Policy
        args = {}
        args["default-src 'none'"] = None
        args["img-src 'self'"] = None
        args["script-src 'self' 'unsafe-inline' 'unsafe-eval' " +
             "https://maxcdn.bootstrapcdn.com https://code.jquery.com https://cdnjs.cloudflare.com"] = None
        args["style-src 'self' https://maxcdn.bootstrapcdn.com"] = None
        args["frame-ancestors 'none'"] = None
        headers.add('Content-Security-Policy', None, **args)

        super(SecureResponse, self).__init__(response, **kwargs)
