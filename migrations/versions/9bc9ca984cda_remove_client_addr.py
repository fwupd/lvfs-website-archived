"""

Revision ID: 9bc9ca984cda
Revises: 3dc586299daf
Create Date: 2020-06-15 15:33:14.591154

"""

# revision identifiers, used by Alembic.
revision = '9bc9ca984cda'
down_revision = '3dc586299daf'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.drop_column('clients', 'addr')


def downgrade():
    op.add_column('clients', sa.Column('addr', sa.VARCHAR(length=40), autoincrement=False, nullable=False))
