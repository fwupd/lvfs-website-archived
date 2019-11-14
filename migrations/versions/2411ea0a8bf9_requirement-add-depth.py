"""

Revision ID: 2411ea0a8bf9
Revises: ef0591734691
Create Date: 2019-11-14 16:03:24.774172

"""

# revision identifiers, used by Alembic.
revision = '2411ea0a8bf9'
down_revision = 'ef0591734691'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('requirements', sa.Column('depth', sa.Integer(), nullable=True))

def downgrade():
    op.drop_column('requirements', 'depth')
