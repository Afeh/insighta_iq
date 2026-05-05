"""add query indexes for performance

Revision ID: 4_add_query_indexes
Revises: 3ee7c6207c36
Create Date: 2026-05-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4_add_query_indexes'
down_revision: Union[str, Sequence[str], None] = '3ee7c6207c36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add indexes for frequently queried columns."""
    # Index for gender filtering
    op.create_index('idx_profiles_gender', 'profiles', ['gender'])
    
    # Index for age filtering
    op.create_index('idx_profiles_age', 'profiles', ['age'])
    
    # Index for age_group filtering
    op.create_index('idx_profiles_age_group', 'profiles', ['age_group'])
    
    # Index for country_id filtering
    op.create_index('idx_profiles_country_id', 'profiles', ['country_id'])
    
    # Index for created_at sorting
    op.create_index('idx_profiles_created_at', 'profiles', ['created_at'])
    
    # Composite index for common filter combinations (gender + age)
    op.create_index('idx_profiles_gender_age', 'profiles', ['gender', 'age'])
    
    # Composite index for country + age (common combination)
    op.create_index('idx_profiles_country_age', 'profiles', ['country_id', 'age'])


def downgrade() -> None:
    """Downgrade schema - drop indexes."""
    op.drop_index('idx_profiles_country_age', table_name='profiles')
    op.drop_index('idx_profiles_gender_age', table_name='profiles')
    op.drop_index('idx_profiles_created_at', table_name='profiles')
    op.drop_index('idx_profiles_country_id', table_name='profiles')
    op.drop_index('idx_profiles_age_group', table_name='profiles')
    op.drop_index('idx_profiles_age', table_name='profiles')
    op.drop_index('idx_profiles_gender', table_name='profiles')
