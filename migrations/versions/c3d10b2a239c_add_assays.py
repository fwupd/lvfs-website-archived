"""

Revision ID: c3d10b2a239c
Revises: a79dd3da286b
Create Date: 2019-01-10 14:25:35.915843

"""

# revision identifiers, used by Alembic.
revision = 'c3d10b2a239c'
down_revision = 'a79dd3da286b'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.create_table('assays',
    sa.Column('assay_id', sa.Integer(), nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('plugin_id', sa.Text(), nullable=True),
    sa.Column('waivable', sa.Boolean(), nullable=True),
    sa.Column('started_ts', sa.DateTime(), nullable=True),
    sa.Column('ended_ts', sa.DateTime(), nullable=True),
    sa.Column('waived_ts', sa.DateTime(), nullable=True),
    sa.Column('waived_user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['component_id'], ['components.component_id'], ),
    sa.ForeignKeyConstraint(['waived_user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('assay_id'),
    sa.UniqueConstraint('assay_id'),
    mysql_character_set='utf8mb4'
    )
    op.create_table('assay_attributes',
    sa.Column('assay_attribute_id', sa.Integer(), nullable=False),
    sa.Column('assay_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('success', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['assay_id'], ['assays.assay_id'], ),
    sa.PrimaryKeyConstraint('assay_attribute_id'),
    sa.UniqueConstraint('assay_attribute_id'),
    mysql_character_set='utf8mb4'
    )

def downgrade():
    op.drop_table('assay_attributes')
    op.drop_table('assays')
