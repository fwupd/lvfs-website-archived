"""

Revision ID: c26f0a8c9572
Revises: e076643fdb96
Create Date: 2020-02-03 17:55:03.987499

"""

# revision identifiers, used by Alembic.
revision = 'c26f0a8c9572'
down_revision = 'e076643fdb96'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('metrics',
    sa.Column('setting_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('value', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('setting_id')
    )

def downgrade():
    op.drop_table('metrics')
