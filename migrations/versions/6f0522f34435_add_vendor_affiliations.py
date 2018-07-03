"""

Revision ID: 6f0522f34435
Revises: efa7a171590b
Create Date: 2018-07-01 16:32:37.271816

"""

# revision identifiers, used by Alembic.
revision = '6f0522f34435'
down_revision = 'efa7a171590b'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.create_table('affiliations',
    sa.Column('affiliation_id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('vendor_id', sa.Integer(), nullable=False),
    sa.Column('vendor_id_odm', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['vendor_id'], ['vendors.vendor_id'], ),
    sa.ForeignKeyConstraint(['vendor_id_odm'], ['vendors.vendor_id'], ),
    sa.PrimaryKeyConstraint('affiliation_id'),
    sa.UniqueConstraint('affiliation_id'),
    mysql_character_set='utf8mb4'
    )

def downgrade():
    op.drop_table('affiliations')
