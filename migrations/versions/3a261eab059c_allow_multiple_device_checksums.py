"""

Revision ID: 3a261eab059c
Revises: 6dde8aa078e5
Create Date: 2018-12-14 13:23:57.766317

"""

# revision identifiers, used by Alembic.
revision = '3a261eab059c'
down_revision = '031e02cbc569'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.create_table('checksums',
    sa.Column('checksum_id', sa.Integer(), nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['components.component_id'], ),
    sa.PrimaryKeyConstraint('checksum_id'),
    sa.UniqueConstraint('checksum_id'),
    mysql_character_set='utf8mb4'
    )
    op.drop_column('components', 'checksum_device')

def downgrade():
    op.add_column('components', sa.Column('checksum_device', mysql.VARCHAR(length=40), nullable=True))
    op.drop_table('checksums')
