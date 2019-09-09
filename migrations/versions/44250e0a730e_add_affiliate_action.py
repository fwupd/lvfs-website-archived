"""

Revision ID: 44250e0a730e
Revises: 9373c9ac33da
Create Date: 2019-09-09 11:30:12.578540

"""

# revision identifiers, used by Alembic.
revision = '44250e0a730e'
down_revision = '9373c9ac33da'

from alembic import op
import sqlalchemy as sa

from lvfs import db
from lvfs.models import Affiliation, AffiliationAction

def upgrade():
    op.create_table('affiliation_actions',
    sa.Column('affiliation_action_id', sa.Integer(), nullable=False),
    sa.Column('affiliation_id', sa.Integer(), nullable=False),
    sa.Column('ctime', sa.DateTime(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['affiliation_id'], ['affiliations.affiliation_id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('affiliation_action_id'),
    sa.UniqueConstraint('affiliation_action_id'),
    mysql_character_set='utf8mb4'
    )

    # migrate affiliates to a sane set
    for aff in db.session.query(Affiliation):
        if aff.actions:
            continue
        for action in ['@delete',
                       '@modify',
                       '@undelete',
                       '@modify-updateinfo',
                       '@view']:
            aff.actions.append(AffiliationAction(action=action, user_id=1))
    db.session.commit()

def downgrade():
    op.drop_table('affiliation_actions')
