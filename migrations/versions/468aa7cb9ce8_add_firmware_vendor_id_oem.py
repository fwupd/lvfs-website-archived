"""

Revision ID: 468aa7cb9ce8
Revises: 38831f5bfa01
Create Date: 2019-08-12 14:07:11.123844

"""

# revision identifiers, used by Alembic.
revision = '468aa7cb9ce8'
down_revision = '814ccd8a065b'

from alembic import op
import sqlalchemy as sa

from lvfs import db
from lvfs.models import Firmware

def upgrade():
    op.add_column('firmware', sa.Column('vendor_id_oem', sa.Integer(), nullable=False))
    for fw in db.session.query(Firmware).all():
        fw.vendor_id_oem = fw.vendor_id
    db.session.commit()
    op.create_foreign_key('firmware_ibfk_vendor_id_oem', 'firmware', 'vendors', ['vendor_id_oem'], ['vendor_id'])

def downgrade():
    op.drop_constraint('firmware_ibfk_vendor_id_oem', 'firmware', type_='foreignkey')
    op.drop_column('firmware', 'vendor_id_oem')
