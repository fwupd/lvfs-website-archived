"""

Revision ID: 17bb8d5d9e0f
Revises: 3e12b1ee63bf
Create Date: 2019-05-31 13:12:11.732272

"""

# revision identifiers, used by Alembic.
revision = '17bb8d5d9e0f'
down_revision = '3e12b1ee63bf'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('component_shard_certificates',
    sa.Column('component_shard_certificate_id', sa.Integer(), nullable=False),
    sa.Column('component_shard_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=True),
    sa.Column('plugin_id', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('serial_number', sa.Text(), nullable=True),
    sa.Column('not_before', sa.DateTime(), nullable=True),
    sa.Column('not_after', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['component_shard_id'], ['component_shards.component_shard_id'], ),
    sa.PrimaryKeyConstraint('component_shard_certificate_id'),
    sa.UniqueConstraint('component_shard_certificate_id'),
    mysql_character_set='utf8mb4'
    )

def downgrade():
    op.drop_table('component_shard_certificates')
