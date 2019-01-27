"""

Revision ID: f49b79b3ffdd
Revises: 5ebf95d88441
Create Date: 2018-03-19 12:36:41.396478

"""

# revision identifiers, used by Alembic.
revision = 'f49b79b3ffdd'
down_revision = '5ebf95d88441'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app import db
from app.models import Remote, Vendor

class FirmwareEventOld(db.Model):
    __tablename__ = 'firmware_events'
    __table_args__ = {'extend_existing': True}
    target = db.Column(db.Text, nullable=False)

class FirmwareOld(db.Model):
    __tablename__ = 'firmware'
    __table_args__ = {'extend_existing': True}
    target = db.Column(db.Text, nullable=False)

def upgrade():
    op.create_table('remotes',
    sa.Column('remote_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('is_public', sa.Boolean(), nullable=True),
    sa.PrimaryKeyConstraint('remote_id'),
    sa.UniqueConstraint('remote_id')
    )
    op.add_column('firmware', sa.Column('remote_id', sa.Integer(), nullable=False))
    op.add_column('firmware_events', sa.Column('remote_id', sa.Integer(), nullable=False))
    op.add_column('vendors', sa.Column('remote_id', sa.Integer(), nullable=False))

    # create first three remotes that have to exist
    db.session.add(Remote(name='stable', is_public=True))
    db.session.add(Remote(name='testing', is_public=True))
    db.session.add(Remote(name='private'))
    db.session.commit()

    # create any of the vendor remotes that should exist
    for v in db.session.query(Vendor).all():
        r = Remote(name='embargo-%s' % v.group_id)
        db.session.add(r)
        db.session.commit()
        v.remote_id = r.remote_id

    # reassign target->remote_id
    remotes = {}
    for r in db.session.query(Remote).all():
        remotes[r.name] = r
    vendors = {}
    for v in db.session.query(Vendor).all():
        vendors[v.vendor_id] = v
    fws = {}
    for fw in db.session.query(FirmwareOld).all():
        remote_name = fw.target
        if remote_name == 'embargo':
            remote_name = 'embargo-%s' % vendors[fw.vendor_id].group_id
        fw.remote_id = remotes[remote_name].remote_id
        fws[fw.firmware_id] = fw
    for event in db.session.query(FirmwareEventOld).all():
        remote_name = event.target
        if remote_name == 'embargo':
            fw = fws[event.firmware_id]
            remote_name = 'embargo-%s' % vendors[fw.vendor_id].group_id
        event.remote_id = remotes[remote_name].remote_id
    db.session.commit()

    # all valid now
    op.create_foreign_key(None, 'firmware', 'remotes', ['remote_id'], ['remote_id'])
    op.create_foreign_key(None, 'firmware_events', 'remotes', ['remote_id'], ['remote_id'])
    op.create_foreign_key(None, 'vendors', 'remotes', ['remote_id'], ['remote_id'])

    # no longer required
    op.drop_column('firmware', 'target')
    op.drop_column('firmware_events', 'target')

def downgrade():
    op.drop_constraint(None, 'vendors', type_='foreignkey')
    op.drop_column('vendors', 'remote_id')
    op.add_column('firmware_events', sa.Column('target', mysql.TEXT(), nullable=False))
    op.drop_constraint(None, 'firmware_events', type_='foreignkey')
    op.drop_column('firmware_events', 'remote_id')
    op.add_column('firmware', sa.Column('target', mysql.VARCHAR(length=255), nullable=False))
    op.drop_constraint(None, 'firmware', type_='foreignkey')
    op.drop_column('firmware', 'remote_id')
    op.drop_table('remotes')
