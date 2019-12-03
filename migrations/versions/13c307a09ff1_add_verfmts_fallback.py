"""

Revision ID: 13c307a09ff1
Revises: 946c9e47ceaa
Create Date: 2019-12-03 19:57:33.060314

"""

# revision identifiers, used by Alembic.
revision = '13c307a09ff1'
down_revision = 'ae8f6b33ba7d'

from alembic import op
import sqlalchemy as sa

from lvfs import db
from lvfs.models import Component, Verfmt

def upgrade():
    op.add_column('verfmts', sa.Column('fallbacks', sa.Text(), nullable=True))
    verfmt = db.session.query(Verfmt).filter(Verfmt.value == 'dell-bios').one()
    for md in db.session.query(Component):
        if md.fw.vendor.group_id != 'dell':
            continue
        if md.verfmt and md.verfmt.value != 'quad':
            continue
        if md.protocol and md.protocol.value != 'org.uefi.capsule':
            continue
        print('fixing', md.component_id, md.names)
        md.verfmt= verfmt
    db.session.commit()

def downgrade():
    verfmt = db.session.query(Verfmt).filter(Verfmt.value == 'quad').one()
    for md in db.session.query(Component):
        if md.fw.vendor.group_id != 'dell':
            continue
        if md.verfmt and md.verfmt.value != 'dell-bios':
            continue
        if md.protocol and md.protocol.value != 'org.uefi.capsule':
            continue
        print('fixing', md.component_id, md.names)
        md.verfmt= verfmt
    db.session.commit()
    op.drop_column('verfmts', 'fallbacks')
