"""

Revision ID: e076643fdb96
Revises: dbf9a3d31989
Create Date: 2020-01-31 08:51:22.547546

"""

# revision identifiers, used by Alembic.
revision = 'e076643fdb96'
down_revision = 'dbf9a3d31989'

from lvfs import db
from lvfs.models import User

def upgrade():
    for user in db.session.query(User):
        user.username = user.username.lower()
    db.session.commit()

def downgrade():
    pass
