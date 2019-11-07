"""

Revision ID: 05217bb7d0c0
Revises: ecd1aef76799
Create Date: 2019-11-07 15:32:48.781990

"""

# revision identifiers, used by Alembic.
revision = '05217bb7d0c0'
down_revision = 'ecd1aef76799'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from lvfs import db
from lvfs.models import Verfmt, Component, Vendor

def upgrade():
    if 1:
        op.create_table('verfmts',
        sa.Column('verfmt_id', sa.Integer(), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('example', sa.Text(), nullable=True),
        sa.Column('fwupd_version', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('verfmt_id'),
        sa.UniqueConstraint('verfmt_id'),
        mysql_character_set='utf8mb4'
        )
        op.add_column('components', sa.Column('verfmt_id', sa.Integer(), nullable=True))
        op.create_foreign_key('components_ibfk_4', 'components', 'verfmts', ['verfmt_id'], ['verfmt_id'])
        op.add_column('vendors', sa.Column('verfmt_id', sa.Integer(), nullable=True))
        op.create_foreign_key('vendors_ibfk_2', 'vendors', 'verfmts', ['verfmt_id'], ['verfmt_id'])
        op.add_column('protocol', sa.Column('verfmt_id', sa.Integer(), nullable=True))
        op.create_foreign_key('protocol_ibfk_1', 'protocol', 'verfmts', ['verfmt_id'], ['verfmt_id'])

        # create the ones we support already
        verfmts = [
            Verfmt(value='plain',
                   fwupd_version='1.2.0',
                   example='12345678',
                   name='Plain integer'),
            Verfmt(value='pair',
                   fwupd_version='1.2.0',
                   example='1234.5678',
                   name='Pair of large numbers'),
            Verfmt(value='triplet',
                   fwupd_version='1.1.0',
                   example='12.34.5678',
                   name='Microsoft-style'),
            Verfmt(value='quad',
                   fwupd_version='1.1.0',
                   example='12.34.56.78',
                   name='Dell-style'),
            Verfmt(value='intel-me',
                   fwupd_version='1.2.0',
                   example='12.2.34.5678',
                   name='Intel ME, with bitshift'),
            Verfmt(value='intel-me2',
                   fwupd_version='1.2.0',
                   example='1.2.34.5678',
                   name='Intel ME'),
            Verfmt(value='bcd',
                   fwupd_version='1.2.9',
                   example='12.34',
                   name='Binary Coded Decimal'),
            Verfmt(value='surface-legacy',
                   fwupd_version='1.3.4',
                   example='12.34.56',
                   name='Microsoft Surface (legacy)'),
            Verfmt(value='surface',
                   fwupd_version='1.3.4',
                   example='12.34.56',
                   name='Microsoft Surface'),
        ]
        for verfmt in verfmts:
            db.session.add(verfmt)
        db.session.commit()

    # convert existing version formats for vendors and components
    lookup = {}
    for verfmt in db.session.query(Verfmt):
        lookup[verfmt.value] = verfmt
    for md in db.session.query(Component):
        if md.unused_version_format:
            md.verfmt = lookup[md.unused_version_format]
    for vendor in db.session.query(Vendor):
        if vendor.unused_version_format:
            vendor.verfmt = lookup[vendor.unused_version_format]
    db.session.commit()

def downgrade():
    op.drop_constraint('vendors_ibfk_2', 'vendors', type_='foreignkey')
    op.drop_column('vendors', 'verfmt_id')
    op.drop_constraint('components_ibfk_4', 'components', type_='foreignkey')
    op.drop_column('components', 'verfmt_id')
    op.drop_table('verfmts')
    op.drop_constraint('protocol_ibfk_1', 'protocol', type_='foreignkey')
    op.drop_column('protocol', 'verfmt_id')
