"""Add multi-role system tables

Revision ID: add_multi_role_system
Revises: 
Create Date: 2025-09-01 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_multi_role_system'
down_revision = None  # Update this with the latest revision
branch_labels = None
depends_on = None


def upgrade():
    # Add subscription tracking fields to users table
    op.add_column('users', sa.Column('subscription_status', sa.String(20), nullable=False, server_default='free'))
    op.add_column('users', sa.Column('subscription_expires_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('users', sa.Column('role_upgraded_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('users', sa.Column('monthly_revenue', sa.DECIMAL(10,2), nullable=False, server_default='0'))
    
    # Create subscriptions table
    op.create_table('subscriptions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('plan_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('current_period_start', sa.TIMESTAMP(), nullable=False),
        sa.Column('current_period_end', sa.TIMESTAMP(), nullable=False),
        sa.Column('monthly_fee', sa.DECIMAL(10,2), nullable=False),
        sa.Column('trial_ends_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.UniqueConstraint('stripe_subscription_id')
    )
    op.create_index('ix_subscriptions_user_id', 'subscriptions', ['user_id'])
    op.create_index('ix_subscriptions_status', 'subscriptions', ['status'])
    
    # Create casual_listings table (separate from shops)
    op.create_table('casual_listings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('seller_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price', sa.DECIMAL(10,2), nullable=False),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('condition', sa.String(50), nullable=True),
        sa.Column('images', sa.JSON(), nullable=True),
        sa.Column('location', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('is_promoted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('views_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['seller_id'], ['users.id'], )
    )
    op.create_index('ix_casual_listings_seller_id', 'casual_listings', ['seller_id'])
    op.create_index('ix_casual_listings_status', 'casual_listings', ['status'])
    op.create_index('ix_casual_listings_category', 'casual_listings', ['category'])
    op.create_index('ix_casual_listings_created_at', 'casual_listings', ['created_at'])
    
    # Create delivery_agents table
    op.create_table('delivery_agents',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('vehicle_type', sa.String(50), nullable=True),
        sa.Column('license_number', sa.String(100), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('availability_schedule', sa.JSON(), nullable=True),
        sa.Column('current_status', sa.String(20), nullable=False, server_default='offline'),
        sa.Column('current_location', sa.String(255), nullable=True), # For GPS coordinates
        sa.Column('rating', sa.DECIMAL(3,2), nullable=False, server_default='5.0'),
        sa.Column('total_deliveries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('earnings_this_month', sa.DECIMAL(10,2), nullable=False, server_default='0'),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], )
    )
    op.create_index('ix_delivery_agents_user_id', 'delivery_agents', ['user_id'])
    op.create_index('ix_delivery_agents_current_status', 'delivery_agents', ['current_status'])
    op.create_index('ix_delivery_agents_rating', 'delivery_agents', ['rating'])
    
    # Create delivery_assignments table
    op.create_table('delivery_assignments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('order_id', sa.String(), nullable=False),
        sa.Column('agent_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='assigned'),
        sa.Column('pickup_location', sa.String(255), nullable=True),
        sa.Column('delivery_location', sa.String(255), nullable=True),
        sa.Column('estimated_distance', sa.DECIMAL(5,2), nullable=True), # in km
        sa.Column('delivery_fee', sa.DECIMAL(10,2), nullable=True),
        sa.Column('agent_earnings', sa.DECIMAL(10,2), nullable=True),
        sa.Column('assigned_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('picked_up_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('delivered_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['agent_id'], ['delivery_agents.id'], ),
        # Note: order_id will reference orders table when it's created
    )
    op.create_index('ix_delivery_assignments_agent_id', 'delivery_assignments', ['agent_id'])
    op.create_index('ix_delivery_assignments_status', 'delivery_assignments', ['status'])
    op.create_index('ix_delivery_assignments_assigned_at', 'delivery_assignments', ['assigned_at'])
    
    # Create transaction_fees table for revenue tracking
    op.create_table('transaction_fees',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('order_id', sa.String(), nullable=True),
        sa.Column('listing_id', sa.String(), nullable=True),
        sa.Column('fee_type', sa.String(50), nullable=False), # 'casual_seller', 'shop_owner', 'delivery'
        sa.Column('fee_percentage', sa.DECIMAL(5,2), nullable=False),
        sa.Column('fee_amount', sa.DECIMAL(10,2), nullable=False),
        sa.Column('platform_revenue', sa.DECIMAL(10,2), nullable=False),
        sa.Column('transaction_amount', sa.DECIMAL(10,2), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], )
    )
    op.create_index('ix_transaction_fees_user_id', 'transaction_fees', ['user_id'])
    op.create_index('ix_transaction_fees_fee_type', 'transaction_fees', ['fee_type'])
    op.create_index('ix_transaction_fees_created_at', 'transaction_fees', ['created_at'])
    
    # Create user_metrics table for analytics and upgrade prompts
    op.create_table('user_metrics',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('total_purchases', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('monthly_purchases', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_spent', sa.DECIMAL(10,2), nullable=False, server_default='0'),
        sa.Column('monthly_spent', sa.DECIMAL(10,2), nullable=False, server_default='0'),
        sa.Column('total_listings', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_sales', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('page_views', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('time_spent_minutes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_upgrade_prompt', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.UniqueConstraint('user_id')
    )
    op.create_index('ix_user_metrics_user_id', 'user_metrics', ['user_id'])
    

def downgrade():
    # Drop created tables
    op.drop_table('user_metrics')
    op.drop_table('transaction_fees')
    op.drop_table('delivery_assignments')
    op.drop_table('delivery_agents')
    op.drop_table('casual_listings')
    op.drop_table('subscriptions')
    
    # Drop added columns from users table
    op.drop_column('users', 'monthly_revenue')
    op.drop_column('users', 'role_upgraded_at')
    op.drop_column('users', 'subscription_expires_at')
    op.drop_column('users', 'subscription_status')