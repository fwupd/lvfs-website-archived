"""

Revision ID: 61b9b75cb259
Revises: 9997d57e00c4
Create Date: 2019-05-13 09:51:33.419700

"""

# revision identifiers, used by Alembic.
revision = '61b9b75cb259'
down_revision = '9997d57e00c4'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.create_table('component_shard_infos',
    sa.Column('component_shard_info_id', sa.Integer(), nullable=False),
    sa.Column('guid', sa.String(length=36), nullable=True),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('cnt', sa.Integer()),
    sa.PrimaryKeyConstraint('component_shard_info_id'),
    sa.UniqueConstraint('component_shard_info_id'),
    mysql_character_set='utf8mb4'
    )
    op.create_index(op.f('ix_component_shard_infos_guid'), 'component_shard_infos', ['guid'], unique=False)
    op.create_table('component_shards',
    sa.Column('component_shard_id', sa.Integer(), nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('component_shard_info_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['components.component_id'], ),
    sa.ForeignKeyConstraint(['component_shard_info_id'], ['component_shard_infos.component_shard_info_id'], ),
    sa.PrimaryKeyConstraint('component_shard_id'),
    sa.UniqueConstraint('component_shard_id'),
    mysql_character_set='utf8mb4'
    )
    op.create_table('component_shard_checksums',
    sa.Column('checksum_id', sa.Integer(), nullable=False),
    sa.Column('component_shard_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['component_shard_id'], ['component_shards.component_shard_id'], ),
    sa.PrimaryKeyConstraint('checksum_id'),
    sa.UniqueConstraint('checksum_id'),
    mysql_character_set='utf8mb4'
    )

def downgrade():
    op.drop_table('component_shard_checksums')
    op.drop_table('component_shards')
    op.drop_index(op.f('ix_component_shard_infos_guid'), table_name='component_shard_infos')
    op.drop_table('component_shard_infos')
