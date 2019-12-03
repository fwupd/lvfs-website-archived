"""

Revision ID: ae8f6b33ba7d
Revises: 946c9e47ceaa
Create Date: 2019-12-03 21:14:10.737816

"""

# revision identifiers, used by Alembic.
revision = 'ae8f6b33ba7d'
down_revision = '946c9e47ceaa'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('components', sa.Column('release_tag', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('components', 'release_tag')
