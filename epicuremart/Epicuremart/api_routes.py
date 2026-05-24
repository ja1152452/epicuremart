from flask import Blueprint, jsonify, request
from functools import wraps
from app import db, User, Product, Order, Category
import jwt
import os

api = Blueprint('api', __name__, url_prefix='/api')

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token missing'}), 401
        try:
            token = token.replace('Bearer ', '')
            data = jwt.decode(token, os.environ.get('SECRET_KEY'), algorithms=['HS256'])
            current_user = User.query.get(data['user_id'])
        except:
            return jsonify({'error': 'Invalid token'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

@api.route('/login', methods=['POST'])
def api_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        token = jwt.encode({'user_id': user.id}, os.environ.get('SECRET_KEY'), algorithm='HS256')
        return jsonify({
            'token': token,
            'user': {
                'id': user.id,
                'email': user.email,
                'role': user.role,
                'full_name': user.full_name
            }
        })
    return jsonify({'error': 'Invalid credentials'}), 401

@api.route('/products', methods=['GET'])
def get_products():
    products = Product.query.filter_by(is_active=True).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'price': float(p.price),
        'stock': p.stock,
        'image': p.image
    } for p in products])

@api.route('/orders', methods=['GET'])
@token_required
def get_orders(current_user):
    orders = Order.query.filter_by(customer_id=current_user.id).all()
    return jsonify([{
        'id': o.id,
        'order_number': o.order_number,
        'status': o.status,
        'total_amount': float(o.total_amount)
    } for o in orders])
