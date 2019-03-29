"""

Revision ID: 5eaa6ae92bb7
Revises: 229dccd843ab
Create Date: 2019-03-29 16:06:38.622092

"""

# revision identifiers, used by Alembic.
revision = '5eaa6ae92bb7'
down_revision = '229dccd843ab'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('vendors', sa.Column('quote_author', sa.Text(), nullable=True))
    op.add_column('vendors', sa.Column('quote_text', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('vendors', 'quote_text')
    op.drop_column('vendors', 'quote_author')
