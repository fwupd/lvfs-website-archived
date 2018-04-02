"""

Revision ID: 5e87dae99eab
Revises: f49b79b3ffdd
Create Date: 2018-04-02 11:07:13.698622

"""

# revision identifiers, used by Alembic.
revision = '5e87dae99eab'
down_revision = 'f49b79b3ffdd'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.drop_index('user_id', table_name='users')
    op.alter_column('users', 'username', existing_type=sa.Text, existing_nullable=False,
        type_=sa.String(80))
    op.alter_column('users', 'password', existing_type=sa.Text, existing_nullable=True,
        type_=mysql.BINARY(40))
    op.create_index('idx_username_password', 'users', ['username', 'password'])


def downgrade():
    op.create_index('user_id', 'users', ['user_id'], unique=True)
    op.drop_index('idx_username_password', 'users')
    op.alter_column('users', 'username', existing_type=sa.String(80), existing_nullable=False,
        type_=sa.Text)
    op.alter_column('users', 'password', existing_type=mysql.BINARY(40), existing_nullable=True,
        type_=sa.Text)
