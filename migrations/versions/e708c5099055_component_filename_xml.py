"""

Revision ID: e708c5099055
Revises: 842bdde8f550
Create Date: 2020-03-02 10:33:19.142814

"""

# revision identifiers, used by Alembic.
revision = 'e708c5099055'
down_revision = '842bdde8f550'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('components', sa.Column('filename_xml', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('components', 'filename_xml')
