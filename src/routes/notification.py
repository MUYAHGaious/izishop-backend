from flask import Blueprint, request, jsonify
from src.models.user import db
from datetime import datetime, timedelta
import json

notification_bp = Blueprint('notification', __name__)

# Mock notification data (in production, this would be stored in database)
MOCK_NOTIFICATIONS = [
    {
        'id': 1,
        'type': 'order',
        'title': 'New Order Received',
        'message': 'Order #ORD-2025-001 has been placed by Jean-Baptiste',
        'timestamp': datetime.utcnow() - timedelta(minutes=5),
        'read': False,
        'icon': 'Package'
    },
    {
        'id': 2,
        'type': 'payment',
        'title': 'Payment Confirmed',
        'message': 'Payment of 45,000 XAF has been confirmed for Order #ORD-2025-002',
        'timestamp': datetime.utcnow() - timedelta(minutes=15),
        'read': False,
        'icon': 'CreditCard'
    },
    {
        'id': 3,
        'type': 'delivery',
        'title': 'Delivery Update',
        'message': 'Your order is out for delivery and will arrive within 2 hours',
        'timestamp': datetime.utcnow() - timedelta(minutes=30),
        'read': True,
        'icon': 'Truck'
    },
    {
        'id': 4,
        'type': 'system',
        'title': 'System Maintenance',
        'message': 'Scheduled maintenance will occur tonight from 2:00 AM to 4:00 AM',
        'timestamp': datetime.utcnow() - timedelta(hours=1),
        'read': True,
        'icon': 'Settings'
    },
    {
        'id': 5,
        'type': 'promotion',
        'title': 'New Promotion Available',
        'message': 'Get 20% off on all electronics this weekend!',
        'timestamp': datetime.utcnow() - timedelta(hours=2),
        'read': False,
        'icon': 'Tag'
    },
    {
        'id': 6,
        'type': 'review',
        'title': 'New Product Review',
        'message': 'Your product "Samsung Galaxy S24" received a 5-star review',
        'timestamp': datetime.utcnow() - timedelta(hours=3),
        'read': True,
        'icon': 'Star'
    },
    {
        'id': 7,
        'type': 'stock',
        'title': 'Low Stock Alert',
        'message': 'Product "Nike Air Max 270" is running low on stock (5 items left)',
        'timestamp': datetime.utcnow() - timedelta(hours=4),
        'read': False,
        'icon': 'AlertTriangle'
    },
    {
        'id': 8,
        'type': 'shop',
        'title': 'Shop Verification',
        'message': 'Your shop "TechHub Electronics" has been verified successfully',
        'timestamp': datetime.utcnow() - timedelta(days=1),
        'read': True,
        'icon': 'CheckCircle'
    }
]

@notification_bp.route('/notifications', methods=['GET'])
def get_notifications():
    """Get notifications with filtering and pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        filter_type = request.args.get('type')  # all, unread, order, system, etc.
        
        # Filter notifications
        notifications = MOCK_NOTIFICATIONS.copy()
        
        if filter_type and filter_type != 'all':
            if filter_type == 'unread':
                notifications = [n for n in notifications if not n['read']]
            else:
                notifications = [n for n in notifications if n['type'] == filter_type]
        
        # Sort by timestamp (newest first)
        notifications.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Pagination
        start = (page - 1) * per_page
        end = start + per_page
        paginated_notifications = notifications[start:end]
        
        # Convert timestamps to ISO format for JSON serialization
        for notification in paginated_notifications:
            notification['timestamp'] = notification['timestamp'].isoformat()
        
        # Calculate pagination info
        total = len(notifications)
        pages = (total + per_page - 1) // per_page
        has_next = page < pages
        has_prev = page > 1
        
        return jsonify({
            'success': True,
            'notifications': paginated_notifications,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': pages,
                'has_next': has_next,
                'has_prev': has_prev
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@notification_bp.route('/notifications/<int:notification_id>/read', methods=['PUT'])
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    try:
        # Find notification
        notification = None
        for n in MOCK_NOTIFICATIONS:
            if n['id'] == notification_id:
                notification = n
                break
        
        if not notification:
            return jsonify({'success': False, 'error': 'Notification not found'}), 404
        
        # Mark as read
        notification['read'] = True
        
        return jsonify({
            'success': True,
            'message': 'Notification marked as read'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@notification_bp.route('/notifications/mark-all-read', methods=['PUT'])
def mark_all_notifications_read():
    """Mark all notifications as read"""
    try:
        # Mark all as read
        for notification in MOCK_NOTIFICATIONS:
            notification['read'] = True
        
        return jsonify({
            'success': True,
            'message': 'All notifications marked as read'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@notification_bp.route('/notifications/<int:notification_id>', methods=['DELETE'])
def delete_notification(notification_id):
    """Delete a notification"""
    try:
        # Find and remove notification
        global MOCK_NOTIFICATIONS
        MOCK_NOTIFICATIONS = [n for n in MOCK_NOTIFICATIONS if n['id'] != notification_id]
        
        return jsonify({
            'success': True,
            'message': 'Notification deleted successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@notification_bp.route('/notifications/count', methods=['GET'])
def get_notification_count():
    """Get notification counts"""
    try:
        total = len(MOCK_NOTIFICATIONS)
        unread = len([n for n in MOCK_NOTIFICATIONS if not n['read']])
        
        # Count by type
        type_counts = {}
        for notification in MOCK_NOTIFICATIONS:
            notification_type = notification['type']
            if notification_type not in type_counts:
                type_counts[notification_type] = {'total': 0, 'unread': 0}
            
            type_counts[notification_type]['total'] += 1
            if not notification['read']:
                type_counts[notification_type]['unread'] += 1
        
        return jsonify({
            'success': True,
            'counts': {
                'total': total,
                'unread': unread,
                'by_type': type_counts
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@notification_bp.route('/notifications', methods=['POST'])
def create_notification():
    """Create a new notification (for testing purposes)"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['type', 'title', 'message']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        
        # Create new notification
        new_notification = {
            'id': max([n['id'] for n in MOCK_NOTIFICATIONS]) + 1 if MOCK_NOTIFICATIONS else 1,
            'type': data['type'],
            'title': data['title'],
            'message': data['message'],
            'timestamp': datetime.utcnow(),
            'read': False,
            'icon': data.get('icon', 'Bell')
        }
        
        MOCK_NOTIFICATIONS.insert(0, new_notification)  # Add to beginning
        
        # Convert timestamp for response
        response_notification = new_notification.copy()
        response_notification['timestamp'] = response_notification['timestamp'].isoformat()
        
        return jsonify({
            'success': True,
            'notification': response_notification,
            'message': 'Notification created successfully'
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

