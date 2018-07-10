"""

Revision ID: cf1db1cb7fce
Revises: bb26893296d3
Create Date: 2018-07-10 19:40:11.347780

"""

# revision identifiers, used by Alembic.
revision = 'cf1db1cb7fce'
down_revision = 'bb26893296d3'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('users', sa.Column('password_recovery', sa.String(length=40), nullable=True))
    op.add_column('users', sa.Column('password_recovery_ts', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column('users', 'password_recovery_ts')
    op.drop_column('users', 'password_recovery')
