"""

Revision ID: dbf9a3d31989
Revises: 2233c26bbe15
Create Date: 2020-01-29 10:40:52.679943

"""

# revision identifiers, used by Alembic.
revision = 'dbf9a3d31989'
down_revision = '2233c26bbe15'

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table('component_shard_attributes',
    sa.Column('component_shard_attribute_id', sa.Integer(), nullable=False),
    sa.Column('component_shard_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('value', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['component_shard_id'], ['component_shards.component_shard_id'], ),
    sa.PrimaryKeyConstraint('component_shard_attribute_id'),
    mysql_character_set='utf8mb4'
    )
    op.create_index(op.f('ix_component_shard_attributes_component_shard_id'), 'component_shard_attributes', ['component_shard_id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_component_shard_attributes_component_shard_id'), table_name='component_shard_attributes')
    op.drop_table('component_shard_attributes')
