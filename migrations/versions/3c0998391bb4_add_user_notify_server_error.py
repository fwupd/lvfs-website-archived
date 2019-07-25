"""

Revision ID: 3c0998391bb4
Revises: d1b89f7256f6
Create Date: 2019-07-25 15:17:28.183849

"""

# revision identifiers, used by Alembic.
revision = '3c0998391bb4'
down_revision = 'd1b89f7256f6'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('users', sa.Column('notify_server_error', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('users', 'notify_server_error')
