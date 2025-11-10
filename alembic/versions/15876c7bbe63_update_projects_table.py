"""Update Projects Table

Revision ID: 15876c7bbe63
Revises: 531baa9737e9
Create Date: 2025-11-10 10:10:32.511444

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15876c7bbe63'
down_revision: Union[str, Sequence[str], None] = '531baa9737e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Modify ENUM values
    op.execute("""
        ALTER TABLE projects 
        MODIFY status ENUM('draft','pending_approval','approved','rejected')
        DEFAULT 'draft'
    """)

    # Add new workflow columns
    op.add_column('projects', sa.Column('team_id', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('approved_at', sa.DateTime(), nullable=True))
    op.add_column('projects', sa.Column('rejected_by', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('rejected_at', sa.DateTime(), nullable=True))

    # Create new foreign keys
    op.create_foreign_key(
        'fk_projects_rejected_by',
        'projects', 'users',
        ['rejected_by'], ['id']
    )

    # Ensure updated_at auto timestamp on update
    op.execute("""
        ALTER TABLE projects
        MODIFY updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    """)


def downgrade():
    # Revert updated_at if needed
    op.execute("""
        ALTER TABLE projects
        MODIFY updated_at DATETIME DEFAULT (now())
    """)

    # Drop foreign keys
    op.drop_constraint('fk_projects_rejected_by', 'projects', type_='foreignkey')
    op.drop_constraint('fk_projects_team', 'projects', type_='foreignkey')

    # Drop added columns
    op.drop_column('projects', 'approved_at')
    op.drop_column('projects', 'rejected_by')
    op.drop_column('projects', 'rejected_at')
    op.drop_column('projects', 'team_id')

    # Restore original ENUM
    op.execute("""
        ALTER TABLE projects 
        MODIFY status ENUM('active','completed','archived')
        DEFAULT NULL
    """)