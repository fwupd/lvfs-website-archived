"""

Revision ID: 1822ddbf2a73
Revises: 7cd25be1d3ee
Create Date: 2019-09-10 11:58:50.232999

"""

# revision identifiers, used by Alembic.
revision = '1822ddbf2a73'
down_revision = '7cd25be1d3ee'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.drop_column('vendors', 'is_fwupd_supported')
    op.drop_column('vendors', 'is_uploading')

def downgrade():
    op.add_column('vendors', sa.Column('is_uploading', mysql.VARCHAR(charset='utf8', length=16), server_default=sa.text("'no'"), nullable=False))
    op.add_column('vendors', sa.Column('is_fwupd_supported', mysql.VARCHAR(charset='utf8', length=16), server_default=sa.text("'no'"), nullable=False))
