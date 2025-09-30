"""Add order cancellation system

Revision ID: add_order_cancellation_system
Revises:
Create Date: 2025-01-09 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_order_cancellation_system'
down_revision = 'update_subscription_for_tranzak'
branch_labels = None
depends_on = None

def upgrade():
    """Add order cancellation system tables and fields"""

    # Create cancellation reason enum
    cancellation_reason_enum = postgresql.ENUM(
        'customer_request',
        'payment_failed',
        'inventory_unavailable',
        'shipping_issues',
        'duplicate_order',
        'pricing_error',
        'customer_changed_mind',
        'wrong_item_ordered',
        'delivery_issues',
        'other',
        name='cancellationreason'
    )
    cancellation_reason_enum.create(op.get_bind())

    # Create refund status enum
    refund_status_enum = postgresql.ENUM(
        'pending',
        'processing',
        'completed',
        'failed',
        'cancelled',
        name='refundstatus'
    )
    refund_status_enum.create(op.get_bind())

    # Add cancellation fields to orders table
    op.add_column('orders', sa.Column('cancelled_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('cancellation_reason', sa.String(length=100), nullable=True))
    op.add_column('orders', sa.Column('can_be_cancelled', sa.Boolean(), nullable=False, server_default='true'))

    # Create order_cancellations table
    op.create_table('order_cancellations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('order_id', sa.String(), nullable=False),
        sa.Column('cancelled_by', sa.String(), nullable=False),
        sa.Column('reason', cancellation_reason_enum, nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(), nullable=False),
        sa.Column('refund_requested', sa.Boolean(), nullable=False),
        sa.Column('refund_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('refund_status', refund_status_enum, nullable=True),
        sa.Column('refund_reference', sa.String(length=100), nullable=True),
        sa.Column('items_restocked', sa.Boolean(), nullable=False),
        sa.Column('restock_completed_at', sa.DateTime(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('processing_notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['cancelled_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for better performance
    op.create_index('ix_order_cancellations_id', 'order_cancellations', ['id'])
    op.create_index('ix_order_cancellations_order_id', 'order_cancellations', ['order_id'])
    op.create_index('ix_order_cancellations_cancelled_by', 'order_cancellations', ['cancelled_by'])

def downgrade():
    """Remove order cancellation system"""

    # Drop indexes
    op.drop_index('ix_order_cancellations_cancelled_by', 'order_cancellations')
    op.drop_index('ix_order_cancellations_order_id', 'order_cancellations')
    op.drop_index('ix_order_cancellations_id', 'order_cancellations')

    # Drop table
    op.drop_table('order_cancellations')

    # Remove columns from orders table
    op.drop_column('orders', 'can_be_cancelled')
    op.drop_column('orders', 'cancellation_reason')
    op.drop_column('orders', 'cancelled_at')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS refundstatus')
    op.execute('DROP TYPE IF EXISTS cancellationreason')