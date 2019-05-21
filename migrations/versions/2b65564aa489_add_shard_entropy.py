"""

Revision ID: 2b65564aa489
Revises: 5603c899b84a
Create Date: 2019-05-21 14:21:36.462053

"""

# revision identifiers, used by Alembic.
revision = '2b65564aa489'
down_revision = '5603c899b84a'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('component_shards', sa.Column('entropy', sa.Float(), nullable=True))

def downgrade():
    op.drop_column('component_shards', 'entropy')
