"""

Revision ID: 688568bacd0a
Revises: b1851318108b
Create Date: 2018-11-05 10:11:08.713672

"""

# revision identifiers, used by Alembic.
revision = '688568bacd0a'
down_revision = 'b1851318108b'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('firmware', sa.Column('is_dirty', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('firmware', 'is_dirty')
