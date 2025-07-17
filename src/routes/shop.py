from flask import Blueprint, request, jsonify
from src.models.product import db, Shop, Product
from sqlalchemy import or_

shop_bp = Blueprint('shop', __name__)

@shop_bp.route('/shops', methods=['GET'])
def get_shops():
    """Get shops with filtering, sorting, and pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        category = request.args.get('category')
        search = request.args.get('search')
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')
        verified_only = request.args.get('verified_only', type=bool)
        
        # Build query
        query = Shop.query.filter_by(is_active=True)
        
        # Apply filters
        if category:
            query = query.filter(Shop.category == category)
        
        if verified_only:
            query = query.filter(Shop.is_verified == True)
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Shop.name.ilike(search_term),
                    Shop.description.ilike(search_term),
                    Shop.category.ilike(search_term)
                )
            )
        
        # Apply sorting
        if sort_by == 'rating':
            query = query.order_by(Shop.rating.desc())
        elif sort_by == 'name':
            if sort_order == 'asc':
                query = query.order_by(Shop.name.asc())
            else:
                query = query.order_by(Shop.name.desc())
        else:  # created_at
            if sort_order == 'asc':
                query = query.order_by(Shop.created_at.asc())
            else:
                query = query.order_by(Shop.created_at.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        shops = [shop.to_dict() for shop in pagination.items]
        
        return jsonify({
            'success': True,
            'shops': shops,
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

@shop_bp.route('/shops/<int:shop_id>', methods=['GET'])
def get_shop(shop_id):
    """Get a single shop by ID"""
    try:
        shop = Shop.query.get_or_404(shop_id)
        
        if not shop.is_active:
            return jsonify({'success': False, 'error': 'Shop not found'}), 404
        
        return jsonify({
            'success': True,
            'shop': shop.to_dict()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@shop_bp.route('/shops', methods=['POST'])
def create_shop():
    """Create a new shop"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'contact_email']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        
        # Check if shop name already exists
        existing_shop = Shop.query.filter_by(name=data['name']).first()
        if existing_shop:
            return jsonify({'success': False, 'error': 'Shop name already exists'}), 400
        
        shop = Shop(
            name=data['name'],
            description=data.get('description'),
            logo=data.get('logo'),
            banner=data.get('banner'),
            category=data.get('category'),
            contact_email=data['contact_email'],
            contact_phone=data.get('contact_phone'),
            address=data.get('address')
        )
        
        db.session.add(shop)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'shop': shop.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@shop_bp.route('/shops/<int:shop_id>', methods=['PUT'])
def update_shop(shop_id):
    """Update a shop"""
    try:
        shop = Shop.query.get_or_404(shop_id)
        data = request.get_json()
        
        # Update fields
        updatable_fields = ['name', 'description', 'logo', 'banner', 'category',
                           'contact_email', 'contact_phone', 'address', 'is_active']
        
        for field in updatable_fields:
            if field in data:
                setattr(shop, field, data[field])
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'shop': shop.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@shop_bp.route('/shops/<int:shop_id>', methods=['DELETE'])
def delete_shop(shop_id):
    """Delete a shop (soft delete)"""
    try:
        shop = Shop.query.get_or_404(shop_id)
        shop.is_active = False
        
        # Also deactivate all products from this shop
        Product.query.filter_by(shop_id=shop_id).update({'is_active': False})
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Shop deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@shop_bp.route('/shops/<int:shop_id>/products', methods=['GET'])
def get_shop_products(shop_id):
    """Get products for a specific shop"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        category = request.args.get('category')
        search = request.args.get('search')
        
        # Check if shop exists
        shop = Shop.query.get_or_404(shop_id)
        
        # Build query
        query = Product.query.filter_by(shop_id=shop_id, is_active=True)
        
        # Apply filters
        if category:
            query = query.filter(Product.category == category)
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Product.name.ilike(search_term),
                    Product.description.ilike(search_term),
                    Product.brand.ilike(search_term)
                )
            )
        
        # Order by created_at desc
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
            'shop': shop.to_dict(),
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

@shop_bp.route('/shop-categories', methods=['GET'])
def get_shop_categories():
    """Get all shop categories"""
    try:
        categories = db.session.query(Shop.category)\
            .filter(Shop.is_active == True)\
            .distinct()\
            .all()
        
        category_list = [cat[0] for cat in categories if cat[0]]
        
        return jsonify({
            'success': True,
            'categories': category_list
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

