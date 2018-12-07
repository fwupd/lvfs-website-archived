"""

Revision ID: b298782e35cb
Revises: 4641acfd71e3
Create Date: 2019-03-12 12:56:26.191637

"""

# revision identifiers, used by Alembic.
revision = 'b298782e35cb'
down_revision = '4641acfd71e3'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('firmware', sa.Column('banned_country_codes', sa.Text(), nullable=True))
    op.add_column('vendors', sa.Column('banned_country_codes', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('vendors', 'banned_country_codes')
    op.drop_column('firmware', 'banned_country_codes')
