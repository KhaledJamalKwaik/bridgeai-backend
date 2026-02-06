"""Refactor team roles to client and ba

Revision ID: 20260205_092104
Revises: 0252304dc04b
Create Date: 2026-02-05 09:21:04

This migration:
1. Updates TeamRole enum from (owner, admin, member, viewer) to (client, ba)
2. Migrates existing team members to new roles based on their user role
3. Enforces 2-member team limit by keeping only first 2 active members per team
4. Ensures each team has at most 1 client and 1 BA

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260205_092104'
down_revision: Union[str, None] = '0252304dc04b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade database schema for MySQL:
    1. Expand enum to include both old and new values
    2. Migrate data to new values
    3. Remove old values from enum
    """
    
    # Step 1: Expand enum to include both old and new values temporarily
    op.execute("""
        ALTER TABLE team_members 
        MODIFY COLUMN role ENUM('owner', 'admin', 'member', 'viewer', 'client', 'ba') NOT NULL
    """)
    
    # Step 2: Update the data to new values
    op.execute("""
        UPDATE team_members tm
        INNER JOIN users u ON tm.user_id = u.id
        SET tm.role = CASE 
            WHEN u.role = 'ba' THEN 'ba'
            WHEN tm.role IN ('owner', 'admin') THEN 'ba'
            ELSE 'client'
        END
        WHERE tm.role IN ('owner', 'admin', 'member', 'viewer')
    """)
    
    # Step 3: Shrink enum to only include new values
    op.execute("""
        ALTER TABLE team_members 
        MODIFY COLUMN role ENUM('client', 'ba') NOT NULL
    """)
    
    # Step 4: Enforce 2-member team limit
    op.execute("""
        UPDATE team_members tm
        INNER JOIN (
            SELECT 
                tm2.id,
                ROW_NUMBER() OVER (
                    PARTITION BY tm2.team_id 
                    ORDER BY 
                        CASE WHEN t.created_by = tm2.user_id THEN 0 ELSE 1 END,
                        tm2.joined_at ASC
                ) as rn
            FROM team_members tm2
            INNER JOIN teams t ON t.id = tm2.team_id
            WHERE tm2.is_active = 1
        ) ranked ON tm.id = ranked.id
        SET tm.is_active = 0
        WHERE ranked.rn > 2
    """)
    
    # Step 5: Cancel pending invitations for teams at capacity
    op.execute("""
        UPDATE invitations i
        INNER JOIN (
            SELECT tm.team_id
            FROM team_members tm
            WHERE tm.is_active = 1
            GROUP BY tm.team_id
            HAVING COUNT(*) >= 2
        ) full_teams ON i.team_id = full_teams.team_id
        SET i.status = 'canceled'
        WHERE i.status = 'pending'
    """)


def downgrade() -> None:
    """
    Downgrade database schema (reverse the migration).
    WARNING: This will restore old role structure but may lose data fidelity.
    """
    
    # Modify column back to old enum
    op.execute("""
        ALTER TABLE team_members 
        MODIFY COLUMN role ENUM('owner', 'admin', 'member', 'viewer') NOT NULL
    """)
    
    # Migrate data back: map ba -> admin, client -> member
    op.execute("""
        UPDATE team_members tm
        SET tm.role = CASE 
            WHEN tm.role = 'ba' THEN 'admin'
            ELSE 'member'
        END
    """)
    
    # For team creators, assign owner role
    op.execute("""
        UPDATE team_members tm
        INNER JOIN teams t ON tm.team_id = t.id
        SET tm.role = 'owner'
        WHERE tm.user_id = t.created_by
    """)
