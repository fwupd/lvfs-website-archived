"""

Revision ID: 57315c468b88
Revises: f1d919f4797b
Create Date: 2020-04-03 09:00:57.518675

"""

# revision identifiers, used by Alembic.
revision = '57315c468b88'
down_revision = 'f1d919f4797b'

from collections import defaultdict

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('remotes', sa.Column('build_cnt', sa.Integer(), nullable=True))

def downgrade():
    op.drop_column('remotes', 'build_cnt')

# run with PYTHONPATH=.
if __name__ == '__main__':
    from lvfs import db
    from lvfs.models import Event, Remote

    # get hash table of every time we signed a remote
    remote_build_cnts = defaultdict(int)
    for evt in db.session.query(Event)\
                         .filter(Event.vendor_id == 1)\
                         .filter(Event.user_id == 2)\
                         .filter(Event.address == '127.0.0.1')\
                         .filter(Event.message.startswith('Signed metadata'))\
                         .order_by(Event.timestamp.desc()):
        remote_build_cnts[evt.message[16:]] += 1

    # set the built count correctly
    for remote_name in remote_build_cnts:
        remote = db.session.query(Remote)\
                           .filter(Remote.name == remote_name)\
                           .first()
        if not remote:
            print('failed to find {}'.format(remote_name))
            continue
        print('setting {} to {}'.format(remote_name, remote_build_cnts[remote_name]))
        remote.build_cnt = remote_build_cnts[remote_name]

    # done
    db.session.commit()
