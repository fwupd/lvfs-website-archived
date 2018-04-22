"""

Revision ID: 16f43da356f4
Revises: 44e3334bb64e
Create Date: 2018-04-22 20:53:07.417406

"""

# revision identifiers, used by Alembic.
revision = '16f43da356f4'
down_revision = '44e3334bb64e'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.create_table('firmware_limits',
    sa.Column('firmware_limit_id', sa.Integer(), nullable=False),
    sa.Column('firmware_id', sa.Integer(), nullable=False),
    sa.Column('value', sa.Integer(), nullable=False),
    sa.Column('user_agent_glob', sa.Text(), nullable=True),
    sa.Column('response', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['firmware_id'], ['firmware.firmware_id'], ),
    sa.PrimaryKeyConstraint('firmware_limit_id'),
    sa.UniqueConstraint('firmware_limit_id'),
    mysql_character_set='utf8mb4'
    )

def downgrade():
    op.drop_table('firmware_limits')
