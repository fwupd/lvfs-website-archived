"""

Revision ID: 18e5e636d4a8
Revises: fa9291165397
Create Date: 2020-09-09 14:30:53.044780

"""

# revision identifiers, used by Alembic.
revision = '18e5e636d4a8'
down_revision = 'fa9291165397'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('firmware', sa.Column('regenerate_ts', sa.DateTime(), nullable=True))
    op.add_column('remotes', sa.Column('regenerate_ts', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('remotes', 'regenerate_ts')
    op.drop_column('firmware', 'regenerate_ts')
