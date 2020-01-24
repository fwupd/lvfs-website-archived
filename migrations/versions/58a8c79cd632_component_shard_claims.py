"""

Revision ID: 58a8c79cd632
Revises: e1b495a29979
Create Date: 2020-01-24 12:02:34.098059

"""

# revision identifiers, used by Alembic.
revision = '58a8c79cd632'
down_revision = 'e1b495a29979'

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table('component_shard_claims',
    sa.Column('component_shard_claim_id', sa.Integer(), nullable=False),
    sa.Column('component_shard_info_id', sa.Integer(), nullable=True),
    sa.Column('checksum', sa.Text(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=True),
    sa.Column('value', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['component_shard_info_id'], ['component_shard_infos.component_shard_info_id'], ),
    sa.PrimaryKeyConstraint('component_shard_claim_id'),
    mysql_character_set='utf8mb4'
    )

def downgrade():
    op.drop_table('component_shard_claims')
