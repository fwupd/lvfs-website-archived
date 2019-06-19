"""

Revision ID: 65b618b6e525
Revises: 2fdd3f46da19
Create Date: 2019-04-03 09:35:43.126224

"""

# revision identifiers, used by Alembic.
revision = '65b618b6e525'
down_revision = '2fdd3f46da19'

import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from lvfs import db
from lvfs.models import Client, Vendor, AnalyticVendor, _get_datestr_from_datetime
from lvfs.dbutils import _execute_count_star

def upgrade():
    if 1:
        op.create_table('analytics_vendor',
        sa.Column('analytic_id', sa.Integer(), nullable=False),
        sa.Column('datestr', sa.Integer(), nullable=True),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('cnt', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.vendor_id'], ),
        sa.PrimaryKeyConstraint('analytic_id'),
        sa.UniqueConstraint('analytic_id'),
        mysql_character_set='utf8mb4'
        )
        op.create_index(op.f('ix_analytics_vendor_datestr'), 'analytics_vendor', ['datestr'], unique=False)
        op.create_index(op.f('ix_analytics_vendor_vendor_id'), 'analytics_vendor', ['vendor_id'], unique=False)

    # get all the vendor firmwares
    vendor_fws = {}
    for v in db.session.query(Vendor).all():
        fw_ids = []
        for fw in v.fws:
            fw_ids.append(fw.firmware_id)
        if not fw_ids:
            continue
        vendor_fws[v.vendor_id] = fw_ids

    # generate the last year of data for each vendor
    now = datetime.date.today() - datetime.timedelta(days=1)
    for _ in range(365):
        datestr = _get_datestr_from_datetime(now)
        for vendor_id in vendor_fws:
            print('processing %s:%s' % (datestr, vendor_id))
            fw_ids = vendor_fws[vendor_id]
            cnt = _execute_count_star(db.session.query(Client).\
                            filter(Client.firmware_id.in_(fw_ids)).\
                            filter(Client.datestr == datestr))
            db.session.add(AnalyticVendor(vendor_id, datestr, cnt))
        now -= datetime.timedelta(days=1)
        db.session.commit()

def downgrade():
    op.drop_index(op.f('ix_analytics_vendor_vendor_id'), table_name='analytics_vendor')
    op.drop_index(op.f('ix_analytics_vendor_datestr'), table_name='analytics_vendor')
    op.drop_table('analytics_vendor')
