"""

Revision ID: 2fdd3f46da19
Revises: 5eaa6ae92bb7
Create Date: 2019-03-30 19:35:10.480408

"""

# revision identifiers, used by Alembic.
revision = '2fdd3f46da19'
down_revision = '5eaa6ae92bb7'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from lvfs import db
from lvfs.models import Client, _get_datestr_from_datetime

def upgrade():
    if 1:
        op.add_column('clients', sa.Column('datestr', sa.Integer(), nullable=True))
        op.create_index(op.f('ix_clients_datestr'), 'clients', ['datestr'], unique=False)

    # we have to break this into chunks to avoid having 4GB+ of Client objects
    cnt = 0
    while True:
        clients = db.session.query(Client).filter(Client.datestr == None).limit(10000).all()
        if not clients:
            break
        for c in clients:
            c.datestr = _get_datestr_from_datetime(c.timestamp)
            cnt += 1
            if cnt % 1000 == 0:
                print(cnt)
                db.session.commit()
    db.session.commit()

def downgrade():
    op.drop_index(op.f('ix_clients_datestr'), table_name='clients')
    op.drop_column('clients', 'datestr')
