from flask import Blueprint, request, jsonify
from src.models.product import db, CartItem, Product
from src.models.user import User

cart_bp = Blueprint('cart', __name__)

@cart_bp.route('/cart/<int:user_id>', methods=['GET'])
def get_cart(user_id):
    """Get user's cart items"""
    try:
        # Check if user exists
        user = User.query.get_or_404(user_id)
        
        cart_items = CartItem.query.filter_by(user_id=user_id)\
            .join(Product)\
            .filter(Product.is_active == True)\
            .all()
        
        items = [item.to_dict() for item in cart_items]
        
        # Calculate totals
        subtotal = sum(item['product']['price'] * item['quantity'] for item in items)
        total_items = sum(item['quantity'] for item in items)
        
        return jsonify({
            'success': True,
            'cart': {
                'user_id': user_id,
                'items': items,
                'subtotal': subtotal,
                'total_items': total_items
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@cart_bp.route('/cart', methods=['POST'])
def add_to_cart():
    """Add item to cart"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['user_id', 'product_id', 'quantity']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        
        # Validate quantity
        if data['quantity'] <= 0:
            return jsonify({'success': False, 'error': 'Quantity must be greater than 0'}), 400
        
        # Check if user exists
        user = User.query.get(data['user_id'])
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Check if product exists and is active
        product = Product.query.get(data['product_id'])
        if not product or not product.is_active:
            return jsonify({'success': False, 'error': 'Product not found'}), 404
        
        # Check stock availability
        if product.stock < data['quantity']:
            return jsonify({'success': False, 'error': 'Insufficient stock'}), 400
        
        # Check if item already exists in cart
        existing_item = CartItem.query.filter_by(
            user_id=data['user_id'],
            product_id=data['product_id']
        ).first()
        
        if existing_item:
            # Update quantity
            new_quantity = existing_item.quantity + data['quantity']
            if product.stock < new_quantity:
                return jsonify({'success': False, 'error': 'Insufficient stock'}), 400
            
            existing_item.quantity = new_quantity
            db.session.commit()
            
            return jsonify({
                'success': True,
                'cart_item': existing_item.to_dict(),
                'message': 'Cart updated successfully'
            })
        else:
            # Create new cart item
            cart_item = CartItem(
                user_id=data['user_id'],
                product_id=data['product_id'],
                quantity=data['quantity']
            )
            
            db.session.add(cart_item)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'cart_item': cart_item.to_dict(),
                'message': 'Item added to cart successfully'
            }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@cart_bp.route('/cart/<int:cart_item_id>', methods=['PUT'])
def update_cart_item(cart_item_id):
    """Update cart item quantity"""
    try:
        cart_item = CartItem.query.get_or_404(cart_item_id)
        data = request.get_json()
        
        if 'quantity' not in data:
            return jsonify({'success': False, 'error': 'Quantity is required'}), 400
        
        quantity = data['quantity']
        
        if quantity <= 0:
            return jsonify({'success': False, 'error': 'Quantity must be greater than 0'}), 400
        
        # Check stock availability
        if cart_item.product.stock < quantity:
            return jsonify({'success': False, 'error': 'Insufficient stock'}), 400
        
        cart_item.quantity = quantity
        db.session.commit()
        
        return jsonify({
            'success': True,
            'cart_item': cart_item.to_dict(),
            'message': 'Cart item updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@cart_bp.route('/cart/<int:cart_item_id>', methods=['DELETE'])
def remove_from_cart(cart_item_id):
    """Remove item from cart"""
    try:
        cart_item = CartItem.query.get_or_404(cart_item_id)
        
        db.session.delete(cart_item)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Item removed from cart successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@cart_bp.route('/cart/<int:user_id>/clear', methods=['DELETE'])
def clear_cart(user_id):
    """Clear all items from user's cart"""
    try:
        # Check if user exists
        user = User.query.get_or_404(user_id)
        
        CartItem.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Cart cleared successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@cart_bp.route('/cart/<int:user_id>/count', methods=['GET'])
def get_cart_count(user_id):
    """Get total number of items in user's cart"""
    try:
        # Check if user exists
        user = User.query.get_or_404(user_id)
        
        total_items = db.session.query(db.func.sum(CartItem.quantity))\
            .filter_by(user_id=user_id)\
            .join(Product)\
            .filter(Product.is_active == True)\
            .scalar() or 0
        
        return jsonify({
            'success': True,
            'count': total_items
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

