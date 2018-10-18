"""

Revision ID: 3fd6598319ec
Revises: cf1db1cb7fce
Create Date: 2018-10-18 19:55:22.394563

"""

# revision identifiers, used by Alembic.
revision = '3fd6598319ec'
down_revision = 'cf1db1cb7fce'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('components', sa.Column('priority', sa.Integer(), nullable=True))

def downgrade():
    op.drop_column('components', 'priority')
