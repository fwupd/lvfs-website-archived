"""

Revision ID: efa7a171590b
Revises: b2ef90c2047a
Create Date: 2018-06-28 14:35:23.873091

"""

# revision identifiers, used by Alembic.
revision = 'efa7a171590b'
down_revision = 'b2ef90c2047a'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

import datetime
from app import db
from app.models import Event

def upgrade():
    op.add_column('users', sa.Column('atime', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('ctime', sa.DateTime(), nullable=False))
    op.add_column('users', sa.Column('mtime', sa.DateTime(), nullable=False))

    # migrate data
    user_mtimes = {}
    user_ctimes = {}
    for event in db.session.query(Event).order_by(Event.timestamp.desc()).all():
        if event.message == 'Logged in' or event.message == 'Logged in, and created account':
            if not event.user.atime:
                event.user.atime = event.timestamp
                print(('setting %s atime to %s' % (event.user.username, event.timestamp)))
        elif event.message == 'Updated profile':
            if event.user.username not in user_mtimes:
                event.user.mtime = event.timestamp
                print(('setting %s mtime to %s' % (event.user.username, event.timestamp)))
                user_mtimes[event.user.username] = 1
        user_ctimes[event.user] = event.timestamp
    for user in user_ctimes:
        print(('setting %s ctime to %s' % (user.username, user_ctimes[user])))
        user.ctime = user_ctimes[user]
    db.session.commit()

def downgrade():
    op.drop_column('users', 'mtime')
    op.drop_column('users', 'ctime')
    op.drop_column('users', 'atime')
