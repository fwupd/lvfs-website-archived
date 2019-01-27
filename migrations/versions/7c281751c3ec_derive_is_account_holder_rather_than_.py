"""

Revision ID: 7c281751c3ec
Revises: e1dc251adcab
Create Date: 2019-01-25 21:31:17.781831

"""

# revision identifiers, used by Alembic.
revision = '7c281751c3ec'
down_revision = 'e1dc251adcab'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.drop_column('vendors', 'is_account_holder')

def downgrade():
    op.add_column('vendors', sa.Column('is_account_holder', mysql.VARCHAR(charset='utf8', length=16), server_default=sa.text("'no'"), nullable=False))
