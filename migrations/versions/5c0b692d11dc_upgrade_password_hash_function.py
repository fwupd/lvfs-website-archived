"""

Revision ID: 5c0b692d11dc
Revises: 2fe8c6bfedb7
Create Date: 2019-01-20 20:25:18.905014

"""

# revision identifiers, used by Alembic.
revision = '5c0b692d11dc'
down_revision = '2fe8c6bfedb7'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.alter_column('users', 'password',
               existing_type=mysql.VARCHAR(length=40),
               type_=sa.String(length=128),
               existing_nullable=True)

def downgrade():
    op.alter_column('users', 'password',
               existing_type=sa.String(length=128),
               type_=mysql.VARCHAR(length=40),
               existing_nullable=True)
