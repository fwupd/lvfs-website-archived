"""

Revision ID: 4b78b3c65d57
Revises: e0f5f8381a8d
Create Date: 2019-10-15 19:30:19.318100

"""

# revision identifiers, used by Alembic.
revision = '4b78b3c65d57'
down_revision = 'e0f5f8381a8d'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('yara_query',
    sa.Column('yara_query_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('value', sa.Text(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('found', sa.Integer(), nullable=True),
    sa.Column('total', sa.Integer(), nullable=True),
    sa.Column('ctime', sa.DateTime(), nullable=False),
    sa.Column('started_ts', sa.DateTime(), nullable=True),
    sa.Column('ended_ts', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('yara_query_id'),
    sa.UniqueConstraint('yara_query_id'),
    mysql_character_set='utf8mb4'
    )
    op.create_table('yara_query_result',
    sa.Column('yara_query_result_id', sa.Integer(), nullable=False),
    sa.Column('yara_query_id', sa.Integer(), nullable=False),
    sa.Column('component_shard_id', sa.Integer(), nullable=False),
    sa.Column('result', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['component_shard_id'], ['component_shards.component_shard_id'], ),
    sa.ForeignKeyConstraint(['yara_query_id'], ['yara_query.yara_query_id'], ),
    sa.PrimaryKeyConstraint('yara_query_result_id'),
    sa.UniqueConstraint('yara_query_result_id'),
    mysql_character_set='utf8mb4'
    )
    op.add_column('users', sa.Column('is_researcher', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('users', 'is_researcher')
    op.drop_table('yara_query_result')
    op.drop_table('yara_query')
