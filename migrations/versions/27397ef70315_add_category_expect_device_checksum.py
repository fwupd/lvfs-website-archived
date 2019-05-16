"""

Revision ID: 27397ef70315
Revises: 1e56e78afabc
Create Date: 2019-05-16 09:54:30.549139

"""

# revision identifiers, used by Alembic.
revision = '27397ef70315'
down_revision = '1e56e78afabc'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('categories', sa.Column('expect_device_checksum', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('categories', 'expect_device_checksum')
