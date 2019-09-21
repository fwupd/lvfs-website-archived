"""

Revision ID: e0f5f8381a8d
Revises: 0fc01b4d6dce
Create Date: 2019-09-21 12:20:45.882858

"""

# revision identifiers, used by Alembic.
revision = 'e0f5f8381a8d'
down_revision = '0fc01b4d6dce'

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('components', sa.Column('name_variant_suffix', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('components', 'name_variant_suffix')
