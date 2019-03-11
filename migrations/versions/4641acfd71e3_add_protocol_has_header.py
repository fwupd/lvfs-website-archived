"""

Revision ID: 4641acfd71e3
Revises: 7c281751c3ec
Create Date: 2019-03-11 15:56:56.076248

"""

# revision identifiers, used by Alembic.
revision = '4641acfd71e3'
down_revision = '7c281751c3ec'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('protocol', sa.Column('has_header', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('protocol', 'has_header')
