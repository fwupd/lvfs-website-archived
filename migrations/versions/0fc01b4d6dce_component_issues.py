"""

Revision ID: 0fc01b4d6dce
Revises: 858f56a164c8
Create Date: 2019-09-13 17:54:52.101241

"""

# revision identifiers, used by Alembic.
revision = '0fc01b4d6dce'
down_revision = '858f56a164c8'

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table('component_issues',
    sa.Column('component_issue_id', sa.Integer(), nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['components.component_id'], ),
    sa.PrimaryKeyConstraint('component_issue_id'),
    mysql_character_set='utf8mb4'
    )
    op.create_index(op.f('ix_component_issues_component_issue_id'), 'component_issues', ['component_issue_id'], unique=True)

def downgrade():
    op.drop_index(op.f('ix_component_issues_component_issue_id'), table_name='component_issues')
    op.drop_table('component_issues')
