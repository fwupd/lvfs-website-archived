"""

Revision ID: 9595113b929c
Revises: 58a8c79cd632
Create Date: 2020-01-25 11:36:48.843219

"""

# revision identifiers, used by Alembic.
revision = '9595113b929c'
down_revision = '58a8c79cd632'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('claims',
    sa.Column('claim_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('icon', sa.Text(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('url', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('claim_id'),
    mysql_character_set='utf8mb4'
    )
    op.create_index(op.f('ix_claims_kind'), 'claims', ['kind'], unique=False)
    op.add_column('component_claims', sa.Column('claim_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_component_claims_claim_id'), 'component_claims', ['claim_id'], unique=False)
    op.create_foreign_key(None, 'component_claims', 'claims', ['claim_id'], ['claim_id'])
    op.add_column('component_shard_claims', sa.Column('claim_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'component_shard_claims', 'claims', ['claim_id'], ['claim_id'])
    op.add_column('component_shard_infos', sa.Column('claim_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_component_shard_infos_claim_id'), 'component_shard_infos', ['claim_id'], unique=False)
    op.create_foreign_key(None, 'component_shard_infos', 'claims', ['claim_id'], ['claim_id'])

def downgrade():
    op.drop_constraint(None, 'component_shard_infos', type_='foreignkey')
    op.drop_index(op.f('ix_component_shard_infos_claim_id'), table_name='component_shard_infos')
    op.drop_column('component_shard_infos', 'claim_id')
    op.drop_constraint(None, 'component_shard_claims', type_='foreignkey')
    op.drop_column('component_shard_claims', 'claim_id')
    op.drop_constraint(None, 'component_claims', type_='foreignkey')
    op.drop_index(op.f('ix_component_claims_claim_id'), table_name='component_claims')
    op.drop_column('component_claims', 'claim_id')
    op.drop_index(op.f('ix_claims_kind'), table_name='claims')
    op.drop_table('claims')
