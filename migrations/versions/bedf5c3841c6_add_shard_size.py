"""

Revision ID: bedf5c3841c6
Revises: 27397ef70315
Create Date: 2019-05-21 09:38:52.252701

"""

# revision identifiers, used by Alembic.
revision = 'bedf5c3841c6'
down_revision = '27397ef70315'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('component_shards', sa.Column('size', sa.Integer(), nullable=True))

def downgrade():
    op.drop_column('component_shards', 'size')
