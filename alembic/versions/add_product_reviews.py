"""Add product reviews table

Revision ID: add_product_reviews
Revises: add_rating_system
Create Date: 2025-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_product_reviews'
down_revision = 'add_rating_system'
branch_labels = None
depends_on = None


def upgrade():
    # Create product_reviews table
    op.create_table('product_reviews',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('product_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('is_verified_purchase', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('helpful_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for better performance
    op.create_index(op.f('ix_product_reviews_id'), 'product_reviews', ['id'], unique=False)
    op.create_index(op.f('ix_product_reviews_product_id'), 'product_reviews', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_reviews_user_id'), 'product_reviews', ['user_id'], unique=False)
    op.create_index(op.f('ix_product_reviews_rating'), 'product_reviews', ['rating'], unique=False)
    op.create_index(op.f('ix_product_reviews_created_at'), 'product_reviews', ['created_at'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index(op.f('ix_product_reviews_created_at'), table_name='product_reviews')
    op.drop_index(op.f('ix_product_reviews_rating'), table_name='product_reviews')
    op.drop_index(op.f('ix_product_reviews_user_id'), table_name='product_reviews')
    op.drop_index(op.f('ix_product_reviews_product_id'), table_name='product_reviews')
    op.drop_index(op.f('ix_product_reviews_id'), table_name='product_reviews')
    
    # Drop table
    op.drop_table('product_reviews')
