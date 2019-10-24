"""

Revision ID: d5d554c30ce4
Revises: 4b78b3c65d57
Create Date: 2019-10-24 18:27:33.426659

"""

# revision identifiers, used by Alembic.
revision = 'd5d554c30ce4'
down_revision = '4b78b3c65d57'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('component_claims',
    sa.Column('component_claim_id', sa.Integer(), nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['components.component_id'], ),
    sa.PrimaryKeyConstraint('component_claim_id'),
    mysql_character_set='utf8mb4'
    )
    op.create_index(op.f('ix_component_claims_component_claim_id'), 'component_claims', ['component_claim_id'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_component_claims_component_claim_id'), table_name='component_claims')
    op.drop_table('component_claims')
