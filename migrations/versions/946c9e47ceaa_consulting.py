"""

Revision ID: 946c9e47ceaa
Revises: 4cecae8c1345
Create Date: 2019-11-18 17:04:41.162978

"""

# revision identifiers, used by Alembic.
revision = '946c9e47ceaa'
down_revision = '4cecae8c1345'

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('vendors', sa.Column('consulting_link', sa.Text(), nullable=True))
    op.add_column('vendors', sa.Column('consulting_text', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('vendors', 'consulting_text')
    op.drop_column('vendors', 'consulting_link')
