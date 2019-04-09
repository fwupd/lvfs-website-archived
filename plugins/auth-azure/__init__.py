#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2
#
# pylint: disable=no-self-use,no-member,unexpected-keyword-arg

import uuid

from flask import session, request
from flask_oauthlib.client import OAuthException

from app import oauth
from app.pluginloader import PluginBase, PluginSettingBool, PluginSettingText, PluginError
from app.util import _get_settings

settings = _get_settings('auth_azure')
if 'auth_azure_consumer_key' in settings and settings['auth_azure_consumer_key']:
    remote_app = oauth.remote_app(
        'microsoft',
        consumer_key=settings['auth_azure_consumer_key'],
        consumer_secret=settings['auth_azure_consumer_secret'],
        request_token_params={'scope': 'offline_access User.Read'},
        base_url='https://graph.microsoft.com/v1.0/',
        request_token_url=None,
        access_token_method='POST',
        access_token_url='https://login.microsoftonline.com/common/oauth2/v2.0/token',
        authorize_url='https://login.microsoftonline.com/common/oauth2/v2.0/authorize'
    )

    @remote_app.tokengetter
    def get_auth_azure_token():
        return session.get('auth_azure_token')

class Plugin(PluginBase):
    def __init__(self):
        PluginBase.__init__(self)

    def name(self):
        return 'Azure'

    def summary(self):
        return 'Authenticate against Microsoft Azure Active Directory.'

    def settings(self):
        s = []
        s.append(PluginSettingBool('auth_azure_enable', 'Enabled', False))
        s.append(PluginSettingText('auth_azure_consumer_key', 'Consumer Key', ''))
        s.append(PluginSettingText('auth_azure_consumer_secret', 'Consumer Secret', ''))
        return s

    def oauth_authorize(self, callback):

        # generate the guid to only accept initiated logins
        guid = uuid.uuid4()
        session['auth_azure_state'] = guid
        return remote_app.authorize(callback=callback, state=guid)

    def oauth_get_data(self):

        # get response success
        try:
            oauth_response = remote_app.authorized_response()
        except OAuthException as e:
            raise PluginError(str(e))
        if oauth_response is None:
            raise PluginError('Access Denied' + str(request))

        # check response for correct GUID
        if str(session['auth_azure_state']) != str(request.args['state']):
            raise PluginError('State has been messed with, end authentication')

        # save the access token -- treat as a password
        session['auth_azure_token'] = (oauth_response['access_token'], '')

        # get the profile ID
        resp = remote_app.get('me')
        if not resp:
            raise PluginError('No suitable profile response')
        if not resp.data:
            raise PluginError('No suitable profile data')
        return resp.data

    def oauth_logout(self):
        session.pop('auth_azure_token', None)
        session.pop('auth_azure_state', None)
