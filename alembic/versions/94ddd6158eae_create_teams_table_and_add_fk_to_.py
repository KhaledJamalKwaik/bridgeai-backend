"""Create Teams Table And Add FK To Projects Table

Revision ID: 94ddd6158eae
Revises: 15876c7bbe63
Create Date: 2025-11-10 10:22:23.243261

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '94ddd6158eae'
down_revision: Union[str, Sequence[str], None] = '15876c7bbe63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Create teams table
    op.create_table(
        'teams',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(256), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False)
    )

    # Add FK for team_id already added in previous migration
    op.create_foreign_key(
        'fk_projects_team',
        'projects', 'teams',
        ['team_id'], ['id']
    )


def downgrade():
    op.drop_constraint('fk_projects_team', 'projects', type_='foreignkey')
    op.drop_table('teams')
