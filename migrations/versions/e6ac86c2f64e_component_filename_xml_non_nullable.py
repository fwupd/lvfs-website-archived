"""

Revision ID: e6ac86c2f64e
Revises: e708c5099055
Create Date: 2020-03-02 11:16:42.236436

"""

# revision identifiers, used by Alembic.
revision = 'e6ac86c2f64e'
down_revision = 'e708c5099055'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column('components', 'filename_xml',
               existing_type=sa.TEXT(),
               nullable=False)

def downgrade():
    op.alter_column('components', 'filename_xml',
               existing_type=sa.TEXT(),
               nullable=True)
