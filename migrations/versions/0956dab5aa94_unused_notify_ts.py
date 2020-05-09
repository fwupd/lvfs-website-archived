"""

Revision ID: 0956dab5aa94
Revises: 79fd156f0f48
Create Date: 2020-05-09 21:35:17.267496

"""

# revision identifiers, used by Alembic.
revision = '0956dab5aa94'
down_revision = '79fd156f0f48'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('users', sa.Column('unused_notify_ts', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('users', 'unused_notify_ts')
