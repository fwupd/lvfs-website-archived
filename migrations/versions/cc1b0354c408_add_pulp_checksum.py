"""

Revision ID: cc1b0354c408
Revises: 17bb8d5d9e0f
Create Date: 2019-06-20 17:56:51.434967

"""

# revision identifiers, used by Alembic.
revision = 'cc1b0354c408'
down_revision = '17bb8d5d9e0f'

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('firmware', sa.Column('checksum_pulp', sa.String(length=64), nullable=False))

def downgrade():
    op.drop_column('firmware', 'checksum_pulp')
