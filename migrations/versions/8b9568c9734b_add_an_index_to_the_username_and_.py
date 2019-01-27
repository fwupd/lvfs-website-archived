"""

Revision ID: 8b9568c9734b
Revises: 9008a83fce83
Create Date: 2018-04-03 10:59:23.526389

"""

# revision identifiers, used by Alembic.
revision = '8b9568c9734b'
down_revision = '9008a83fce83'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.alter_column('users', 'password',
               existing_type=mysql.TEXT(charset='utf8mb4'),
               type_=sa.String(length=40),
               existing_nullable=True)
    op.alter_column('users', 'username',
               existing_type=mysql.TEXT(),
               type_=sa.String(length=80),
               existing_nullable=False)
    op.create_index('idx_users_username_password', 'users', ['username', 'password'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index('idx_users_username_password', table_name='users')
    op.alter_column('users', 'username',
               existing_type=sa.String(length=80),
               type_=mysql.TEXT(),
               existing_nullable=False)
    op.alter_column('users', 'password',
               existing_type=sa.String(length=40),
               type_=mysql.TEXT(charset='utf8mb4'),
               existing_nullable=True)
