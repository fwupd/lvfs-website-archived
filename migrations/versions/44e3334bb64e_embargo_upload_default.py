"""

Revision ID: 44e3334bb64e
Revises: e49864726960
Create Date: 2018-04-11 21:57:17.965477

"""

# revision identifiers, used by Alembic.
revision = '44e3334bb64e'
down_revision = 'e49864726960'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('vendors', sa.Column('is_embargo_default', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('vendors', 'is_embargo_default')
