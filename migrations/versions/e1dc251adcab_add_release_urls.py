"""

Revision ID: e1dc251adcab
Revises: 1df57688bcc5
Create Date: 2019-01-23 15:57:46.154314

"""

# revision identifiers, used by Alembic.
revision = 'e1dc251adcab'
down_revision = '1df57688bcc5'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('components', sa.Column('details_url', sa.Text(), nullable=True))
    op.add_column('components', sa.Column('source_url', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('components', 'source_url')
    op.drop_column('components', 'details_url')
