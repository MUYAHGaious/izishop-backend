"""Update subscription table for Tranzak integration

Revision ID: update_subscription_for_tranzak
Revises: add_multi_role_system
Create Date: 2025-09-01 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'update_subscription_for_tranzak'
down_revision = 'add_multi_role_system'
branch_labels = None
depends_on = None


def upgrade():
    # Replace stripe_subscription_id with tranzak_request_id
    op.add_column('subscriptions', sa.Column('tranzak_request_id', sa.String(255), nullable=True))
    
    # Create unique index for tranzak_request_id
    op.create_index('ix_subscriptions_tranzak_request_id', 'subscriptions', ['tranzak_request_id'], unique=True)
    
    # Drop the old stripe_subscription_id column if it exists
    try:
        op.drop_column('subscriptions', 'stripe_subscription_id')
    except Exception:
        # Column might not exist, ignore error
        pass


def downgrade():
    # Add back stripe_subscription_id
    op.add_column('subscriptions', sa.Column('stripe_subscription_id', sa.String(255), nullable=True))
    
    # Create unique index for stripe_subscription_id
    op.create_index('ix_subscriptions_stripe_subscription_id', 'subscriptions', ['stripe_subscription_id'], unique=True)
    
    # Drop tranzak_request_id
    try:
        op.drop_index('ix_subscriptions_tranzak_request_id')
        op.drop_column('subscriptions', 'tranzak_request_id')
    except Exception:
        pass