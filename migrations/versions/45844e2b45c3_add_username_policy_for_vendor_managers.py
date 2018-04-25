"""

Revision ID: 45844e2b45c3
Revises: 16f43da356f4
Create Date: 2018-04-25 10:55:33.771042

"""

# revision identifiers, used by Alembic.
revision = '45844e2b45c3'
down_revision = '16f43da356f4'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('vendors', sa.Column('username_glob', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('vendors', 'username_glob')
