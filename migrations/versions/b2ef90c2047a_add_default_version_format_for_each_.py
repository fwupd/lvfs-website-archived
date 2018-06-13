"""

Revision ID: b2ef90c2047a
Revises: d210ef5deccb
Create Date: 2018-06-19 16:04:15.667075

"""

# revision identifiers, used by Alembic.
revision = 'b2ef90c2047a'
down_revision = 'd210ef5deccb'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('vendors', sa.Column('version_format', sa.String(length=10), nullable=True))

def downgrade():
    op.drop_column('vendors', 'version_format')
