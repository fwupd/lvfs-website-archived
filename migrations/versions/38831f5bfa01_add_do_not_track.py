"""

Revision ID: 38831f5bfa01
Revises: 3c0998391bb4
Create Date: 2019-08-04 14:34:28.624079

"""

# revision identifiers, used by Alembic.
revision = '38831f5bfa01'
down_revision = '3c0998391bb4'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('firmware', sa.Column('do_not_track', sa.Boolean(), nullable=True))
    op.add_column('vendors', sa.Column('do_not_track', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('vendors', 'do_not_track')
    op.drop_column('firmware', 'do_not_track')
