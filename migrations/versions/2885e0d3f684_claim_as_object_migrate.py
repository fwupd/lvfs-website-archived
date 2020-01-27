"""

Revision ID: 2885e0d3f684
Revises: 9595113b929c
Create Date: 2020-01-27 14:21:54.315165

"""

# revision identifiers, used by Alembic.
revision = '2885e0d3f684'
down_revision = '9595113b929c'

from alembic import op
import sqlalchemy as sa

from lvfs import db
from lvfs.models import Claim, ComponentShardInfo, ComponentClaim

def upgrade():

    # add all the existing types
    db.session.add(Claim(kind='computrace',
                         icon='info',
                         summary='Contains Absolute Computrace Agent'))
    db.session.add(Claim(kind='hp-surestart',
                         icon='success',
                         summary='Contains HP Sure Start'))
    db.session.add(Claim(kind='uefi-shell',
                         icon='info',
                         summary='Contains UEFI Shell'))
    db.session.commit()

    # map the old name to the new ID
    claim_ids = {}
    for claim in db.session.query(Claim):
        claim_ids['{}-{}'.format(claim.icon, claim.kind)] = claim.claim_id
    for shard_info in db.session.query(ComponentShardInfo):
        if not shard_info._unused_claim_kind:
            continue
        shard_info.claim_id = claim_ids[shard_info._unused_claim_kind]
    for component_claim in db.session.query(ComponentClaim):
        component_claim.claim_id = claim_ids[component_claim._unused_kind]
    db.session.commit()

    op.alter_column('component_claims', 'claim_id',
               existing_type=sa.INTEGER(),
               nullable=False)

def downgrade():
    op.alter_column('component_claims', 'claim_id',
               existing_type=sa.INTEGER(),
               nullable=True)
