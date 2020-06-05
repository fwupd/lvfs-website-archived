#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2019-2020 Richard Hughes <richard@hughsie.com>
#
# SPDX-License-Identifier: GPL-2.0+
#
# pylint: disable=singleton-comparison

from lvfs import db

from lvfs.dbutils import _execute_count_star
from lvfs.models import Metric, Client, Firmware, Remote, Test, Report
from lvfs.models import Protocol, ComponentShardInfo, ComponentShard, Component
from lvfs.models import Vendor, User

def _regenerate_metrics():
    values = {}
    values['ClientCnt'] = _execute_count_star(\
                                db.session.query(Client))
    values['FirmwareCnt'] = _execute_count_star(\
                                db.session.query(Firmware))
    values['FirmwareStableCnt'] = _execute_count_star(\
                                db.session.query(Firmware)\
                                          .join(Remote)\
                                          .filter(Remote.name == 'stable'))
    values['FirmwareTestingCnt'] = _execute_count_star(\
                                db.session.query(Firmware)\
                                          .join(Remote)\
                                          .filter(Remote.name == 'testing'))
    values['FirmwarePrivateCnt'] = _execute_count_star(\
                                db.session.query(Firmware)\
                                          .join(Remote)\
                                          .filter(Remote.is_public == False))
    values['TestCnt'] = _execute_count_star(\
                                db.session.query(Test))
    values['ReportCnt'] = _execute_count_star(\
                                db.session.query(Report))
    values['ProtocolCnt'] = _execute_count_star(\
                                db.session.query(Protocol))
    values['ComponentShardInfoCnt'] = _execute_count_star(\
                                db.session.query(ComponentShardInfo))
    values['ComponentShardCnt'] = _execute_count_star(\
                                db.session.query(ComponentShard))
    values['ComponentCnt'] = _execute_count_star(\
                                db.session.query(Component))
    values['VendorCnt'] = _execute_count_star(\
                                db.session.query(Vendor)\
                                          .filter(Vendor.visible)\
                                          .filter(Vendor.username_glob != None))
    values['UserCnt'] = _execute_count_star(\
                                db.session.query(User)\
                                         .filter(User.auth_type != 'disabled'))

    #  save to database
    for key in values:
        metric = db.session.query(Metric).filter(Metric.key == key).first()
        if not metric:
            metric = Metric(key=key)
            db.session.add(metric)
        metric.value = values[key]
        print('{}={}'.format(metric.key, metric.value))
    db.session.commit()
