#!/usr/bin/python
# Copyright (C) 2015 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 2

from lvfs_client import LvfsClient

#SERVER = 'https://testing-lvfs.rhcloud.com'
SERVER = 'http://localhost:5000'

FILE = './contrib/hughski-colorhug2-2.0.3.cab'

def main():

    w = LvfsClient(SERVER)
    w.add_user('user', 'test', 'Pa$$w0rd')

    # set up tests to ensure the file is really gone
    w.action_fwdelete('3d69d6c68c915d7cbb4faa029230c92933263f42', auth='admin')
    w.action_userdel('test', auth='admin')

    # no auth
    r = w.action_useradd('test', 'test', 'test', 'Test User', 'test@user.com', auth='none')
    assert r.status_code == 401, "expected error when adding user : %s" % r.text

    # only admin auth
    r = w.action_useradd('test', 'test', 'test', 'Test User', 'test@user.com', auth='user')
    assert r.status_code == 401, "expected error when adding user"

    # admin, bad password
    r = w.action_useradd('test', 'test', 'test', 'Test User', 'test@user.com', auth='admin')
    assert r.status_code == 400, "expected error when adding bad password : %s" % r.status_code

    # admin, good password, bad email
    r = w.action_useradd('test', 'Pa$$w0rd', 'test', 'Test User', 'invalid', auth='admin')
    assert r.status_code == 400, "expected error when adding bad email : %s" % r.status_code

    # admin, good password, good email, bad qa_group
    r = w.action_useradd('test', 'Pa$$w0rd', '', 'Test User', 'test@user.com', auth='admin')
    assert r.status_code == 401, "expected error when adding bad qa_group : %s" % r.status_code

    # admin, good password, good email
    r = w.action_useradd('test', 'Pa$$w0rd', 'test', 'Test User', 'test@user.com', auth='admin')
    assert r.status_code == 201, "failed to add user : %s" % r.text

    # get an error when deleting an unknown id
    r = w.action_fwdelete('deadbeef')
    assert r.status_code == 400, "expected error when deleting random id : %s" % r.status_code

    # upload new fw to stable as a non QA user
    r = w.action_upload(FILE, 'stable')
    assert r.status_code == 401, "expected error when !QA upload file to stable"

    # upload new fw to stable as a non QA user
    r = w.action_upload(FILE, 'testing')
    assert r.status_code == 401, "expected error when !QA upload file to testing"

    # upload random fw
    r = w.action_upload('./contrib/check.py', 'private')
    assert r.status_code == 415, "expected error when uploading random file : %s" % r.status_code

    # upload new fw to non embargo without credentials
    r = w.action_upload(FILE, 'stable')
    assert r.status_code == 401, "expected error when uploading to stable"
    r = w.action_upload(FILE, 'testing')
    assert r.status_code == 401, "expected error when uploading to testing"

    # upload new fw
    r = w.action_upload(FILE, 'embargoed')
    assert r.status_code == 201, "failed to upload file: %i" % r.status_code

    # upload existing fw again
    r = w.action_upload(FILE, 'embargoed')
    assert r.status_code == 422, "expected error when reuploading file : %s" % r.status_code

    # delete the test file without login
    r = w.action_fwdelete('3d69d6c68c915d7cbb4faa029230c92933263f42', auth='none')
    assert r.status_code == 401, "expected error when deleting file without login"

    # make the user part of QA
    r = w.action_userinc('test', 'qa', auth='none')
    assert r.status_code == 401, "expected error when inc user"
    r = w.action_userinc('test', 'qa', auth='user')
    assert r.status_code == 401, "expected error when inc user"
    r = w.action_userinc('test', 'qa', auth='admin')
    assert r.status_code == 200, "cannot inc user : %s" % r.status_code
    r = w.action_userinc('test', 'dave', auth='admin')
    assert r.status_code == 401, "expected error when inc user"

    # delete the test file
    r = w.action_fwdelete('3d69d6c68c915d7cbb4faa029230c92933263f42')
    assert r.status_code == 200, "failed to delete file"

    # regenerate metadata as non-admin user
    r = w.action_metadata_rebuild(auth='user')
    assert r.status_code == 401, "expected error when rebuild as user"

    # regenerate metadata as admin user
    r = w.action_metadata_rebuild(auth='admin')
    assert r.status_code == 200, "failed to rebuild metadata"

    # delete the test user
    r = w.action_userdel('test', auth='admin')
    assert r.status_code == 200, "failed to delete test user"

if __name__ == "__main__":
    main()
