"""Add order status history tracking

Revision ID: add_order_status_history
Revises:
Create Date: 2024-09-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_order_status_history'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create order_status_history table
    op.create_table('order_status_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('order_id', sa.String(), nullable=False),
        sa.Column('old_status', sa.String(50), nullable=True),
        sa.Column('new_status', sa.String(50), nullable=False),
        sa.Column('changed_by', sa.String(), nullable=True),
        sa.Column('changed_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_order_status_history_order_id', 'order_id'),
        sa.Index('ix_order_status_history_changed_at', 'changed_at')
    )

    # Add new columns to orders table
    op.add_column('orders', sa.Column('estimated_delivery_date', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('carrier', sa.String(100), nullable=True))
    op.add_column('orders', sa.Column('delivery_instructions', sa.Text(), nullable=True))
    op.add_column('orders', sa.Column('status_updated_at', sa.DateTime(), nullable=True))

    # Create index for faster status queries
    op.create_index('ix_orders_status_updated_at', 'orders', ['status_updated_at'])


def downgrade():
    # Remove indexes
    op.drop_index('ix_orders_status_updated_at', table_name='orders')

    # Remove columns from orders table
    op.drop_column('orders', 'status_updated_at')
    op.drop_column('orders', 'delivery_instructions')
    op.drop_column('orders', 'carrier')
    op.drop_column('orders', 'estimated_delivery_date')

    # Drop order_status_history table
    op.drop_table('order_status_history')