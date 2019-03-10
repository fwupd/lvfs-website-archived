"""

Revision ID: b73c19797ab0
Revises: 03e7f95f0cd7
Create Date: 2019-03-10 20:29:40.150003

"""

# revision identifiers, used by Alembic.
revision = 'b73c19797ab0'
down_revision = '03e7f95f0cd7'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('reports', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'reports', 'users', ['user_id'], ['user_id'])

def downgrade():
    op.drop_constraint(None, 'reports', type_='foreignkey')
    op.drop_column('reports', 'user_id')
