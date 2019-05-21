"""

Revision ID: 5603c899b84a
Revises: bedf5c3841c6
Create Date: 2019-05-21 14:17:18.556884

"""

# revision identifiers, used by Alembic.
revision = '5603c899b84a'
down_revision = 'bedf5c3841c6'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.alter_column('keywords', 'value',
               existing_type=mysql.TEXT(),
               nullable=False)
    op.alter_column('search_events', 'value',
               existing_type=mysql.TEXT(),
               nullable=False)

def downgrade():
    op.alter_column('search_events', 'value',
               existing_type=mysql.TEXT(),
               nullable=True)
    op.alter_column('keywords', 'value',
               existing_type=mysql.TEXT(),
               nullable=True)
