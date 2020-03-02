"""

Revision ID: 160f5fd39ab4
Revises: 5e5acddd3a52
Create Date: 2020-03-02 14:56:56.488018

"""

# revision identifiers, used by Alembic.
revision = '160f5fd39ab4'
down_revision = '5e5acddd3a52'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column('components', 'checksum_contents_sha256',
               existing_type=sa.VARCHAR(length=64),
               nullable=False)

def downgrade():
    op.alter_column('components', 'checksum_contents_sha256',
               existing_type=sa.VARCHAR(length=64),
               nullable=True)
