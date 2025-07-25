"""Add rating and review system

Revision ID: add_rating_system
Revises: 83343540558f_initial_tables
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'add_rating_system'
down_revision = '83343540558f_initial_tables'
branch_labels = None
depends_on = None

def upgrade():
    # Add rating columns to shops table
    op.add_column('shops', sa.Column('average_rating', sa.Float(), default=0.0))
    op.add_column('shops', sa.Column('total_reviews', sa.Integer(), default=0))
    
    # Create ratings table
    op.create_table('ratings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('shop_id', sa.String(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('review', sa.Text(), nullable=True),
        sa.Column('is_verified_purchase', sa.Boolean(), default=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_flagged', sa.Boolean(), default=False),
        sa.Column('helpful_count', sa.Integer(), default=0),
        sa.Column('not_helpful_count', sa.Integer(), default=0),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ),
        sa.UniqueConstraint('user_id', 'shop_id', name='unique_user_shop_rating')
    )
    op.create_index(op.f('ix_ratings_id'), 'ratings', ['id'], unique=False)
    op.create_index(op.f('ix_ratings_shop_id'), 'ratings', ['shop_id'], unique=False)
    op.create_index(op.f('ix_ratings_user_id'), 'ratings', ['user_id'], unique=False)
    op.create_index(op.f('ix_ratings_rating'), 'ratings', ['rating'], unique=False)
    op.create_index(op.f('ix_ratings_created_at'), 'ratings', ['created_at'], unique=False)
    
    # Create rating helpfulness table
    op.create_table('rating_helpfulness',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('rating_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('is_helpful', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['rating_id'], ['ratings.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.UniqueConstraint('rating_id', 'user_id', name='unique_user_rating_helpfulness')
    )
    op.create_index(op.f('ix_rating_helpfulness_id'), 'rating_helpfulness', ['id'], unique=False)
    
    # Create rating flags table
    op.create_table('rating_flags',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('rating_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), default=False),
        sa.Column('admin_action', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['rating_id'], ['ratings.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.UniqueConstraint('rating_id', 'user_id', name='unique_user_rating_flag')
    )
    op.create_index(op.f('ix_rating_flags_id'), 'rating_flags', ['id'], unique=False)
    
    # Create shop stats table
    op.create_table('shop_stats',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('shop_id', sa.String(), nullable=False),
        sa.Column('average_rating', sa.Float(), default=0.0),
        sa.Column('total_reviews', sa.Integer(), default=0),
        sa.Column('total_orders', sa.Integer(), default=0),
        sa.Column('total_products', sa.Integer(), default=0),
        sa.Column('total_sales', sa.Float(), default=0.0),
        sa.Column('response_rate', sa.Float(), default=0.0),
        sa.Column('response_time_hours', sa.Float(), default=0.0),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ),
        sa.UniqueConstraint('shop_id', name='unique_shop_stats')
    )
    op.create_index(op.f('ix_shop_stats_id'), 'shop_stats', ['id'], unique=False)
    op.create_index(op.f('ix_shop_stats_shop_id'), 'shop_stats', ['shop_id'], unique=True)

def downgrade():
    # Drop indexes and tables in reverse order
    op.drop_index(op.f('ix_shop_stats_shop_id'), table_name='shop_stats')
    op.drop_index(op.f('ix_shop_stats_id'), table_name='shop_stats')
    op.drop_table('shop_stats')
    
    op.drop_index(op.f('ix_rating_flags_id'), table_name='rating_flags')
    op.drop_table('rating_flags')
    
    op.drop_index(op.f('ix_rating_helpfulness_id'), table_name='rating_helpfulness')
    op.drop_table('rating_helpfulness')
    
    op.drop_index(op.f('ix_ratings_created_at'), table_name='ratings')
    op.drop_index(op.f('ix_ratings_rating'), table_name='ratings')
    op.drop_index(op.f('ix_ratings_user_id'), table_name='ratings')
    op.drop_index(op.f('ix_ratings_shop_id'), table_name='ratings')
    op.drop_index(op.f('ix_ratings_id'), table_name='ratings')
    op.drop_table('ratings')
    
    # Remove columns from shops table
    op.drop_column('shops', 'total_reviews')
    op.drop_column('shops', 'average_rating')