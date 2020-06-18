"""

Revision ID: 13fe98071e44
Revises: 9bc9ca984cda
Create Date: 2020-06-18 13:57:18.897618

"""

# revision identifiers, used by Alembic.
revision = '13fe98071e44'
down_revision = '9bc9ca984cda'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('remotes', sa.Column('access_token', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('remotes', 'access_token')
