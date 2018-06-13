"""

Revision ID: d210ef5deccb
Revises: 7f85346d339f
Create Date: 2018-06-13 17:22:11.191154

"""

# revision identifiers, used by Alembic.
revision = 'd210ef5deccb'
down_revision = '7f85346d339f'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('components', sa.Column('version_format', sa.String(length=10), nullable=True))

def downgrade():
    op.drop_column('components', 'version_format')
