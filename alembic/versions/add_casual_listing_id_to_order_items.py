"""Add casual_listing_id to order_items table

Revision ID: add_casual_listing_id_order_items
Revises: update_subscription_for_tranzak
Create Date: 2025-11-16 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_casual_listing_id_order_items'
down_revision = 'update_subscription_for_tranzak'
branch_labels = None
depends_on = None


def upgrade():
    # Make product_id nullable
    op.alter_column('order_items', 'product_id',
               existing_type=sa.String(),
               nullable=True)

    # Add casual_listing_id column
    op.add_column('order_items',
        sa.Column('casual_listing_id', sa.String(), nullable=True)
    )

    # Create foreign key constraint to casual_listings table
    op.create_foreign_key(
        'fk_order_items_casual_listing_id',
        'order_items', 'casual_listings',
        ['casual_listing_id'], ['id']
    )

    # Create index on casual_listing_id
    op.create_index(
        'ix_order_items_casual_listing_id',
        'order_items',
        ['casual_listing_id']
    )


def downgrade():
    # Drop index
    op.drop_index('ix_order_items_casual_listing_id', table_name='order_items')

    # Drop foreign key constraint
    op.drop_constraint('fk_order_items_casual_listing_id', 'order_items', type_='foreignkey')

    # Drop column
    op.drop_column('order_items', 'casual_listing_id')

    # Make product_id non-nullable again
    op.alter_column('order_items', 'product_id',
               existing_type=sa.String(),
               nullable=False)
