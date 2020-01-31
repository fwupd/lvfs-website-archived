"""

Revision ID: 842bdde8f550
Revises: e076643fdb96
Create Date: 2020-01-31 11:55:39.492410

"""

# revision identifiers, used by Alembic.
revision = '842bdde8f550'
down_revision = 'c26f0a8c9572'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('claims', sa.Column('description', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('claims', 'description')
