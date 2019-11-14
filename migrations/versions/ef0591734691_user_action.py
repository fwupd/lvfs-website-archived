"""

Revision ID: ef0591734691
Revises: 05217bb7d0c0
Create Date: 2019-11-14 08:44:46.977211

"""

# revision identifiers, used by Alembic.
revision = 'ef0591734691'
down_revision = '05217bb7d0c0'

from alembic import op
import sqlalchemy as sa

from lvfs import db
from lvfs.models import User, UserAction

def upgrade():
    op.create_table('user_actions',
    sa.Column('user_action_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('ctime', sa.DateTime(), nullable=False),
    sa.Column('value', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('user_action_id'),
    sa.UniqueConstraint('user_action_id'),
    mysql_character_set='utf8mb4'
    )

    for user in db.session.query(User):
        if user.unused_is_qa:
            user.actions.append(UserAction(value='qa'))
        if user.unused_is_robot:
            user.actions.append(UserAction(value='robot'))
        if user.unused_is_analyst:
            user.actions.append(UserAction(value='analyst'))
        if user.unused_is_vendor_manager:
            user.actions.append(UserAction(value='vendor-manager'))
        if user.unused_is_approved_public:
            user.actions.append(UserAction(value='approved-public'))
        if user.unused_is_admin:
            user.actions.append(UserAction(value='admin'))
        if user.unused_is_researcher:
            user.actions.append(UserAction(value='researcher'))
        if user.unused_notify_demote_failures:
            user.actions.append(UserAction(value='notify-demote-failures'))
        if user.unused_notify_server_error:
            user.actions.append(UserAction(value='notify-server-error'))
        if user.unused_notify_upload_vendor:
            user.actions.append(UserAction(value='notify-upload-vendor'))
        if user.unused_notify_upload_affiliate:
            user.actions.append(UserAction(value='notify-upload-affiliate'))
        if user.unused_notify_promote:
            user.actions.append(UserAction(value='notify-promote'))

    db.session.commit()

def downgrade():
    op.drop_table('user_actions')
