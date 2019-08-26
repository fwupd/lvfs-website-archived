"""

Revision ID: 1e56e78afabc
Revises: 61b9b75cb259
Create Date: 2019-05-15 16:29:01.223343

"""

# revision identifiers, used by Alembic.
revision = '1e56e78afabc'
down_revision = '61b9b75cb259'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from lvfs import db
from lvfs.models import Test

def upgrade():
    op.add_column('tests', sa.Column('scheduled_ts', sa.DateTime(), nullable=False))
    for test in db.session.query(Test):
        test.scheduled_ts = test.started_ts
    db.session.commit()

def downgrade():
    op.drop_column('tests', 'scheduled_ts')
