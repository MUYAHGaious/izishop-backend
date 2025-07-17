#!/usr/bin/env python3
"""
Seed script to populate the database with sample data
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.models.user import db, User
from src.models.product import Product, Shop, Review, CartItem
from flask import Flask
from datetime import datetime, timedelta
import random

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

def seed_users():
    """Create sample users"""
    users = [
        {
            'name': 'John Doe',
            'email': 'john@example.com',
            'password': 'password123'
        },
        {
            'name': 'Jane Smith',
            'email': 'jane@example.com',
            'password': 'password123'
        },
        {
            'name': 'Admin User',
            'email': 'admin@izishop.cm',
            'password': 'admin123'
        }
    ]
    
    for user_data in users:
        existing_user = User.query.filter_by(email=user_data['email']).first()
        if not existing_user:
            user = User(
                name=user_data['name'],
                email=user_data['email']
            )
            user.set_password(user_data['password'])
            db.session.add(user)
    
    db.session.commit()
    print("✓ Users seeded")

def seed_shops():
    """Create sample shops"""
    shops = [
        {
            'name': 'TechHub Electronics',
            'description': 'Premier electronics store with latest gadgets and competitive prices',
            'category': 'Electronics',
            'contact_email': 'contact@techhub.cm',
            'contact_phone': '+237 6XX XXX XXX',
            'address': 'Douala, Cameroon',
            'is_verified': True,
            'rating': 4.8
        },
        {
            'name': 'SportZone Douala',
            'description': 'Your one-stop shop for all sporting goods and equipment',
            'category': 'Sports',
            'contact_email': 'info@sportzone.cm',
            'contact_phone': '+237 6XX XXX XXX',
            'address': 'Douala, Cameroon',
            'is_verified': True,
            'rating': 4.6
        },
        {
            'name': 'Fashion Forward',
            'description': 'Trendy fashion and clothing for men and women',
            'category': 'Fashion',
            'contact_email': 'hello@fashionforward.cm',
            'contact_phone': '+237 6XX XXX XXX',
            'address': 'Yaoundé, Cameroon',
            'is_verified': False,
            'rating': 4.3
        },
        {
            'name': 'Home & Garden Paradise',
            'description': 'Everything you need for your home and garden',
            'category': 'Home & Garden',
            'contact_email': 'support@homegarden.cm',
            'contact_phone': '+237 6XX XXX XXX',
            'address': 'Bamenda, Cameroon',
            'is_verified': True,
            'rating': 4.5
        }
    ]
    
    for shop_data in shops:
        existing_shop = Shop.query.filter_by(name=shop_data['name']).first()
        if not existing_shop:
            shop = Shop(**shop_data)
            db.session.add(shop)
    
    db.session.commit()
    print("✓ Shops seeded")

def seed_products():
    """Create sample products"""
    shops = Shop.query.all()
    
    products = [
        # Electronics
        {
            'name': 'Samsung Galaxy S24 Ultra 256GB',
            'description': 'Latest Samsung flagship smartphone with advanced camera system and S Pen',
            'price': 850000,
            'original_price': 950000,
            'category': 'Electronics',
            'brand': 'Samsung',
            'stock': 15,
            'images': ['https://images.unsplash.com/photo-1610945265064-0e34e5519bbf?w=400&h=400&fit=crop'],
            'shop_name': 'TechHub Electronics',
            'is_featured': True,
            'rating': 4.8
        },
        {
            'name': 'Apple MacBook Pro 14-inch M3',
            'description': 'Powerful laptop for professionals with M3 chip and Retina display',
            'price': 1250000,
            'original_price': 1350000,
            'category': 'Electronics',
            'brand': 'Apple',
            'stock': 8,
            'images': ['https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400&h=400&fit=crop'],
            'shop_name': 'TechHub Electronics',
            'is_featured': True,
            'rating': 4.9
        },
        {
            'name': 'Sony WH-1000XM5 Headphones',
            'description': 'Industry-leading noise canceling wireless headphones',
            'price': 285000,
            'original_price': 320000,
            'category': 'Electronics',
            'brand': 'Sony',
            'stock': 25,
            'images': ['https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400&h=400&fit=crop'],
            'shop_name': 'TechHub Electronics',
            'rating': 4.7
        },
        
        # Sports
        {
            'name': 'Nike Air Max 270 Running Shoes',
            'description': 'Comfortable running shoes with Max Air cushioning',
            'price': 125000,
            'category': 'Sports',
            'brand': 'Nike',
            'stock': 30,
            'images': ['https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop'],
            'shop_name': 'SportZone Douala',
            'rating': 4.6
        },
        {
            'name': 'Adidas Ultraboost 22 Black',
            'description': 'Premium running shoes with Boost technology',
            'price': 95000,
            'original_price': 110000,
            'category': 'Sports',
            'brand': 'Adidas',
            'stock': 20,
            'images': ['https://images.unsplash.com/photo-1595950653106-6c9ebd614d3a?w=400&h=400&fit=crop'],
            'shop_name': 'SportZone Douala',
            'rating': 4.5
        },
        {
            'name': 'Professional Basketball',
            'description': 'Official size basketball for indoor and outdoor play',
            'price': 35000,
            'category': 'Sports',
            'brand': 'Spalding',
            'stock': 50,
            'images': ['https://images.unsplash.com/photo-1546519638-68e109498ffc?w=400&h=400&fit=crop'],
            'shop_name': 'SportZone Douala',
            'rating': 4.4
        },
        
        # Fashion
        {
            'name': 'Designer Cotton T-Shirt',
            'description': 'Premium quality cotton t-shirt with modern fit',
            'price': 25000,
            'category': 'Fashion',
            'brand': 'Local Brand',
            'stock': 100,
            'images': ['https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=400&fit=crop'],
            'shop_name': 'Fashion Forward',
            'rating': 4.2
        },
        {
            'name': 'Leather Handbag',
            'description': 'Elegant leather handbag perfect for any occasion',
            'price': 85000,
            'original_price': 100000,
            'category': 'Fashion',
            'brand': 'Fashion Forward',
            'stock': 15,
            'images': ['https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=400&h=400&fit=crop'],
            'shop_name': 'Fashion Forward',
            'rating': 4.3
        },
        
        # Home & Garden
        {
            'name': 'Indoor Plant Collection',
            'description': 'Set of 3 beautiful indoor plants to brighten your home',
            'price': 45000,
            'category': 'Home & Garden',
            'brand': 'Green Life',
            'stock': 25,
            'images': ['https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=400&h=400&fit=crop'],
            'shop_name': 'Home & Garden Paradise',
            'rating': 4.6
        },
        {
            'name': 'Modern Table Lamp',
            'description': 'Stylish table lamp with adjustable brightness',
            'price': 65000,
            'category': 'Home & Garden',
            'brand': 'Home Decor',
            'stock': 12,
            'images': ['https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&h=400&fit=crop'],
            'shop_name': 'Home & Garden Paradise',
            'rating': 4.4
        }
    ]
    
    for product_data in products:
        shop = Shop.query.filter_by(name=product_data['shop_name']).first()
        if shop:
            existing_product = Product.query.filter_by(name=product_data['name']).first()
            if not existing_product:
                product_data['shop_id'] = shop.id
                product_data['image_list'] = product_data.pop('images')
                product_data.pop('shop_name')
                
                product = Product(**product_data)
                db.session.add(product)
    
    db.session.commit()
    print("✓ Products seeded")

def seed_reviews():
    """Create sample reviews"""
    users = User.query.all()
    products = Product.query.all()
    
    if not users or not products:
        print("⚠ Skipping reviews - no users or products found")
        return
    
    # Create some sample reviews
    sample_reviews = [
        "Great product! Exactly as described and fast delivery.",
        "Good quality for the price. Would recommend.",
        "Excellent customer service and product quality.",
        "Fast shipping and well packaged. Very satisfied.",
        "Amazing product! Exceeded my expectations.",
        "Good value for money. Will buy again.",
        "Perfect! Just what I was looking for.",
        "High quality product. Very happy with purchase."
    ]
    
    for product in products[:5]:  # Add reviews to first 5 products
        num_reviews = random.randint(3, 8)
        for _ in range(num_reviews):
            user = random.choice(users)
            
            # Check if user already reviewed this product
            existing_review = Review.query.filter_by(
                product_id=product.id,
                user_id=user.id
            ).first()
            
            if not existing_review:
                review = Review(
                    product_id=product.id,
                    user_id=user.id,
                    rating=random.randint(4, 5),
                    comment=random.choice(sample_reviews),
                    created_at=datetime.utcnow() - timedelta(days=random.randint(1, 30))
                )
                db.session.add(review)
        
        # Update product rating and review count
        reviews = Review.query.filter_by(product_id=product.id).all()
        if reviews:
            avg_rating = sum(r.rating for r in reviews) / len(reviews)
            product.rating = round(avg_rating, 1)
            product.review_count = len(reviews)
    
    db.session.commit()
    print("✓ Reviews seeded")

def main():
    """Main seeding function"""
    app = create_app()
    
    with app.app_context():
        print("🌱 Starting database seeding...")
        
        # Create all tables
        db.create_all()
        
        # Seed data
        seed_users()
        seed_shops()
        seed_products()
        seed_reviews()
        
        print("✅ Database seeding completed successfully!")

if __name__ == '__main__':
    main()

