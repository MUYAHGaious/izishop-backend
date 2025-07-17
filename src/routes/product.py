from flask import Blueprint, request, jsonify
from src.models.product import db, Product, Shop, Review, CartItem
from src.models.user import User
from sqlalchemy import or_, and_

product_bp = Blueprint('product', __name__)

@product_bp.route('/products', methods=['GET'])
def get_products():
    """Get products with filtering, sorting, and pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        category = request.args.get('category')
        brand = request.args.get('brand')
        min_price = request.args.get('min_price', type=float)
        max_price = request.args.get('max_price', type=float)
        search = request.args.get('search')
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')
        
        # Build query
        query = Product.query.filter_by(is_active=True)
        
        # Apply filters
        if category:
            query = query.filter(Product.category == category)
        
        if brand:
            query = query.filter(Product.brand == brand)
        
        if min_price is not None:
            query = query.filter(Product.price >= min_price)
        
        if max_price is not None:
            query = query.filter(Product.price <= max_price)
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Product.name.ilike(search_term),
                    Product.description.ilike(search_term),
                    Product.brand.ilike(search_term)
                )
            )
        
        # Apply sorting
        if sort_by == 'price':
            if sort_order == 'asc':
                query = query.order_by(Product.price.asc())
            else:
                query = query.order_by(Product.price.desc())
        elif sort_by == 'rating':
            query = query.order_by(Product.rating.desc())
        elif sort_by == 'name':
            if sort_order == 'asc':
                query = query.order_by(Product.name.asc())
            else:
                query = query.order_by(Product.name.desc())
        else:  # created_at
            if sort_order == 'asc':
                query = query.order_by(Product.created_at.asc())
            else:
                query = query.order_by(Product.created_at.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        products = [product.to_dict() for product in pagination.items]
        
        return jsonify({
            'success': True,
            'products': products,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@product_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """Get a single product by ID"""
    try:
        product = Product.query.get_or_404(product_id)
        
        if not product.is_active:
            return jsonify({'success': False, 'error': 'Product not found'}), 404
        
        return jsonify({
            'success': True,
            'product': product.to_dict()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@product_bp.route('/products', methods=['POST'])
def create_product():
    """Create a new product"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'price', 'category', 'shop_id']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        
        # Check if shop exists
        shop = Shop.query.get(data['shop_id'])
        if not shop:
            return jsonify({'success': False, 'error': 'Shop not found'}), 404
        
        product = Product(
            name=data['name'],
            description=data.get('description'),
            price=data['price'],
            original_price=data.get('original_price'),
            category=data['category'],
            brand=data.get('brand'),
            stock=data.get('stock', 0),
            shop_id=data['shop_id'],
            is_featured=data.get('is_featured', False)
        )
        
        # Handle images
        if 'images' in data:
            product.image_list = data['images']
        
        db.session.add(product)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'product': product.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@product_bp.route('/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    """Update a product"""
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json()
        
        # Update fields
        updatable_fields = ['name', 'description', 'price', 'original_price', 
                           'category', 'brand', 'stock', 'is_featured', 'is_active']
        
        for field in updatable_fields:
            if field in data:
                setattr(product, field, data[field])
        
        # Handle images
        if 'images' in data:
            product.image_list = data['images']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'product': product.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@product_bp.route('/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    """Delete a product (soft delete)"""
    try:
        product = Product.query.get_or_404(product_id)
        product.is_active = False
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Product deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@product_bp.route('/products/<int:product_id>/reviews', methods=['GET'])
def get_product_reviews(product_id):
    """Get reviews for a product"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        product = Product.query.get_or_404(product_id)
        
        pagination = Review.query.filter_by(product_id=product_id)\
            .order_by(Review.created_at.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)
        
        reviews = [review.to_dict() for review in pagination.items]
        
        return jsonify({
            'success': True,
            'reviews': reviews,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@product_bp.route('/products/<int:product_id>/reviews', methods=['POST'])
def create_review():
    """Create a review for a product"""
    try:
        data = request.get_json()
        product_id = request.view_args['product_id']
        
        # Validate required fields
        required_fields = ['user_id', 'rating']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        
        # Validate rating
        if not (1 <= data['rating'] <= 5):
            return jsonify({'success': False, 'error': 'Rating must be between 1 and 5'}), 400
        
        # Check if product exists
        product = Product.query.get_or_404(product_id)
        
        # Check if user exists
        user = User.query.get(data['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Check if user already reviewed this product
        existing_review = Review.query.filter_by(
            product_id=product_id, 
            user_id=data['user_id']
        ).first()
        
        if existing_review:
            return jsonify({'success': False, 'error': 'You have already reviewed this product'}), 400
        
        review = Review(
            product_id=product_id,
            user_id=data['user_id'],
            rating=data['rating'],
            comment=data.get('comment')
        )
        
        db.session.add(review)
        
        # Update product rating
        reviews = Review.query.filter_by(product_id=product_id).all()
        if reviews:
            avg_rating = sum(r.rating for r in reviews) / len(reviews)
            product.rating = round(avg_rating, 1)
            product.review_count = len(reviews)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'review': review.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@product_bp.route('/categories', methods=['GET'])
def get_categories():
    """Get all product categories"""
    try:
        categories = db.session.query(Product.category)\
            .filter(Product.is_active == True)\
            .distinct()\
            .all()
        
        category_list = [cat[0] for cat in categories if cat[0]]
        
        return jsonify({
            'success': True,
            'categories': category_list
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@product_bp.route('/brands', methods=['GET'])
def get_brands():
    """Get all product brands"""
    try:
        brands = db.session.query(Product.brand)\
            .filter(and_(Product.is_active == True, Product.brand.isnot(None)))\
            .distinct()\
            .all()
        
        brand_list = [brand[0] for brand in brands if brand[0]]
        
        return jsonify({
            'success': True,
            'brands': brand_list
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

