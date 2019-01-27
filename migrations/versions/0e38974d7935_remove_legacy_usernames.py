"""

Revision ID: 0e38974d7935
Revises: 687f5c4d0aa3
Create Date: 2018-11-19 09:23:39.940350

"""

# revision identifiers, used by Alembic.
revision = '0e38974d7935'
down_revision = '8b4c4d30c3fd'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.drop_column('users', 'username_old')

def downgrade():
    op.add_column('users', sa.Column('username_old', mysql.TEXT(charset='utf8'), nullable=True))
