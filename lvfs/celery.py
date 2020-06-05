#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=too-few-public-methods,unused-argument

from celery import Celery
from celery.signals import task_postrun

from flask import g, has_app_context

class FlaskCelery(Celery):

    def __init__(self, *args, **kwargs):

        super(FlaskCelery, self).__init__(*args, **kwargs)
        self.patch_task()

        if 'app' in kwargs:
            self.init_app(kwargs['app'])

    def patch_task(self):
        TaskBase = self.Task
        _celery = self

        class ContextTask(TaskBase):
            abstract = True

            def __call__(self, *args, **kwargs):
                if has_app_context():
                    return TaskBase.__call__(self, *args, **kwargs)
                with _celery.app.app_context():
                    _celery.app.config['SERVER_NAME'] = _celery.app.config['HOST_NAME']
                    from lvfs import db
                    from lvfs.models import User
                    g.user = db.session.query(User).filter(User.username == 'anon@fwupd.org').first()
                    return TaskBase.__call__(self, *args, **kwargs)

        self.Task = ContextTask

    def init_app(self, app):
        self.app = app
        self.config_from_object(app.config)

@task_postrun.connect
def close_session(*args, **kwargs):
    from lvfs import db
    db.session.remove()
