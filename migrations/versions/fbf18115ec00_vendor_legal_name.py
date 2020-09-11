"""

Revision ID: fbf18115ec00
Revises: 18e5e636d4a8
Create Date: 2020-09-11 09:36:41.437270

"""

# revision identifiers, used by Alembic.
revision = 'fbf18115ec00'
down_revision = '18e5e636d4a8'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('vendors', sa.Column('legal_name', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('vendors', 'legal_name')
