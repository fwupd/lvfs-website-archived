"""

Revision ID: 5e5acddd3a52
Revises: e6ac86c2f64e
Create Date: 2020-03-02 13:19:32.548107

"""

# revision identifiers, used by Alembic.
revision = '5e5acddd3a52'
down_revision = 'e6ac86c2f64e'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('components', sa.Column('checksum_contents_sha256', sa.String(length=64), nullable=True))
    op.alter_column('components', 'checksum_contents', existing_type=sa.String(40), new_column_name='checksum_contents_sha1')

def downgrade():
    op.drop_column('components', 'checksum_contents_sha256')
    op.alter_column('components', 'checksum_contents_sha1', existing_type=sa.String(40), new_column_name='checksum_contents')
