"""

Revision ID: 229dccd843ab
Revises: b73c19797ab0
Create Date: 2019-03-29 14:55:00.229848

"""

# revision identifiers, used by Alembic.
revision = '229dccd843ab'
down_revision = 'b73c19797ab0'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('vendors', sa.Column('visible_on_landing', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('vendors', 'visible_on_landing')
