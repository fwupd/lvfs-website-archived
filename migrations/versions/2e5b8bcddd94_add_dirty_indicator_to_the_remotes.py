"""

Revision ID: 2e5b8bcddd94
Revises: f49b79b3ffdd
Create Date: 2018-03-19 13:43:51.852703

"""

# revision identifiers, used by Alembic.
revision = '2e5b8bcddd94'
down_revision = 'fd4c8cf000ce'

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('remotes', sa.Column('is_dirty', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('remotes', 'is_dirty')
