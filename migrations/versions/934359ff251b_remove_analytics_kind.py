"""

Revision ID: 934359ff251b
Revises: 72b8a7b9db60
Create Date: 2018-03-15 20:05:03.697929

"""

# revision identifiers, used by Alembic.
revision = '934359ff251b'
down_revision = '72b8a7b9db60'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app import db
from app.models import Analytic

class AnalyticOld(db.Model):
  __tablename__ = 'analytics'
  __table_args__ = {'extend_existing': True}
  kind = db.Column(db.Integer, primary_key=True, default=0)

def upgrade():
    for analytic in db.session.query(AnalyticOld).all():
        if analytic.kind != 1:
            db.session.delete(analytic)
    db.session.commit()
    op.drop_index('datestr', 'analytics')
    op.create_primary_key('analytics_pk', 'analytics', ['datestr'])
    op.drop_column('analytics', 'kind')

def downgrade():
    op.add_column('analytics', sa.Column('kind', mysql.INTEGER(display_width=11), autoincrement=False, nullable=False))
