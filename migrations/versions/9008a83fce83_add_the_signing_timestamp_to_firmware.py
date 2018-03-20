"""

Revision ID: 9008a83fce83
Revises: 2e5b8bcddd94
Create Date: 2018-03-20 09:44:19.277911

"""

# revision identifiers, used by Alembic.
revision = '9008a83fce83'
down_revision = '2e5b8bcddd94'

from alembic import op
import sqlalchemy as sa

from app import db
from app.models import Firmware

def upgrade():
    op.add_column('firmware', sa.Column('signed_timestamp', sa.DateTime(), nullable=True))

    # assume the upload timestamp is the signing timestamp
    for fw in db.session.query(Firmware).all():
        if not fw.signed_timestamp:
            fw.signed_timestamp = fw.timestamp
    db.session.commit()

def downgrade():
    op.drop_column('firmware', 'signed_timestamp')
