"""

Revision ID: d1b89f7256f6
Revises: 17bb8d5d9e0f
Create Date: 2019-06-06 11:41:51.748727

"""

# revision identifiers, used by Alembic.
revision = 'd1b89f7256f6'
down_revision = 'cc1b0354c408'

from alembic import op
import sqlalchemy as sa

from lvfs import db
from lvfs.models import Firmware

def upgrade():
    op.add_column('firmware', sa.Column('failure_minimum', sa.Integer(), nullable=True))
    op.add_column('firmware', sa.Column('failure_percentage', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('notify_demote_failures', sa.Boolean(), nullable=True))

    # repair old firmware
    for fw in db.session.query(Firmware).all():
        fw.failure_minimum = 5
        fw.failure_percentage = 70
    db.session.commit()

def downgrade():
    op.drop_column('firmware', 'failure_percentage')
    op.drop_column('firmware', 'failure_minimum')
    op.drop_column('users', 'notify_demote_failures')
