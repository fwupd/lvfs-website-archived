"""

Revision ID: 5bcdefe58b44
Revises: 8f394b9db1f0
Create Date: 2018-12-06 14:48:18.849780

"""

# revision identifiers, used by Alembic.
revision = '5bcdefe58b44'
down_revision = '8f394b9db1f0'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('users', sa.Column('human_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'users', 'users', ['human_user_id'], ['user_id'])

def downgrade():
    op.drop_constraint(None, 'users', type_='foreignkey')
    op.drop_column('users', 'human_user_id')
