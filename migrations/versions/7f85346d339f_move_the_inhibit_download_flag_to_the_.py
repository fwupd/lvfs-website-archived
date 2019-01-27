"""

Revision ID: 7f85346d339f
Revises: 45844e2b45c3
Create Date: 2018-06-13 16:58:42.357391

"""

# revision identifiers, used by Alembic.
revision = '7f85346d339f'
down_revision = '45844e2b45c3'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app import db
from app.models import Firmware

class FirmwareOld(db.Model):
  __tablename__ = 'firmware'
  __table_args__ = {'extend_existing': True}
  inhibit_download = db.Column(db.Boolean, default=False)

def upgrade():
    op.add_column('components', sa.Column('inhibit_download', sa.Boolean(), nullable=True))
    firmware_ids = []
    for fw in db.session.query(FirmwareOld).all():
        if fw.inhibit_download:
            firmware_ids.append(fw.firmware_id)
    for fw in db.session.query(Firmware).all():
        if fw.firmware_id in firmware_ids:
            for md in fw.mds:
                md.inhibit_download = True
    db.session.commit()
    op.drop_column('firmware', 'inhibit_download')

def downgrade():
    op.add_column('firmware', sa.Column('inhibit_download', mysql.TINYINT(display_width=1), server_default=sa.text('0'), autoincrement=False, nullable=True))
    op.drop_column('components', 'inhibit_download')
