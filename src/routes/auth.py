from flask import Blueprint, request, jsonify, session
from src.models.user import db, User
from werkzeug.security import check_password_hash
import os

auth_bp = Blueprint('auth', __name__)

# Admin credentials (in production, this should be in environment variables)
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

@auth_bp.route('/login', methods=['POST'])
def login():
    """User login"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('email') or not data.get('password'):
            return jsonify({'success': False, 'error': 'Email and password are required'}), 400
        
        # Find user by email
        user = User.query.filter_by(email=data['email']).first()
        
        if not user or not user.check_password(data['password']):
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        if not user.is_active:
            return jsonify({'success': False, 'error': 'Account is deactivated'}), 401
        
        # Store user session
        session['user_id'] = user.id
        session['user_email'] = user.email
        
        return jsonify({
            'success': True,
            'user': user.to_dict(),
            'message': 'Login successful'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@auth_bp.route('/register', methods=['POST'])
def register():
    """User registration"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=data['email']).first()
        if existing_user:
            return jsonify({'success': False, 'error': 'Email already registered'}), 400
        
        # Validate password length
        if len(data['password']) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters long'}), 400
        
        # Create new user
        user = User(
            name=data['name'],
            email=data['email']
        )
        user.set_password(data['password'])
        
        db.session.add(user)
        db.session.commit()
        
        # Store user session
        session['user_id'] = user.id
        session['user_email'] = user.email
        
        return jsonify({
            'success': True,
            'user': user.to_dict(),
            'message': 'Registration successful'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@auth_bp.route('/admin-login', methods=['POST'])
def admin_login():
    """Admin login"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('username') or not data.get('password'):
            return jsonify({'success': False, 'error': 'Username and password are required'}), 400
        
        # Check admin credentials
        if data['username'] != ADMIN_USERNAME or data['password'] != ADMIN_PASSWORD:
            return jsonify({'success': False, 'error': 'Invalid admin credentials'}), 401
        
        # Store admin session
        session['is_admin'] = True
        session['admin_username'] = data['username']
        
        return jsonify({
            'success': True,
            'admin': {
                'username': data['username'],
                'is_admin': True
            },
            'message': 'Admin login successful'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@auth_bp.route('/logout', methods=['POST'])
def logout():
    """User/Admin logout"""
    try:
        # Clear session
        session.clear()
        
        return jsonify({
            'success': True,
            'message': 'Logout successful'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    """Get current user info"""
    try:
        # Check if admin
        if session.get('is_admin'):
            return jsonify({
                'success': True,
                'user': {
                    'username': session.get('admin_username'),
                    'is_admin': True
                }
            })
        
        # Check if regular user
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user or not user.is_active:
            session.clear()
            return jsonify({'success': False, 'error': 'User not found or deactivated'}), 401
        
        return jsonify({
            'success': True,
            'user': user.to_dict()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@auth_bp.route('/check-admin', methods=['GET'])
def check_admin():
    """Check if current session is admin"""
    try:
        is_admin = session.get('is_admin', False)
        
        return jsonify({
            'success': True,
            'is_admin': is_admin
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

