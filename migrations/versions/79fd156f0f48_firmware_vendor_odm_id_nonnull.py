"""

Revision ID: 79fd156f0f48
Revises: bf6316b24565
Create Date: 2020-04-22 15:37:44.972630

"""

# revision identifiers, used by Alembic.
revision = '79fd156f0f48'
down_revision = 'bf6316b24565'

from alembic import op
import sqlalchemy as sa

from lvfs import db
from lvfs.models import Firmware

def upgrade():
    for fw in db.session.query(Firmware):
        fw.vendor_odm = fw.user.vendor
    db.session.commit()
    op.alter_column('firmware', 'vendor_odm_id',
               existing_type=sa.INTEGER(),
               nullable=False)

def downgrade():
    op.alter_column('firmware', 'vendor_odm_id',
               existing_type=sa.INTEGER(),
               nullable=True)
