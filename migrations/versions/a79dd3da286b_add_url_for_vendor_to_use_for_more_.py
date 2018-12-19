"""

Revision ID: a79dd3da286b
Revises: 6dde8aa078e5
Create Date: 2018-12-19 16:23:49.714809

"""

# revision identifiers, used by Alembic.
revision = 'a79dd3da286b'
down_revision = '6dde8aa078e5'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('vendors', sa.Column('url', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('vendors', 'url')
