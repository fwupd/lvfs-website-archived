"""

Revision ID: 031e02cbc569
Revises: 5bcdefe58b44
Create Date: 2018-12-12 11:09:56.336055

"""

# revision identifiers, used by Alembic.
revision = '031e02cbc569'
down_revision = '5bcdefe58b44'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('components', sa.Column('checksum_device', sa.String(length=40), nullable=True))

def downgrade():
    op.drop_column('components', 'checksum_device')
