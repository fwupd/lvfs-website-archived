"""

Revision ID: 687f5c4d0aa3
Revises: 688568bacd0a
Create Date: 2018-11-10 11:15:39.213906

"""

# revision identifiers, used by Alembic.
revision = '687f5c4d0aa3'
down_revision = '688568bacd0a'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('components', sa.Column('install_duration', sa.Integer(), nullable=True))

def downgrade():
    op.drop_column('components', 'install_duration')
