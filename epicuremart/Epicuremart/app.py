from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message as MailMessage
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta, timezone
from functools import wraps
from decimal import Decimal
import jwt
import pytz
import qrcode
import io
import base64
import os
import secrets
from sqlalchemy import Numeric
from sqlalchemy.dialects.postgresql import UUID
import uuid
from dotenv import load_dotenv
from supabase import create_client, Client

print("STARTING APP")

# Load delivery fee config
_delivery_config_path = os.path.join(os.path.dirname(__file__), 'delivery_config.json')
if os.path.exists(_delivery_config_path):
    import json as _json
    with open(_delivery_config_path) as _f:
        _dc = _json.load(_f)
    app_delivery_base_fee = _dc.get('base_fee', 50.0)
    app_delivery_inter_island_fee = _dc.get('inter_island_fee', 30.0)
else:
    app_delivery_base_fee = 50.0
    app_delivery_inter_island_fee = 30.0

# Load environment variables
load_dotenv()

app = Flask(__name__)
# Flask Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'epicuremart-secret-key-change-in-production-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['DELIVERY_BASE_FEE'] = app_delivery_base_fee
app.config['DELIVERY_INTER_ISLAND_FEE'] = app_delivery_inter_island_fee


# Flask-Mail Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'jayzelyasona23@gmail.com'
app.config['MAIL_PASSWORD'] = 'eqdllipjbwnkucwa'
app.config['MAIL_DEFAULT_SENDER'] = ('Epicuremart', 'jayzelyasona23@gmail.com')
app.config['MAIL_MAX_EMAILS'] = None
app.config['MAIL_ASCII_ATTACHMENTS'] = False

db = SQLAlchemy(app)
mail = Mail(app)

# Supabase Configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Warning: Supabase initialization failed: {e}")
    supabase = None

try:
    supabase_admin: Client = None
    if SUPABASE_SERVICE_ROLE_KEY:
        supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
except Exception as e:
    print(f"Warning: Supabase admin initialization failed: {e}")
    supabase_admin = None

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}

# ==================== CUSTOM JINJA FILTERS ====================
@app.template_filter('safe_sum')
def safe_sum(items, attribute=None, start=0):
    """Sum items safely, treating None values as 0"""
    if not items:
        return start
    
    if attribute:
        return sum((getattr(item, attribute, None) or 0 for item in items), start)
    else:
        return sum((item or 0 for item in items), start)

@app.template_filter('courier_earnings_sum')
def courier_earnings_sum(items):
    """Sum courier earnings with fallback to 60% of delivery_fee if NULL"""
    if not items:
        return 0
    
    total = 0
    for item in items:
        earnings = getattr(item, 'courier_earnings', None)
        if earnings:
            total += float(earnings)
        else:
            # Fallback: calculate as 60% of delivery_fee
            delivery_fee = getattr(item, 'delivery_fee', None)
            if delivery_fee:
                total += float(delivery_fee) * 0.6
    return total

@app.template_filter('rider_earnings_sum')
def rider_earnings_sum(items):
    """Sum rider earnings with fallback to 40% of delivery_fee if NULL"""
    if not items:
        return 0
    
    total = 0
    for item in items:
        earnings = getattr(item, 'rider_earnings', None)
        if earnings:
            total += float(earnings)
        else:
            # Fallback: calculate as 40% of delivery_fee
            delivery_fee = getattr(item, 'delivery_fee', None)
            if delivery_fee:
                total += float(delivery_fee) * 0.4
    return total

# ==================== TIMEZONE HELPER ====================
# Philippines timezone (UTC+8)
PHILIPPINES_TZ = pytz.timezone('Asia/Manila')

def get_philippines_time():
    """Get current time in Philippines timezone"""
    return datetime.now(PHILIPPINES_TZ).replace(tzinfo=None)


def parse_uuid_value(value):
    """Convert UUID strings or numeric UUID integers to uuid.UUID."""
    if not value:
        raise ValueError('Missing UUID value')
    if isinstance(value, uuid.UUID):
        return value
    try:
        if isinstance(value, str) and value.isdigit():
            return uuid.UUID(int=int(value))
        return uuid.UUID(value)
    except (ValueError, AttributeError) as e:
        raise ValueError(f'Invalid UUID value: {value}') from e

# ==================== SUPABASE STORAGE HELPER ====================

def upload_to_supabase(file, bucket_name, file_path):
    """
    Upload a file to Supabase Storage and return the public URL.
    
    Args:
        file: werkzeug FileStorage object
        bucket_name: Name of the Supabase storage bucket
        file_path: Path where the file will be stored (e.g., 'users/id_documents/filename.jpg')
    
    Returns:
        tuple: (success: bool, result: str) - (True, public_url) or (False, error_message)
    """
    client = supabase_admin or supabase
    if not client:
        print("Error: Supabase storage not configured")
        return False, "Supabase storage not configured"
    
    try:
        # Reset file pointer to beginning
        file.seek(0)
        file_content = file.read()
        print(f"[upload_to_supabase] File size: {len(file_content)} bytes, content_type: {file.content_type}")
        
        response = client.storage.from_(bucket_name).upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": file.content_type}
        )
        print(f"[upload_to_supabase] Upload response: {response}")
        
        # Get the public URL
        public_url = client.storage.from_(bucket_name).get_public_url(file_path)
        print(f"[upload_to_supabase] Public URL: {public_url}")
        return True, public_url
    except Exception as e:
        print(f"[upload_to_supabase] Error uploading to Supabase: {e}")
        import traceback
        print(f"[upload_to_supabase] Traceback:\n{traceback.format_exc()}")
        return False, str(e)

# Predefined icons for categories
CATEGORY_ICONS = [
    '🧁', '☕', '🍬', '🌍', '🥗', '🍱',
    '🍕', '🍔', '🍟', '🌮', '🍝', '🍜',
    '🍱', '🍛', '🍲', '🥘', '🍳', '🥞',
    '🥐', '🥖', '🥨', '🧀', '🍖', '🍗',
    '🥩', '🥓', '🍤', '🍣', '🦞', '🦀',
    '🐟', '🥦', '🥬', '🥒', '🌶️', '🌽',
    '🥕', '🧄', '🧅', '🥔', '🍠', '🥜',
    '🍯', '🥛', '🧃', '🧋', '🍷', '🍺',
    '🧊', '🍰', '🎂', '🧁', '🥧', '🍦',
    '🍧', '🍨', '🍩', '🍪', '🍫', '🍬',
    '🍭', '🍮', '🍯', '🍎', '🍏', '🍊',
    '🍋', '🍌', '🍉', '🍇', '🍓', '🫐',
    '🍈', '🍒', '🍑', '🥭', '🍍', '🥥'
]

# ==================== MODELS ====================

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(120), unique=True, nullable=False)
    supabase_user_id = db.Column(db.String(255), unique=True)  # Supabase Auth User ID
    password_hash = db.Column(db.String(255))  # Made nullable for Supabase Auth
    role = db.Column(db.Enum('admin', 'seller', 'customer', 'courier', 'rider', name='user_role'), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    verification_code = db.Column(db.String(10))  # Email verification code
    verification_code_expires = db.Column(db.DateTime)  # Verification code expiry
    is_approved = db.Column(db.Boolean, default=True)  # Admin approval for sellers/couriers/riders
    is_suspended = db.Column(db.Boolean, default=False)  # Account suspension
    suspension_reason = db.Column(db.Text)  # Reason for suspension
    full_name = db.Column(db.String(100))
    first_name = db.Column(db.String(50))
    middle_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    id_document = db.Column(db.String(255))  # File path for uploaded ID
    business_permit = db.Column(db.String(255))  # Business permit for sellers
    drivers_license = db.Column(db.String(255))  # Driver's license for riders/couriers
    or_cr = db.Column(db.String(255))  # OR/CR for riders/couriers
    plate_number = db.Column(db.String(50))  # Plate number for riders/couriers
    vehicle_type = db.Column(db.String(50))  # Vehicle type for riders/couriers
    profile_picture = db.Column(db.String(255))  # Profile picture/business icon
    is_support_agent = db.Column(db.Boolean, default=False)  # Support agent flag
    last_activity = db.Column(db.DateTime)  # Last activity timestamp for online status
    quick_reply_templates = db.Column(db.Text)  # JSON string of quick reply templates
    company_name = db.Column(db.String(200))  # Company name for courier companies
    company_logo = db.Column(db.String(255))  # Company logo for courier companies
    company_address = db.Column(db.Text)  # Company address for courier companies
    company_description = db.Column(db.Text)  # Company description for courier companies
    courier_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'))  # Courier company that rider belongs to (for riders only)
    region = db.Column(db.String(100))
    province = db.Column(db.String(100))
    municipality = db.Column(db.String(100))
    barangay = db.Column(db.String(100))
    street = db.Column(db.String(255))
    block = db.Column(db.String(50))
    lot = db.Column(db.String(50))
    postal_code = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=get_philippines_time)
    
    # Relationships
    shop = db.relationship('Shop', backref='owner', uselist=False, cascade='all, delete-orphan')
    addresses = db.relationship('Address', backref='user', cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='customer', foreign_keys='Order.customer_id')
    cart_items = db.relationship('CartItem', backref='user', cascade='all, delete-orphan')
    riders = db.relationship('User', backref=db.backref('courier_company', remote_side='User.id'), foreign_keys=[courier_id])
    
    def set_password(self, password):
        """Kept for backwards compatibility, but new auth uses Supabase"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Kept for backwards compatibility, but new auth uses Supabase"""
        return check_password_hash(self.password_hash, password) if self.password_hash else False


class Shop(db.Model):
    __tablename__ = 'shops'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    logo = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_philippines_time)
    
    products = db.relationship('Product', backref='shop', cascade='all, delete-orphan')


class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))
    background_image = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=get_philippines_time)
    
    products = db.relationship('Product', backref='category')




class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id = db.Column(UUID(as_uuid=True), db.ForeignKey('shops.id'), nullable=False)
    category_id = db.Column(UUID(as_uuid=True), db.ForeignKey('categories.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(Numeric(10, 2), nullable=False)  # ✅ FIXED
    stock = db.Column(db.Integer, default=0)
    image = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_philippines_time)


class CartItem(db.Model):
    """Transaction-based cart - each add creates a separate entry"""
    __tablename__ = 'cart_items'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=get_philippines_time)
    
    # Relationships
    product = db.relationship('Product')


class Address(db.Model):
    __tablename__ = 'addresses'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    label = db.Column(db.String(50))  # Home, Work, etc.
    full_address = db.Column(db.Text, nullable=False)
    region = db.Column(db.String(100))
    province = db.Column(db.String(100))
    municipality = db.Column(db.String(100))
    city = db.Column(db.String(100))
    barangay = db.Column(db.String(100))
    street = db.Column(db.String(255))  # Street name
    block = db.Column(db.String(50))  # Block number
    lot = db.Column(db.String(50))  # Lot number
    postal_code = db.Column(db.String(20))
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_philippines_time)


class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    shop_id = db.Column(UUID(as_uuid=True), db.ForeignKey('shops.id'), nullable=False)
    courier_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'))
    rider_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'))
    
    status = db.Column(db.Enum(
        'PENDING_PAYMENT', 'READY_FOR_PICKUP', 'IN_TRANSIT_TO_RIDER',
        'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED', name='order_status'
    ), default='PENDING_PAYMENT')
    
    delivery_address_id = db.Column(UUID(as_uuid=True), db.ForeignKey('addresses.id'))
    total_amount = db.Column(Numeric(10, 2), nullable=False)
    delivery_fee = db.Column(Numeric(10, 2), default=0.00)
    subtotal = db.Column(Numeric(10, 2), nullable=False)
    commission_rate = db.Column(Numeric(5, 2), default=5.00)  # 5% commission
    commission_amount = db.Column(Numeric(10, 2), default=0.00)
    seller_amount = db.Column(Numeric(10, 2), default=0.00)
    courier_earnings = db.Column(Numeric(10, 2), default=0.00)  # Courier's share of delivery fee
    rider_earnings = db.Column(Numeric(10, 2), default=0.00)  # Rider's share of delivery fee
    shipping_fee_split_courier = db.Column(Numeric(5, 2), default=60.00)  # 60% to courier
    shipping_fee_split_rider = db.Column(Numeric(5, 2), default=40.00)  # 40% to rider

    # QR Tokens
    pickup_token = db.Column(db.String(500))  # JWT for courier pickup
    delivery_token = db.Column(db.String(500))  # JWT for customer delivery
    
    # Rider assignment lock
    rider_locked = db.Column(db.Boolean, default=False)  # Lock rider after handoff to prevent reassignment
    
    # Proof of Delivery
    proof_of_delivery = db.Column(db.String(255))  # Photo uploaded by rider as proof
    cancellation_reason = db.Column(db.Text)  # Reason for cancellation
    
    created_at = db.Column(db.DateTime, default=get_philippines_time)
    updated_at = db.Column(db.DateTime, default=get_philippines_time, onupdate=get_philippines_time)
    
    # Relationships
    items = db.relationship('OrderItem', backref='order', cascade='all, delete-orphan')
    delivery_address = db.relationship('Address', foreign_keys=[delivery_address_id])
    shop = db.relationship('Shop', foreign_keys=[shop_id])
    courier = db.relationship('User', foreign_keys=[courier_id])
    rider = db.relationship('User', foreign_keys=[rider_id])


class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(Numeric(10, 2), nullable=False)
    
    product = db.relationship('Product')

class ProductReview(db.Model):
    __tablename__ = 'product_reviews'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('orders.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    review_text = db.Column(db.Text)
    review_images = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=get_philippines_time)
    
    product = db.relationship('Product', backref='reviews')
    user = db.relationship('User')
    order = db.relationship('Order')


class RiderFeedback(db.Model):
    __tablename__ = 'rider_feedback'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rider_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('orders.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    feedback_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=get_philippines_time)
    
    rider = db.relationship('User', foreign_keys=[rider_id], backref='received_feedback')
    customer = db.relationship('User', foreign_keys=[customer_id])
    order = db.relationship('Order', backref='rider_feedback')


class DeliveryFee(db.Model):
    __tablename__ = 'delivery_fees'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city = db.Column(db.String(100), nullable=False, unique=True)
    province = db.Column(db.String(50), nullable=False)
    fee = db.Column(Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=get_philippines_time)


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'))
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=get_philippines_time)
    
    user = db.relationship('User')

class Conversation(db.Model):
    __tablename__ = 'conversations'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user1_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    user2_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    shop_id = db.Column(UUID(as_uuid=True), db.ForeignKey('shops.id'))  # Optional, for buyer-seller conversations
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('orders.id'))  # Optional, for order-related conversations
    conversation_type = db.Column(db.Enum('buyer_seller', 'seller_rider', 'buyer_rider', 'user_support', 'user_admin', 'seller_courier', 'buyer_courier', 'courier_rider', name='conversation_type'), nullable=False)
    is_read_only = db.Column(db.Boolean, default=False)  # Read-only for completed orders
    last_message_at = db.Column(db.DateTime, default=get_philippines_time)
    created_at = db.Column(db.DateTime, default=get_philippines_time)
    
    user1 = db.relationship('User', foreign_keys=[user1_id])
    user2 = db.relationship('User', foreign_keys=[user2_id])
    shop = db.relationship('Shop', foreign_keys=[shop_id])
    order = db.relationship('Order', foreign_keys=[order_id])
    messages = db.relationship('Message', backref='conversation', cascade='all, delete-orphan', order_by='Message.created_at')


class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = db.Column(UUID(as_uuid=True), db.ForeignKey('conversations.id'), nullable=False)
    sender_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.Enum('text', 'image', name='message_type'), default='text')
    image_url = db.Column(db.String(255))  # For image messages
    status = db.Column(db.Enum('sent', 'delivered', 'seen', name='message_status'), default='sent')  # Message status
    delivered_at = db.Column(db.DateTime)  # When message was delivered
    seen_at = db.Column(db.DateTime)  # When message was seen
    is_read = db.Column(db.Boolean, default=False)  # Deprecated, use status instead
    created_at = db.Column(db.DateTime, default=get_philippines_time)
    
    sender = db.relationship('User')


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notif_type = db.Column(db.String(50), default='info')  # info, success, warning, danger
    is_read = db.Column(db.Boolean, default=False)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('orders.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=get_philippines_time)

    user = db.relationship('User', foreign_keys=[user_id])
    order = db.relationship('Order', foreign_keys=[order_id])


class WithdrawalRequest(db.Model):
    __tablename__ = 'withdrawal_requests'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(Numeric(10, 2), nullable=False)
    payout_method = db.Column(db.String(50), nullable=False)  # e.g., 'bank_transfer', 'gcash', 'paymaya'
    account_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.Text)
    status = db.Column(db.Enum('pending', 'processing', 'completed', 'rejected', name='withdrawal_status'), default='pending')
    rejection_reason = db.Column(db.Text)
    processed_by = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'))
    processed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=get_philippines_time)
    updated_at = db.Column(db.DateTime, default=get_philippines_time, onupdate=get_philippines_time)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='withdrawal_requests')
    processor = db.relationship('User', foreign_keys=[processed_by])
    
# ==================== HELPER FUNCTIONS ====================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))
            
            user = User.query.get(session['user_id'])
            if user.is_support_agent and 'admin' in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('index'))
            if user.role not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('index'))
            
            if not user.is_approved and user.role in ['seller', 'courier', 'rider']:
                flash('Your account is pending approval.', 'warning')
                return redirect(url_for('pending_approval'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def create_notification(user_id, title, message, notif_type='info', order_id=None):
    """Create an in-app notification for a user"""
    try:
        notif = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notif_type=notif_type,
            order_id=order_id
        )
        db.session.add(notif)
        # Don't commit here — caller commits
    except Exception as e:
        print(f"Notification error: {e}")


def log_action(action, entity_type=None, entity_id=None, details=None):
    """Create audit log entry"""
    try:
        log = AuditLog(
            user_id=session.get('user_id'),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print(f"Logging error: {e}")


def send_email(to, subject, body):
    """Send email notification with better error handling"""
    try:
        msg = MailMessage(
            subject=subject,
            recipients=[to],
            body=body,
            sender=app.config['MAIL_DEFAULT_SENDER']
        )
        mail.send(msg)
        print(f"[SUCCESS] Email sent successfully to {to}")
        return True
    except Exception as e:
        print(f"[ERROR] Email error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def generate_qr_token(order_id, token_type, expiry_hours=24):
    """Generate JWT token for QR code"""
    payload = {
        'order_id': str(order_id),
        'type': token_type,  # 'pickup' or 'delivery'
        'exp': datetime.utcnow() + timedelta(hours=expiry_hours)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')


def verify_qr_token(token):
    """Verify and decode JWT token from QR"""
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def generate_qr_code(data):
    """Generate QR code image as base64"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode()


def get_island_group(region):
    """Returns 0=Luzon, 1=Visayas, 2=Mindanao based on region string"""
    if not region:
        return 0
    r = region.lower()
    if any(x in r for x in ['visayas', 'region vi', 'region vii', 'region viii',
                             'western visayas', 'central visayas', 'eastern visayas']):
        return 1
    if any(x in r for x in ['mindanao', 'zamboanga', 'davao', 'soccsksargen', 'caraga',
                             'armm', 'barmm', 'northern mindanao', 'southern mindanao',
                             'region ix', 'region x', 'region xi', 'region xii', 'region xiii']):
        return 2
    return 0


def calculate_delivery_fee(seller_region, customer_region):
    """Calculate delivery fee based on island group distance"""
    base = app.config.get('DELIVERY_BASE_FEE', 50.0)
    addon = app.config.get('DELIVERY_INTER_ISLAND_FEE', 30.0)
    zone_diff = abs(get_island_group(seller_region) - get_island_group(customer_region))
    return base + (zone_diff * addon)


def generate_order_number():
    """Generate unique order number"""
    import random
    timestamp = datetime.now().strftime('%Y%m%d')
    random_part = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    return f"EM{timestamp}{random_part}"


def update_user_activity():
    """Update the last_activity timestamp for the current user"""
    if 'user_id' in session:
        try:
            user = User.query.get(session['user_id'])
            if user:
                user.last_activity = get_philippines_time()
                db.session.commit()
        except Exception as e:
            print(f"Error updating user activity: {e}")


def update_password_both(user, new_password):
    """Update password in both database and Supabase Auth"""
    # Update local database
    user.set_password(new_password)
    
    # Update Supabase Auth if user has supabase_user_id
    if user.supabase_user_id and supabase:
        try:
            # Use admin API to update user password
            import requests
            supabase_url = os.environ.get('SUPABASE_URL')
            service_role_key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
            
            if service_role_key:
                headers = {
                    'apikey': service_role_key,
                    'Authorization': f'Bearer {service_role_key}',
                    'Content-Type': 'application/json'
                }
                
                update_url = f"{supabase_url}/auth/v1/admin/users/{user.supabase_user_id}"
                response = requests.put(update_url, headers=headers, json={'password': new_password})
                
                if response.status_code == 200:
                    print(f"[SUCCESS] Password updated in Supabase Auth for {user.email}")
                else:
                    print(f"[WARNING] Supabase password update failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[WARNING] Error updating Supabase password: {e}")


def get_user_online_status(user):
    """Get online status and last active time for a user"""
    if not user or not user.last_activity:
        return {'online': False, 'last_active': None, 'last_active_text': 'Never'}
    
    now = datetime.utcnow()
    time_diff = (now - user.last_activity).total_seconds()
    
    # Online if active in last 5 minutes
    if time_diff < 300:
        return {'online': True, 'last_active': user.last_activity, 'last_active_text': 'Online'}
    
    # Format last active text
    if time_diff < 3600:  # Less than 1 hour
        minutes = int(time_diff / 60)
        text = f"Last active {minutes} minute{'s' if minutes != 1 else ''} ago"
    elif time_diff < 86400:  # Less than 1 day
        hours = int(time_diff / 3600)
        text = f"Last active {hours} hour{'s' if hours != 1 else ''} ago"
    elif time_diff < 172800:  # Less than 2 days
        text = f"Last active yesterday, {user.last_activity.strftime('%I:%M %p')}"
    else:
        text = f"Last active {user.last_activity.strftime('%b %d, %I:%M %p')}"
    
    return {'online': False, 'last_active': user.last_activity, 'last_active_text': text}


def generate_sales_report_pdf(user_role, user_id, start_date=None, end_date=None):
    """Generate PDF sales report for admin, seller, courier, or rider"""
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    
    # Create PDF buffer
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    heading_style2 = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=12,
                                    textColor=colors.HexColor('#2c3e50'), spaceAfter=8,
                                    spaceBefore=16, fontName='Helvetica-Bold')
    
    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    # Get user
    user = User.query.get(user_id)
    
    # Title
    elements.append(Paragraph("Sales Report", title_style))
    elements.append(Spacer(1, 12))
    
    # User Information
    info_data = [
        ['User Information', ''],
        ['Name:', user.full_name or user.email],
        ['Role:', user.role.upper()],
        ['User ID:', str(user.id)],
    ]
    
    # Date range
    if start_date and end_date:
        info_data.append(['Date Range:', f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"])
    else:
        info_data.append(['Date Range:', 'All Time'])
    
    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 20))
    
    # Query based on role
    from sqlalchemy import func
    
    if user_role == 'seller':
        shop = user.shop
        if not shop:
            return None

        query = Order.query.filter_by(shop_id=shop.id, status='DELIVERED')
        if start_date and end_date:
            query = query.filter(Order.created_at.between(start_date, end_date))
        delivered = query.all()

        cancelled_q = Order.query.filter_by(shop_id=shop.id, status='CANCELLED')
        if start_date and end_date:
            cancelled_q = cancelled_q.filter(Order.created_at.between(start_date, end_date))
        cancelled = cancelled_q.all()

        gross_sales = sum(float(o.subtotal or 0) for o in delivered)
        total_commission = sum(float(o.commission_amount or 0) for o in delivered)
        total_delivery_fees = sum(float(o.delivery_fee or 0) for o in delivered)
        net_profit = gross_sales - total_commission
        order_count = len(delivered)

        # Reporting period
        if start_date and end_date:
            period_str = f"{start_date.strftime('%B %d, %Y')} – {end_date.strftime('%B %d, %Y')}"
        elif delivered:
            oldest = min(o.created_at for o in delivered)
            newest = max(o.created_at for o in delivered)
            period_str = f"{oldest.strftime('%B %d, %Y')} – {newest.strftime('%B %d, %Y')}"
        else:
            period_str = 'All Time'

        # Section I header
        elements.append(Paragraph('I. REPORT OVERVIEW', heading_style2))
        overview_data = [
            ['Reporting Period', period_str],
            ['Shop Name', shop.name],
            ['Generated On', datetime.now().strftime('%B %d, %Y %I:%M %p')],
        ]
        ov_table = Table(overview_data, colWidths=[2.5*inch, 4*inch])
        ov_table.setStyle(TableStyle([
            ('FONTNAME', (0,0),(0,-1),'Helvetica-Bold'),
            ('FONTSIZE', (0,0),(-1,-1),9),
            ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f0f4ff')),
            ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#c0c8e0')),
            ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
        ]))
        elements.append(ov_table)
        elements.append(Spacer(1,14))

        # Section II
        elements.append(Paragraph('II. SALES & TRANSACTIONS', heading_style2))
        sales_data = [
            ['Metric', 'Value'],
            ['Gross Sales (Delivered Orders)', f'₱{gross_sales:,.2f}'],
            ['Total Delivered Orders', str(order_count)],
            ['Shipping Fees (Paid by Customer)', f'₱{total_delivery_fees:,.2f}'],
            ['Platform Commission (5%)', f'-₱{total_commission:,.2f}'],
        ]
        s_table = Table(sales_data, colWidths=[3.5*inch, 2.5*inch])
        s_table.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#2c3e50')),
            ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('FONTSIZE',(0,0),(-1,-1),9),
            ('ALIGN',(1,0),(1,-1),'RIGHT'),
            ('BACKGROUND',(0,1),(-1,-1),colors.white),
            ('GRID',(0,0),(-1,-1),0.5,colors.grey),
            ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
        ]))
        elements.append(s_table)
        elements.append(Spacer(1,14))

        # Section III – Product Performance
        product_stats = {}
        for order in delivered:
            for item in order.items:
                pid = str(item.product_id)
                if pid not in product_stats:
                    product_stats[pid] = {
                        'name': item.product.name if item.product else 'Unknown',
                        'qty': 0, 'stock': item.product.stock if item.product else 0
                    }
                product_stats[pid]['qty'] += item.quantity
        products = sorted(product_stats.values(), key=lambda x: x['qty'], reverse=True)

        elements.append(Paragraph('III. PRODUCT PERFORMANCE', heading_style2))
        if products:
            prod_data = [['Product Name', 'Qty Sold', 'Remaining Stock']]
            for p in products:
                prod_data.append([p['name'][:45], str(p['qty']), str(p['stock'])])
            p_table = Table(prod_data, colWidths=[3.5*inch, 1.2*inch, 1.8*inch])
            p_table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#27ae60')),
                ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
                ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
                ('FONTSIZE',(0,0),(-1,-1),9),
                ('ALIGN',(1,0),(-1,-1),'CENTER'),
                ('BACKGROUND',(0,1),(-1,-1),colors.white),
                ('GRID',(0,0),(-1,-1),0.5,colors.grey),
                ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
            ]))
            elements.append(p_table)
        else:
            elements.append(Paragraph('No delivered products in this period.', styles['Normal']))
        elements.append(Spacer(1,14))

        # Section IV – Costs & RTS
        elements.append(Paragraph('IV. COSTS & COD-SPECIFIC DEDUCTIONS', heading_style2))
        rts_stats = {}
        for order in cancelled:
            for item in order.items:
                pid = str(item.product_id)
                if pid not in rts_stats:
                    rts_stats[pid] = {'name': item.product.name if item.product else 'Unknown', 'qty': 0}
                rts_stats[pid]['qty'] += item.quantity
        rts_list = sorted(rts_stats.values(), key=lambda x: x['qty'], reverse=True)

        costs_data = [
            ['Item', 'Value'],
            ['Shipping Fee (Paid by Customer)', f'₱{total_delivery_fees:,.2f}'],
            ['RTS / Cancelled Orders', str(len(cancelled))],
        ]
        c_table = Table(costs_data, colWidths=[3.5*inch, 2.5*inch])
        c_table.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e74c3c')),
            ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('FONTSIZE',(0,0),(-1,-1),9),
            ('ALIGN',(1,0),(1,-1),'RIGHT'),
            ('BACKGROUND',(0,1),(-1,-1),colors.white),
            ('GRID',(0,0),(-1,-1),0.5,colors.grey),
            ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
        ]))
        elements.append(c_table)

        if rts_list:
            elements.append(Spacer(1,8))
            rts_data = [['Returned Product', 'Qty Returned']]
            for r in rts_list:
                rts_data.append([r['name'][:45], str(r['qty'])])
            r_table = Table(rts_data, colWidths=[4.5*inch, 1.5*inch])
            r_table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#c0392b')),
                ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
                ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
                ('FONTSIZE',(0,0),(-1,-1),9),
                ('ALIGN',(1,0),(1,-1),'CENTER'),
                ('BACKGROUND',(0,1),(-1,-1),colors.white),
                ('GRID',(0,0),(-1,-1),0.5,colors.grey),
                ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
            ]))
            elements.append(r_table)
        elements.append(Spacer(1,14))

        # Section V – Net Profit
        elements.append(Paragraph('V. NET PROFIT (THE BOTTOM LINE)', heading_style2))
        np_data = [
            ['Formula', 'Net Profit = Gross Sales − Platform Commission'],
            ['Gross Sales', f'₱{gross_sales:,.2f}'],
            ['Platform Commission (5%)', f'-₱{total_commission:,.2f}'],
            ['NET PROFIT', f'₱{net_profit:,.2f}'],
        ]
        np_table = Table(np_data, colWidths=[2.5*inch, 4*inch])
        np_table.setStyle(TableStyle([
            ('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),
            ('FONTNAME',(0,3),(-1,3),'Helvetica-Bold'),
            ('FONTSIZE',(0,0),(-1,-1),9),
            ('FONTSIZE',(0,3),(-1,3),11),
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#ecf0f1')),
            ('BACKGROUND',(0,3),(-1,3),colors.HexColor('#2ecc71')),
            ('TEXTCOLOR',(0,3),(-1,3),colors.white),
            ('GRID',(0,0),(-1,-1),0.5,colors.grey),
            ('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9),
        ]))
        elements.append(np_table)
        elements.append(Spacer(1,20))
        elements.append(Paragraph(
            '<i>Note: COGS (Cost of Goods Sold) is not tracked by the platform. '
            'Subtract your own product costs from Net Profit for your actual take-home earnings.</i>',
            ParagraphStyle('Note', parent=styles['Normal'], fontSize=8, textColor=colors.grey)
        ))
        
    elif user_role == 'courier':
        query = Order.query.filter_by(courier_id=user_id, status='DELIVERED')
        if start_date and end_date:
            query = query.filter(Order.created_at.between(start_date, end_date))
        
        orders = query.all()
        total_earnings = sum([float(o.courier_earnings or 0) for o in orders])
        order_count = len(orders)
        
        summary_data = [
            ['Summary', ''],
            ['Total Deliveries:', str(order_count)],
            ['Total Earnings:', f"₱{total_earnings:,.2f}"],
        ]
        
    elif user_role == 'rider':
        query = Order.query.filter_by(rider_id=user_id, status='DELIVERED')
        if start_date and end_date:
            query = query.filter(Order.created_at.between(start_date, end_date))
        
        orders = query.all()
        total_earnings = sum([float(o.rider_earnings or 0) for o in orders])
        order_count = len(orders)
        
        summary_data = [
            ['Summary', ''],
            ['Total Deliveries:', str(order_count)],
            ['Total Earnings:', f"₱{total_earnings:,.2f}"],
        ]
        
    elif user_role == 'admin':
        from sqlalchemy import func as sqlfunc
        query = Order.query.filter_by(status='DELIVERED')
        if start_date and end_date:
            query = query.filter(Order.created_at.between(start_date, end_date))

        orders = query.all()
        total_revenue = sum([float(o.total_amount or 0) for o in orders])
        total_commission = sum([float(o.commission_amount or 0) for o in orders])
        total_products_sold = sum([sum([int(item.quantity or 0) for item in o.items]) for o in orders])
        order_count = len(orders)
        avg_order = total_revenue / order_count if order_count > 0 else 0

        # Best selling products
        product_sales = {}
        for o in orders:
            for item in o.items:
                name = item.product.name if item.product else 'Unknown'
                product_sales[name] = product_sales.get(name, 0) + int(item.quantity or 0)
        top_products = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:10]

        summary_data = [
            ['Summary', ''],
            ['Total Orders:', str(order_count)],
            ['Total Products Sold:', str(total_products_sold)],
            ['Total Revenue:', f'₱{total_revenue:,.2f}'],
            ['Platform Commission (5%):', f'₱{total_commission:,.2f}'],
            ['Average Order Value:', f'₱{avg_order:,.2f}'],
        ]

    if user_role != "seller":
        summary_table = Table(summary_data, colWidths=[3*inch, 3*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2ecc71')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(summary_table)
    
    # Best Selling Products table (admin only)
    if user_role == 'admin' and top_products:
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.enums import TA_CENTER
        from reportlab.platypus import Spacer
        heading_style2 = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=13,
                                        textColor=colors.HexColor('#2c3e50'), spaceAfter=10, spaceBefore=20,
                                        fontName='Helvetica-Bold')
        elements.append(Spacer(1, 20))
        elements.append(Paragraph('BEST SELLING PRODUCTS', heading_style2))
        prod_data = [['Rank', 'Product Name', 'Units Sold']]
        for idx, (name, qty) in enumerate(top_products, 1):
            prod_data.append([str(idx), name[:45], str(qty)])
        prod_table = Table(prod_data, colWidths=[0.6*inch, 4*inch, 1.2*inch])
        prod_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27ae60')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f9f4')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        elements.append(prod_table)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer


@app.context_processor
def inject_cart_and_messages():
    """Make cart count, unread messages, and unread notifications available to all templates"""
    cart_count = 0
    unread_messages = 0
    unread_notifications = 0
    
    if 'user_id' in session:
        user_id = session['user_id']
        cart_count = CartItem.query.filter_by(user_id=user_id).count()
        
        unread_messages = Message.query.join(Conversation).filter(
            db.or_(
                db.and_(Conversation.user1_id == user_id, Message.sender_id != user_id),
                db.and_(Conversation.user2_id == user_id, Message.sender_id != user_id)
            ),
            Message.is_read == False
        ).count()

        unread_notifications = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    
    return dict(cart_count=cart_count, unread_messages=unread_messages, unread_notifications=unread_notifications)


# ==================== ROUTES ====================

@app.route('/')
def index():
    categories = Category.query.all()
    products = Product.query.filter_by(is_active=True).limit(12).all()
    # conversation = Conversation.query.all()
    return render_template('index.html', categories=categories, products=products)


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role', 'customer')
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name', '')
        last_name = request.form.get('last_name')
        phone = request.form.get('phone', '')
        
        # Address fields
        region = request.form.get('region')
        province = request.form.get('province')
        municipality = request.form.get('municipality')
        barangay = request.form.get('barangay')
        postal_code = request.form.get('postal_code', '')
        street = request.form.get('street', '')
        block = request.form.get('block', '')
        lot = request.form.get('lot', '')
        
        # Validate postal code (must be exactly 4 digits)
        if postal_code and not (postal_code.isdigit() and len(postal_code) == 4):
            flash('Postal code must be exactly 4 digits.', 'danger')
            return redirect(url_for('register'))
        
        # Rider/Courier specific fields
        plate_number = request.form.get('plate_number', '')
        vehicle_type = request.form.get('vehicle_type', '')
        courier_id = request.form.get('courier_id', '')
        company_name = request.form.get('company_name', '')
        
        # Validate password match
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))
        
        # Check if email exists in database
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))
        
        # Phone validation - required for riders and customers
        if role in ['customer', 'rider', 'courier'] and not phone:
            flash('Contact number is required for this role.', 'danger')
            return redirect(url_for('register'))
        
        # Validate company name for couriers
        if role == 'courier' and not company_name:
            flash('Company name is required for couriers.', 'danger')
            return redirect(url_for('register'))
        
        # Validate courier selection for riders
        if role == 'rider' and not courier_id:
            flash('Please select a courier company.', 'danger')
            return redirect(url_for('register'))
        
        # Sellers, couriers, riders need admin approval
        is_approved = True if role == 'customer' else False
        
        # Construct full name
        full_name = f"{first_name} {middle_name} {last_name}".replace('  ', ' ').strip()
        
        # ===== SUPABASE AUTH REGISTRATION =====
        try:
            if not supabase:
                flash('Authentication service is temporarily unavailable. Please try again later.', 'danger')
                return redirect(url_for('register'))
            
            # Create user in Supabase Auth
            auth_response = supabase.auth.sign_up({
                "email": email,
                "password": password
            })
            
            supabase_user_id = auth_response.user.id
            
        except Exception as e:
            error_msg = str(e)
            if 'already registered' in error_msg.lower() or 'already exists' in error_msg.lower() or 'user_already_exists' in error_msg.lower():
                # Email exists in Supabase but not in database - need to delete from Supabase first
                flash('This email was previously registered. Please use a different email or contact admin for assistance.', 'danger')
            else:
                flash(f'Registration error: {error_msg}', 'danger')
            return redirect(url_for('register'))
        
        # Generate verification code for ALL users (web and Flutter)
        verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        verification_expires = datetime.utcnow() + timedelta(hours=48)
        is_verified = False  # All users need verification
        
        # Create user record in database
        user = User(
            email=email,
            supabase_user_id=supabase_user_id,
            role=role,
            full_name=full_name,
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            phone=phone,
            plate_number=plate_number,
            vehicle_type=vehicle_type,
            is_approved=is_approved,
            is_verified=is_verified,
            verification_code=verification_code,
            verification_code_expires=verification_expires,
            company_name=company_name if role == 'courier' else None,
            courier_id=uuid.UUID(courier_id) if courier_id and role == 'rider' else None,
            region=region,
            province=province,
            municipality=municipality,
            barangay=barangay,
            street=street,
            postal_code=postal_code
        )
        user.set_password(password)
        
        # Handle ID document upload for all roles (including buyers/customers)
        # NOTE: Couriers do NOT need ID documents - only business permit
        if role in ['customer', 'seller', 'rider']:
            if 'id_document' in request.files:
                file = request.files['id_document']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"id_{role}_{email.split('@')[0]}_{filename}"
                    file_path = f"users/id_documents/{filename}"
                    success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                    if success:
                        user.id_document = result  # Store the public URL
                    else:
                        flash(f'Error uploading ID document: {result}', 'danger')
                        return redirect(url_for('register'))
                elif role in ['seller', 'rider']:
                    flash('Valid ID document is required for this role.', 'danger')
                    return redirect(url_for('register'))
            elif role in ['seller', 'rider']:
                flash('ID document upload is required for sellers and riders.', 'danger')
                return redirect(url_for('register'))
        
        # Handle business permit for sellers
        if role == 'seller':
            if 'business_permit' in request.files:
                file = request.files['business_permit']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"business_permit_{email.split('@')[0]}_{filename}"
                    file_path = f"users/business_permits/{filename}"
                    success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                    if success:
                        user.business_permit = result  # Store the public URL
                    else:
                        flash(f'Error uploading business permit: {result}', 'danger')
                        return redirect(url_for('register'))
                else:
                    flash('Valid business permit is required for sellers.', 'danger')
                    return redirect(url_for('register'))
            else:
                flash('Business permit upload is required for sellers.', 'danger')
                return redirect(url_for('register'))
        
        # Handle business permit/registration for couriers
        if role == 'courier':
            if 'business_permit' in request.files:
                file = request.files['business_permit']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"business_permit_courier_{email.split('@')[0]}_{filename}"
                    file_path = f"users/business_permits/{filename}"
                    success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                    if success:
                        user.business_permit = result  # Store the public URL
                    else:
                        flash(f'Error uploading business permit: {result}', 'danger')
                        return redirect(url_for('register'))
                else:
                    flash('Valid business permit/registration document is required for couriers.', 'danger')
                    return redirect(url_for('register'))
            else:
                flash('Business permit/registration document upload is required for couriers.', 'danger')
                return redirect(url_for('register'))
        
        # Handle driver's license and OR/CR for riders ONLY (not for couriers)
        if role == 'rider':
            # Driver's License
            if 'drivers_license' in request.files:
                file = request.files['drivers_license']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"drivers_license_{role}_{email.split('@')[0]}_{filename}"
                    file_path = f"users/drivers_licenses/{filename}"
                    success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                    if success:
                        user.drivers_license = result  # Store the public URL
                    else:
                        flash(f'Error uploading driver\'s license: {result}', 'danger')
                        return redirect(url_for('register'))
                else:
                    flash('Valid driver\'s license is required for riders.', 'danger')
                    return redirect(url_for('register'))
            else:
                flash('Driver\'s license upload is required for riders.', 'danger')
                return redirect(url_for('register'))
            
            # OR/CR
            if 'or_cr' in request.files:
                file = request.files['or_cr']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"or_cr_{role}_{email.split('@')[0]}_{filename}"
                    file_path = f"users/or_cr/{filename}"
                    success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                    if success:
                        user.or_cr = result  # Store the public URL
                    else:
                        flash(f'Error uploading OR/CR: {result}', 'danger')
                        return redirect(url_for('register'))
                else:
                    flash('Valid OR/CR is required for riders.', 'danger')
                    return redirect(url_for('register'))
            else:
                flash('OR/CR upload is required for riders.', 'danger')
                return redirect(url_for('register'))
            
            # Validate plate number and vehicle type for riders only
            if not plate_number or not vehicle_type:
                flash('Plate number and vehicle type are required for riders.', 'danger')
                return redirect(url_for('register'))
        
        db.session.add(user)
        db.session.commit()
        
        # Send verification email with 6-digit CODE
        email_sent = send_email(
            user.email,
            'Email Verification Code - Epicuremart',
            f'Welcome to Epicuremart!\n\n'
            f'Your email verification code is: {verification_code}\n\n'
            f'This code will expire in 48 hours.\n\n'
            f'Please enter this code on the verification page to complete your registration.'
        )
        
        # ALWAYS print verification code for debugging
        print(f"\n{'='*60}")
        print(f"VERIFICATION CODE FOR {user.email}")
        print(f"CODE: {verification_code}")
        print(f"Email sent: {'[SUCCESS] YES' if email_sent else '[ERROR] NO'}")
        print(f"{'='*60}\n")
        
        # Create address entry if provided
        if region and province and barangay:
            full_address_parts = []
            if lot:
                full_address_parts.append(f"Lot {lot}")
            if block:
                full_address_parts.append(f"Block {block}")
            if street:
                full_address_parts.append(street)
            full_address_parts.extend([barangay, municipality, province, region])
            full_address = ", ".join(full_address_parts)
            
            address = Address(
                user_id=user.id,
                label='Home',
                full_address=full_address,
                region=region,
                province=province,
                municipality=municipality,
                barangay=barangay,
                postal_code=postal_code,
                street=street,
                block=block,
                lot=lot,
                is_default=True
            )
            db.session.add(address)
            db.session.commit()
        
        log_action('USER_REGISTERED', 'User', str(user.id), f'New {role} registered - verification code sent')
        
        flash('Registration successful! Please check your email for the 6-digit verification code.', 'success')
        return redirect(url_for('verify_email_code', user_id=user.id))
    
    # Get list of approved couriers for rider registration
    couriers = User.query.filter_by(role='courier', is_approved=True).all()
    return render_template('register.html', couriers=couriers)


@app.route('/verify-email/<token>')
def verify_email_link(token):
    """Email verification via link (not code)"""
    payload = verify_qr_token(token)
    if not payload or payload.get('type') != 'email_verify':
        flash('Invalid or expired verification link.', 'danger')
        return redirect(url_for('login'))
    
    user = User.query.get(payload['order_id'])  # Reusing order_id field for user_id
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('login'))
    
    if user.is_verified:
        flash('Email already verified. You can log in now.', 'info')
        return redirect(url_for('login'))
    
    user.is_verified = True
    user.verification_code = None
    user.verification_code_expires = None
    db.session.commit()
    
    log_action('EMAIL_VERIFIED', 'User', str(user.id), 'Verified via email link')
    flash('Email verified successfully! You can now log in.', 'success')
    return redirect(url_for('login'))


@app.route('/verify-code/<user_id>', methods=['GET', 'POST'])
def verify_email_code(user_id):
    """Email verification using 6-digit code"""
    # Convert string UUID to UUID object
    try:
        import uuid as uuid_lib
        user_id = uuid_lib.UUID(user_id)
    except (ValueError, AttributeError):
        flash('Invalid verification link.', 'danger')
        return redirect(url_for('login'))
    
    user = User.query.get_or_404(user_id)
    
    if user.is_verified:
        flash('Your account is already verified.', 'info')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        code = request.form.get('verification_code', '').strip()
        
        # DEBUG: Print what we're comparing
        print(f"[DEBUG] User entered: '{code}'")
        print(f"[DEBUG] Database has: '{user.verification_code}'")
        print(f"[DEBUG] Match: {user.verification_code == code}")
        
        if not code:
            flash('Please enter the verification code.', 'warning')
            return render_template('verify_code.html', user=user)
        
        # Check if code matches and is not expired
        if user.verification_code != code:
            flash('Invalid verification code. Please try again.', 'danger')
            return render_template('verify_code.html', user=user)
        
        if user.verification_code_expires and datetime.utcnow() > user.verification_code_expires:
            flash('Verification code has expired. Please request a new one.', 'danger')
            return render_template('verify_code.html', user=user, show_resend=True)
        
        # Verify the user
        user.is_verified = True
        user.verification_code = None
        user.verification_code_expires = None
        db.session.commit()
        
        # Auto-confirm in Supabase so the account works on both web and app
        if user.supabase_user_id:
            try:
                import requests as _req
                _req.put(
                    f"{os.environ.get('SUPABASE_URL')}/auth/v1/admin/users/{user.supabase_user_id}",
                    headers={
                        'apikey': os.environ.get('SUPABASE_SERVICE_ROLE_KEY'),
                        'Authorization': f"Bearer {os.environ.get('SUPABASE_SERVICE_ROLE_KEY')}",
                        'Content-Type': 'application/json'
                    },
                    json={'email_confirm': True}
                )
            except Exception:
                pass
        
        log_action('EMAIL_VERIFIED', 'User', str(user.id), 'Verified via code')
        flash('Email verified successfully! You can now log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('verify_code.html', user=user)


@app.route('/resend-verification/<user_id>', methods=['POST'])
def resend_verification_code(user_id):
    """Resend verification code"""
    # Convert string UUID to UUID object
    try:
        import uuid as uuid_lib
        user_id = uuid_lib.UUID(user_id)
    except (ValueError, AttributeError):
        flash('Invalid verification link.', 'danger')
        return redirect(url_for('login'))
    
    user = User.query.get_or_404(user_id)
    
    if user.is_verified:
        flash('Your account is already verified.', 'info')
        return redirect(url_for('login'))
    
    # Generate new verification code
    verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    user.verification_code = verification_code
    user.verification_code_expires = datetime.utcnow() + timedelta(hours=48)
    db.session.commit()
    
    # Send verification email with code
    send_email(
        user.email,
        'Your New Verification Code',
        f'Your new verification code is: {verification_code}\n\nThis code will expire in 48 hours.'
    )
    
    flash('A new verification code has been sent to your email.', 'success')
    return redirect(url_for('verify_email_code', user_id=user.id))


# ==================== API ENDPOINTS FOR FLUTTER APP ====================

@app.route('/api/send-verification-email', methods=['POST'])
def api_send_verification_email():
    """API endpoint for Flutter app to send verification code email"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400
    
    email = data.get('email', '').strip()
    code = data.get('code', '').strip()
    
    if not email or not code:
        return jsonify({'success': False, 'message': 'Email and code are required'}), 400
    
    # Send verification email
    email_sent = send_email(
        email,
        'Email Verification Code - Epicuremart',
        f'''Welcome to Epicuremart!

Your email verification code is:

    {code}

(This is a 6-digit code)

This code will expire in 48 hours.

Please enter this code on the verification page to complete your registration.

If you did not request this code, please ignore this email.'''
    )
    
    if email_sent:
        print(f"\n{'='*60}")
        print(f"[SUCCESS] API VERIFICATION EMAIL SENT")
        print(f"[EMAIL] Email: {email}")
        print(f"[SECURE] Code: {code}")
        print(f"[TIME] Timestamp: {datetime.utcnow()}")
        print(f"{'='*60}\n")
        
        return jsonify({'success': True, 'message': 'Verification email sent successfully'}), 200
    else:
        print(f"\n{'='*60}")
        print(f"[ERROR] API VERIFICATION EMAIL FAILED")
        print(f"[EMAIL] Email: {email}")
        print(f"[TIME] Timestamp: {datetime.utcnow()}")
        print(f"{'='*60}\n")
        
        return jsonify({'success': False, 'message': 'Failed to send email. Please try again later.'}), 500


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Find user in database
        user = User.query.filter_by(email=email).first()
        
        if not user:
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('login'))
        
        # ===== AUTHENTICATION: Supabase OR Local =====
        # Try Supabase first if user has supabase_user_id
        if user.supabase_user_id:
            try:
                if not supabase:
                    flash('Authentication service is temporarily unavailable. Please try again later.', 'danger')
                    return redirect(url_for('login'))
                
                auth_response = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
                
                if not auth_response.user:
                    flash('Invalid email or password.', 'danger')
                    return redirect(url_for('login'))
                    
            except Exception as e:
                error_str = str(e)
                # 403 = email not confirmed in Supabase (common for app-registered accounts)
                if 'email not confirmed' in error_str.lower() or '403' in error_str or 'code: 403' in error_str.lower():
                    # Auto-confirm via admin API and retry sign-in
                    try:
                        import requests as _requests
                        _url = f"{os.environ.get('SUPABASE_URL')}/auth/v1/admin/users/{user.supabase_user_id}"
                        _headers = {
                            'apikey': os.environ.get('SUPABASE_SERVICE_ROLE_KEY'),
                            'Authorization': f"Bearer {os.environ.get('SUPABASE_SERVICE_ROLE_KEY')}",
                            'Content-Type': 'application/json'
                        }
                        _requests.put(_url, headers=_headers, json={'email_confirm': True})
                        auth_response = supabase.auth.sign_in_with_password({'email': email, 'password': password})
                        if not auth_response.user:
                            flash('Invalid email or password.', 'danger')
                            return redirect(url_for('login'))
                    except Exception:
                        flash('Invalid email or password.', 'danger')
                        return redirect(url_for('login'))
                else:
                    flash('Invalid email or password.', 'danger')
                    return redirect(url_for('login'))
        elif user.password_hash == 'SUPABASE_AUTH' or not user.password_hash:
            # App-registered account with no supabase_user_id stored — try Supabase auth directly
            try:
                if not supabase:
                    flash('Authentication service is temporarily unavailable.', 'danger')
                    return redirect(url_for('login'))
                auth_response = supabase.auth.sign_in_with_password({'email': email, 'password': password})
                if not auth_response.user:
                    flash('Invalid email or password.', 'danger')
                    return redirect(url_for('login'))
                # Save supabase_user_id for future logins
                user.supabase_user_id = auth_response.user.id
                db.session.commit()
            except Exception as e:
                error_str = str(e)
                if 'email not confirmed' in error_str.lower() or '403' in error_str or 'code: 403' in error_str.lower():
                    try:
                        import requests as _requests
                        # Find user in Supabase by email to get their ID
                        _headers = {
                            'apikey': os.environ.get('SUPABASE_SERVICE_ROLE_KEY'),
                            'Authorization': f"Bearer {os.environ.get('SUPABASE_SERVICE_ROLE_KEY')}",
                            'Content-Type': 'application/json'
                        }
                        _list = _requests.get(
                            f"{os.environ.get('SUPABASE_URL')}/auth/v1/admin/users",
                            headers=_headers
                        ).json()
                        supabase_uid = next((u['id'] for u in _list.get('users', []) if u.get('email') == email), None)
                        if supabase_uid:
                            _requests.put(
                                f"{os.environ.get('SUPABASE_URL')}/auth/v1/admin/users/{supabase_uid}",
                                headers=_headers, json={'email_confirm': True}
                            )
                            auth_response = supabase.auth.sign_in_with_password({'email': email, 'password': password})
                            if auth_response.user:
                                user.supabase_user_id = auth_response.user.id
                                db.session.commit()
                            else:
                                flash('Invalid email or password.', 'danger')
                                return redirect(url_for('login'))
                        else:
                            flash('Invalid email or password.', 'danger')
                            return redirect(url_for('login'))
                    except Exception:
                        flash('Invalid email or password.', 'danger')
                        return redirect(url_for('login'))
                else:
                    flash('Invalid email or password.', 'danger')
                    return redirect(url_for('login'))
        else:
            # Fallback to local password check (for admin and old accounts)
            if not user.check_password(password):
                flash('Invalid email or password.', 'danger')
                return redirect(url_for('login'))
        
        # Check if email is verified (skip for admin)
        if not user.is_verified and user.role != 'admin':
            flash('Please verify your email before logging in. Check your inbox for the verification code.', 'warning')
            return redirect(url_for('verify_email_code', user_id=user.id))
        
        # Check if account is suspended
        if user.is_suspended:
            reason = user.suspension_reason or 'No reason provided'
            flash(f'Your account has been suspended. Reason: {reason}', 'danger')
            return redirect(url_for('login'))
        
        # Set session information
        session['user_id'] = user.id
        session['role'] = user.role
        session['profile_picture'] = user.profile_picture
        session['is_support_agent'] = user.is_support_agent if hasattr(user, 'is_support_agent') else False
        if user.supabase_user_id:
            session['supabase_user_id'] = user.supabase_user_id
        
        # Update last activity
        user.last_activity = get_philippines_time()
        db.session.commit()
        
        log_action('USER_LOGIN', 'User', str(user.id))
        
        # Redirect based on role
        if user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif user.role == 'seller':
            if not user.is_approved:
                return redirect(url_for('pending_approval'))
            return redirect(url_for('seller_dashboard'))
        elif user.role == 'courier':
            if not user.is_approved:
                return redirect(url_for('pending_approval'))
            return redirect(url_for('courier_dashboard'))
        elif user.role == 'rider':
            if not user.is_approved:
                return redirect(url_for('pending_approval'))
            return redirect(url_for('rider_dashboard'))
        else:
            return redirect(url_for('index'))
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    # Sign out from Supabase
    try:
        if supabase and session.get('supabase_user_id'):
            supabase.auth.sign_out()
    except Exception as e:
        print(f"Supabase logout error: {e}")
    
    log_action('USER_LOGOUT', 'User', str(session.get('user_id')) if session.get('user_id') else None)
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))


@app.route('/pending-approval')
@login_required
def pending_approval():
    return render_template('pending_approval.html')


# ==================== CUSTOMER ROUTES ====================

@app.route('/browse')
def browse():
    category_id = request.args.get('category')
    search = request.args.get('search', '')
    
    query = Product.query.filter_by(is_active=True)
    
    if category_id:
        query = query.filter_by(category_id=category_id)
    
    if search:
        query = query.filter(Product.name.like(f'%{search}%'))
    
    products = query.all()
    categories = Category.query.all()
    
    return render_template('browse.html', products=products, categories=categories)


@app.route('/cart')
@login_required
def view_cart():
    """View cart with transaction-based cart items"""
    user_id = session['user_id']
    
    # Get all cart items for this user (each entry is a separate transaction)
    cart_items_db = CartItem.query.filter_by(user_id=user_id).order_by(CartItem.created_at.desc()).all()
    
    cart_items = []
    total = 0
    has_stock_error = False
    
    for cart_item in cart_items_db:
        product = cart_item.product
        if product:
            subtotal = float(product.price) * cart_item.quantity
            
            # Check if quantity exceeds stock
            exceeds_stock = cart_item.quantity > product.stock
            if exceeds_stock:
                has_stock_error = True
            
            cart_items.append({
                'cart_item_id': cart_item.id,
                'product': product,
                'quantity': cart_item.quantity,
                'subtotal': subtotal,
                'exceeds_stock': exceeds_stock,
                'created_at': cart_item.created_at
            })
            total += subtotal
    
    return render_template('cart.html', cart_items=cart_items, total=total, has_stock_error=has_stock_error)


@app.route('/cart/add/<product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    """Add product to cart with stock validation"""
    try:
        import uuid as uuid_lib
        product_id = uuid_lib.UUID(product_id)
    except (ValueError, AttributeError):
        flash('Invalid product ID.', 'danger')
        return redirect(url_for('browse'))
    product = Product.query.get_or_404(product_id)
    quantity = int(request.form.get('quantity', 1))
    user_id = session['user_id']
    
    # Validate quantity
    if quantity < 1:
        flash('Quantity must be at least 1.', 'danger')
        return redirect(request.referrer or url_for('browse'))
    
    # Check if product is active and in stock
    if not product.is_active:
        flash('This product is no longer available.', 'danger')
        return redirect(url_for('browse'))
    
    if product.stock == 0:
        flash('This product is out of stock.', 'danger')
        return redirect(request.referrer or url_for('browse'))
    
    # Validate: requested quantity should not exceed stock
    if quantity > product.stock:
        flash(f'Only {product.stock} units available. Please adjust quantity.', 'danger')
        return redirect(request.referrer or url_for('browse'))
    
    # Check total quantity in cart (all cart items for this product)
    existing_cart_items = CartItem.query.filter_by(user_id=user_id, product_id=product_id).all()
    total_in_cart = sum(item.quantity for item in existing_cart_items)
    
    # Check if adding this quantity would exceed stock
    if total_in_cart + quantity > product.stock:
        flash(f'Cannot add {quantity} more. You already have {total_in_cart} in cart. Only {product.stock} available.', 'warning')
        return redirect(request.referrer or url_for('browse'))
    
    # Create new cart item (transaction-based - each add creates separate entry)
    cart_item = CartItem(
        user_id=user_id,
        product_id=product_id,
        quantity=quantity
    )
    db.session.add(cart_item)
    db.session.commit()
    
    flash(f'{product.name} (x{quantity}) added to cart!', 'success')
    return redirect(request.referrer or url_for('browse'))


@app.route('/buy-now/<product_id>', methods=['POST'])
@login_required
@role_required('customer')
def buy_now(product_id):
    """Buy Now - Skip cart and go directly to checkout with this product"""
    try:
        import uuid as uuid_lib
        product_id = uuid_lib.UUID(product_id)
    except (ValueError, AttributeError):
        flash('Invalid product ID.', 'danger')
        return redirect(url_for('browse'))
    product = Product.query.get_or_404(product_id)
    quantity = int(request.form.get('quantity', 1))
    
    # Validate stock
    if product.stock < quantity:
        flash(f'Only {product.stock} units available.', 'danger')
        return redirect(url_for('product_detail', product_id=product_id))
    
    if product.stock == 0:
        flash('This product is out of stock.', 'danger')
        return redirect(url_for('product_detail', product_id=product_id))
    
    # Create a temporary cart for immediate checkout
    session['buy_now_cart'] = {str(product_id): quantity}
    
    return redirect(url_for('checkout'))


@app.route('/cart/remove/<cart_item_id>')
@login_required
def remove_from_cart(cart_item_id):
    """Remove a specific cart item transaction"""
    try:
        import uuid as uuid_lib
        cart_item_id = uuid_lib.UUID(cart_item_id)
    except (ValueError, AttributeError):
        flash('Invalid cart item ID.', 'danger')
        return redirect(url_for('view_cart'))
    user_id = session['user_id']
    cart_item = CartItem.query.filter_by(id=cart_item_id, user_id=user_id).first_or_404()
    
    db.session.delete(cart_item)
    db.session.commit()
    
    flash('Item removed from cart.', 'info')
    return redirect(url_for('view_cart'))


@app.route('/cart/update/<cart_item_id>', methods=['POST'])
@login_required
def update_cart_quantity(cart_item_id):
    """Update quantity of a specific cart item with stock validation"""
    try:
        import uuid as uuid_lib
        cart_item_id = uuid_lib.UUID(cart_item_id)
    except (ValueError, AttributeError):
        flash('Invalid cart item ID.', 'danger')
        return redirect(url_for('view_cart'))
    user_id = session['user_id']
    cart_item = CartItem.query.filter_by(id=cart_item_id, user_id=user_id).first_or_404()
    product = cart_item.product
    new_quantity = int(request.form.get('quantity', 1))
    
    # Validate quantity
    if new_quantity < 1:
        flash('Quantity must be at least 1.', 'warning')
        return redirect(url_for('view_cart'))
    
    # Validate against stock
    if new_quantity > product.stock:
        flash(f'Only {product.stock} units available for {product.name}.', 'warning')
        return redirect(url_for('view_cart'))
    
    # Update the cart item
    cart_item.quantity = new_quantity
    db.session.commit()
    
    flash(f'Updated quantity for {product.name}.', 'success')
    return redirect(url_for('view_cart'))


@app.route('/customer/address/add', methods=['POST'])
@login_required
@role_required('customer')
def add_address():
    label = request.form.get('label')
    full_address = request.form.get('full_address')
    city = request.form.get('city') or request.form.get('municipality')
    postal_code = request.form.get('postal_code')
    province = request.form.get('province')
    municipality = request.form.get('municipality')
    region = request.form.get('region')
    barangay = request.form.get('barangay')
    is_default = request.form.get('is_default') == '1'
    redirect_to = request.form.get('redirect_to', 'checkout')
    
    # If this is set as default, unset other defaults
    if is_default:
        Address.query.filter_by(user_id=session['user_id'], is_default=True).update({'is_default': False})
    
    # If this is the first address, make it default
    if Address.query.filter_by(user_id=session['user_id']).count() == 0:
        is_default = True
    
    address = Address(
        user_id=session['user_id'],
        label=label,
        full_address=full_address,
        city=city,
        postal_code=postal_code,
        province=province,
        municipality=municipality,
        region=region,
        barangay=barangay,
        is_default=is_default
    )
    
    db.session.add(address)
    db.session.commit()
    
    log_action('ADDRESS_ADDED', 'Address', str(address.id), f'Added {label} address')
    flash('Delivery address added successfully!', 'success')
    
    if redirect_to == 'profile':
        return redirect(url_for('customer_profile'))
    return redirect(url_for('checkout'))


@app.route('/customer/profile')
@login_required
@role_required('customer')
def customer_profile():
    user = User.query.get(session['user_id'])
    addresses = Address.query.filter_by(user_id=session['user_id']).all()
    return render_template('customer_profile.html', current_user=user, addresses=addresses)


@app.route('/customer/address/<address_id>/set-default', methods=['POST'])
@login_required
@role_required('customer')
def set_default_address(address_id):
    try:
        import uuid as uuid_lib
        address_id = uuid_lib.UUID(address_id)
    except (ValueError, AttributeError):
        flash('Invalid address ID.', 'danger')
        return redirect(url_for('customer_profile'))
    # Unset all defaults
    Address.query.filter_by(user_id=session['user_id']).update({'is_default': False})
    
    # Set new default
    address = Address.query.get_or_404(address_id)
    if address.user_id != session['user_id']:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('customer_profile'))
    
    address.is_default = True
    db.session.commit()
    
    log_action('ADDRESS_SET_DEFAULT', 'Address', str(address.id))
    flash(f'{address.label} address set as default.', 'success')
    return redirect(url_for('customer_profile'))


@app.route('/customer/address/<address_id>/delete', methods=['POST'])
@login_required
@role_required('customer')
def delete_address(address_id):
    try:
        import uuid as uuid_lib
        address_id = uuid_lib.UUID(address_id)
    except (ValueError, AttributeError):
        flash('Invalid address ID.', 'danger')
        return redirect(url_for('customer_profile'))
    address = Address.query.get_or_404(address_id)
    
    if address.user_id != session['user_id']:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('customer_profile'))
    
    # Check if any orders reference this address
    order_count = Order.query.filter_by(delivery_address_id=address_id).count()
    if order_count > 0:
        flash(f'Cannot delete this address - it is referenced by {order_count} order(s). Please use a different address for future orders.', 'warning')
        return redirect(url_for('customer_profile'))
    
    was_default = address.is_default
    label = address.label
    
    db.session.delete(address)
    
    # If deleted address was default, set another as default
    if was_default:
        new_default = Address.query.filter_by(user_id=session['user_id']).first()
        if new_default:
            new_default.is_default = True
    
    db.session.commit()
    
    log_action('ADDRESS_DELETED', 'Address', str(address_id), f'Deleted {label} address')
    flash('Address deleted successfully.', 'success')
    return redirect(url_for('customer_profile'))


@app.route('/profile/upload-picture', methods=['POST'])
@login_required
def upload_profile_picture():
    """Upload profile picture for any user type (customer, seller, rider, courier)"""
    user = User.query.get(session['user_id'])
    
    if 'profile_picture' not in request.files:
        flash('No file selected.', 'warning')
        return redirect(request.referrer or url_for('index'))
    
    file = request.files['profile_picture']
    
    if file.filename == '':
        flash('No file selected.', 'warning')
        return redirect(request.referrer or url_for('index'))
    
    if file and allowed_file(file.filename):
        # Validate file size (max 5MB)
        file.seek(0, 2)  # Seek to end of file
        file_size = file.tell()  # Get file size
        file.seek(0)  # Reset to beginning
        
        max_size = 5 * 1024 * 1024  # 5MB
        if file_size > max_size:
            flash('File size must be less than 5MB.', 'danger')
            return redirect(request.referrer or url_for('index'))
        
        # Save new profile picture
        filename = secure_filename(file.filename)
        unique_filename = f"profile_{user.role}_{user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
        file_path = f"users/profile_pictures/{unique_filename}"
        success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
        if success:
            user.profile_picture = result  # Store the public URL
            db.session.commit()
            # Update session with new profile picture
            session['profile_picture'] = result
            log_action('PROFILE_PICTURE_UPLOADED', 'User', str(user.id), f'Uploaded profile picture')
            flash('Profile picture updated successfully!', 'success')
        else:
            flash(f'Error uploading profile picture: {result}', 'danger')
    else:
        flash('Invalid file type. Please upload an image (PNG, JPG, JPEG, GIF, WEBP).', 'danger')
    
    # Redirect based on user role
    if user.role == 'customer':
        return redirect(url_for('customer_profile'))
    elif user.role == 'seller':
        return redirect(url_for('seller_dashboard'))
    elif user.role in ['rider', 'courier']:
        return redirect(url_for('rider_dashboard'))
    else:
        return redirect(url_for('index'))


@app.route('/profile/delete-picture', methods=['POST'])
@login_required
def delete_profile_picture():
    """Delete profile picture"""
    user = User.query.get(session['user_id'])
    
    if user.profile_picture:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], user.profile_picture)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Error deleting profile picture: {e}")
        
        user.profile_picture = None
        db.session.commit()
        
        # Update session to remove profile picture
        session['profile_picture'] = None
        
        log_action('PROFILE_PICTURE_DELETED', 'User', str(user.id), 'Deleted profile picture')
        flash('Profile picture removed successfully.', 'success')
    else:
        flash('No profile picture to remove.', 'info')
    
    return redirect(request.referrer or url_for('index'))



@app.route('/checkout', methods=['GET', 'POST'])
@login_required
@role_required('customer')
def checkout():
    user_id = session['user_id']
    
    # Check if this is a Buy Now transaction
    buy_now_cart = session.get('buy_now_cart', None)
    
    if buy_now_cart:
        # Buy Now: Create temporary cart items list
        cart_items_db = []
        for product_id_str, quantity in buy_now_cart.items():
            product = Product.query.get(product_id_str)
            if product:
                # Create a temporary cart item object (not saved to database)
                class TempCartItem:
                    def __init__(self, product, quantity):
                        self.product = product
                        self.quantity = quantity
                        self.id = f"buy_now_{product.id}"
                
                cart_items_db.append(TempCartItem(product, quantity))
    else:
        # Regular cart checkout: Handle selective checkout from cart (POST with selected_items)
        selected_item_ids = request.form.get('selected_items', '').strip()
        
        # If coming from cart with selected items
        if request.method == 'POST' and selected_item_ids:
            # Store selected items in session for GET request
            session['selected_cart_items'] = selected_item_ids
            return redirect(url_for('checkout'))
        
        # Get selected items from session or all cart items
        if 'selected_cart_items' in session and session['selected_cart_items']:
            selected_ids = [id.strip() for id in session['selected_cart_items'].split(',') if id.strip()]
            cart_items_db = CartItem.query.filter(
                CartItem.user_id == user_id,
                CartItem.id.in_(selected_ids)
            ).all()
        else:
            # Default to all cart items (for backward compatibility)
            cart_items_db = CartItem.query.filter_by(user_id=user_id).all()
    
    if not cart_items_db:
        flash('Your cart is empty or no items selected.', 'warning')
        return redirect(url_for('browse'))
    
    # Check if any selected item exceeds stock before allowing checkout
    has_stock_error = False
    for cart_item in cart_items_db:
        if cart_item.quantity > cart_item.product.stock:
            has_stock_error = True
            flash(f'{cart_item.product.name} exceeds available stock.', 'danger')
    
    if has_stock_error:
        # Clear selection and redirect
        session.pop('selected_cart_items', None)
        session.pop('buy_now_cart', None)
        return redirect(url_for('view_cart'))
    
    addresses = Address.query.filter_by(user_id=user_id).all()
    
    if request.method == 'POST' and request.form.get('address_id'):
        address_id = request.form.get('address_id')
        
        if not address_id:
            flash('Please select a delivery address.', 'warning')
            return redirect(url_for('checkout'))
        
        # Get delivery address to calculate delivery fee
        delivery_address = Address.query.get(address_id)
        if not delivery_address or delivery_address.user_id != user_id:
            flash('Invalid delivery address.', 'danger')
            return redirect(url_for('checkout'))
        
        # Validate stock availability BEFORE creating orders
        for cart_item in cart_items_db:
            product = cart_item.product
            if not product:
                flash(f'Product not found.', 'danger')
                session.pop('selected_cart_items', None)
                session.pop('buy_now_cart', None)
                return redirect(url_for('view_cart'))
            
            if product.stock < cart_item.quantity:
                flash(f'Insufficient stock for {product.name}. Only {product.stock} available.', 'danger')
                session.pop('selected_cart_items', None)
                session.pop('buy_now_cart', None)
                return redirect(url_for('view_cart'))
            
            if product.stock == 0:
                flash(f'{product.name} is out of stock.', 'danger')
                session.pop('selected_cart_items', None)
                session.pop('buy_now_cart', None)
                return redirect(url_for('view_cart'))
        
        # Calculate delivery fee based on seller and customer island group distance
        customer_zone = get_island_group(delivery_address.region)
        
        # Group items by shop
        shop_orders = {}
        for cart_item in cart_items_db:
            product = cart_item.product
            if product and product.is_active:
                if product.shop_id not in shop_orders:
                    shop_orders[product.shop_id] = []
                shop_orders[product.shop_id].append((product, cart_item.quantity))
        
        # Create order for each shop
        for shop_id, items in shop_orders.items():
            subtotal = sum([float(p.price) * q for p, q in items])
            
            # Calculate delivery fee based on seller vs customer island group
            shop = Shop.query.get(shop_id)
            seller = User.query.get(shop.seller_id) if shop else None
            seller_region = seller.region if seller and seller.region else None
            if not seller_region:
                seller_addr = Address.query.filter_by(user_id=shop.seller_id).first() if shop else None
                seller_region = seller_addr.region if seller_addr else None
            delivery_fee = calculate_delivery_fee(seller_region, delivery_address.region)
            
            # Calculate commission on subtotal (not including delivery fee) - 5% per transaction
            commission = subtotal * 0.05
            seller_amount = subtotal - commission
            total_amount = subtotal + delivery_fee
            
            # Calculate courier/rider earnings split
            courier_earnings = delivery_fee * 0.60  # 60% to courier
            rider_earnings = delivery_fee * 0.40  # 40% to rider
            
            order = Order(
                order_number=generate_order_number(),
                customer_id=user_id,
                shop_id=shop_id,
                delivery_address_id=address_id,
                subtotal=subtotal,
                delivery_fee=delivery_fee,
                total_amount=total_amount,
                commission_rate=5.00,
                commission_amount=commission,
                seller_amount=seller_amount,
                courier_earnings=courier_earnings,
                rider_earnings=rider_earnings,
                status='PENDING_PAYMENT'
            )
            db.session.add(order)
            db.session.flush()
            
            # Create order items and DEDUCT STOCK
            for product, quantity in items:
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=quantity,
                    price=product.price
                )
                db.session.add(order_item)
                
                # DEDUCT STOCK IMMEDIATELY upon order creation
                product.stock -= quantity
                
                log_action('STOCK_DEDUCTED', 'Product', str(product.id), 
                          f'Deducted {quantity} units for order {order.order_number}')
            
            log_action('ORDER_CREATED', 'Order', str(order.id), f'Order {order.order_number}')
        
        # Clear cart items based on checkout type
        if buy_now_cart:
            # Clear Buy Now session
            session.pop('buy_now_cart', None)
        else:
            # Clear only the checked-out cart items from database
            for cart_item in cart_items_db:
                db.session.delete(cart_item)
            db.session.commit()
            
            # Clear selected items from session
            session.pop('selected_cart_items', None)
        
        # Send confirmation email + notifications
        user = User.query.get(user_id)
        send_email(
            user.email,
            'Order Confirmation',
            f'Your orders have been placed successfully!'
        )
        for shop_id_key in shop_orders:
            placed_order = Order.query.filter_by(customer_id=user_id, shop_id=shop_id_key).order_by(Order.created_at.desc()).first()
            if placed_order:
                create_notification(user_id, 'Order Placed', f'Your order {placed_order.order_number} has been placed successfully.', 'success', placed_order.id)
                shop_obj = Shop.query.get(shop_id_key)
                if shop_obj:
                    customer = User.query.get(user_id)
                    item_count = len(placed_order.items)
                    # Create notification for seller
                    create_notification(
                        shop_obj.seller_id, 
                        'New Order Received!', 
                        f'You have a new order {placed_order.order_number} from {customer.full_name or customer.email} ({item_count} item{"s" if item_count != 1 else ""}). Total: ₱{placed_order.total_amount:.2f}. Please prepare the order for pickup.', 
                        'info', 
                        placed_order.id
                    )
                    # Send email notification to seller
                    send_email(
                        shop_obj.owner.email,
                        'New Order Received - Epicuremart',
                        f'You have received a new order!\n\n'
                        f'Order Number: {placed_order.order_number}\n'
                        f'Customer: {customer.full_name or customer.email}\n'
                        f'Items: {item_count}\n'
                        f'Total Amount: ₱{placed_order.total_amount:.2f}\n\n'
                        f'Please log in to your seller dashboard to view the order details and prepare it for pickup.'
                    )
        db.session.commit()
        
        flash('Order(s) placed successfully!', 'success')
        return redirect(url_for('customer_orders'))
    
    # Calculate cart preview with delivery fee estimate
    cart_items = []
    subtotal = 0
    for cart_item in cart_items_db:
        product = cart_item.product
        if product:
            item_total = float(product.price) * cart_item.quantity
            subtotal += item_total
            cart_items.append({
                'product': product,
                'quantity': cart_item.quantity,
                'subtotal': item_total
            })
    
    # Get delivery fee estimate based on seller vs customer island group
    default_address = Address.query.filter_by(
        user_id=user_id,
        is_default=True
    ).first()

    estimated_delivery_fee = 50.00  # Default (same island)
    if default_address and cart_items_db:
        first_product = cart_items_db[0].product
        if first_product:
            first_shop = Shop.query.get(first_product.shop_id)
            if first_shop:
                seller = User.query.get(first_shop.seller_id)
                seller_region = seller.region if seller and seller.region else None
                if not seller_region:
                    seller_addr = Address.query.filter_by(user_id=first_shop.seller_id).first()
                    seller_region = seller_addr.region if seller_addr else None
                estimated_delivery_fee = calculate_delivery_fee(seller_region, default_address.region)
    
    estimated_total = subtotal + estimated_delivery_fee
    
    return render_template('checkout.html', 
        addresses=addresses,
        cart_items=cart_items,
        subtotal=subtotal,
        estimated_delivery_fee=estimated_delivery_fee,
        estimated_total=estimated_total
    )


@app.route('/customer/orders')
@login_required
@role_required('customer')
def customer_orders():
    orders = Order.query.filter_by(customer_id=session['user_id']).order_by(Order.created_at.desc()).all()
    return render_template('customer_orders.html', orders=orders)


@app.route('/customer/order/<order_id>')
@login_required
@role_required('customer')
def customer_order_detail(order_id):
    try:
        import uuid as uuid_lib
        order_id = uuid_lib.UUID(order_id)
    except (ValueError, AttributeError):
        flash('Invalid order ID.', 'danger')
        return redirect(url_for('customer_orders'))
    order = Order.query.get_or_404(order_id)
    
    if order.customer_id != session['user_id']:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('customer_orders'))
    
    # Generate QR code for delivery confirmation
    qr_data = None
    if order.delivery_token:
        qr_data = generate_qr_code(order.delivery_token)
    
    # Check which products can be reviewed
    reviewable_items = []
    if order.status == 'DELIVERED':
        for item in order.items:
            existing_review = ProductReview.query.filter_by(
                product_id=item.product_id,
                user_id=session['user_id'],
                order_id=order.id
            ).first()
            reviewable_items.append({
                'item': item,
                'has_review': existing_review is not None,
                'review': existing_review
            })
    
    # Get rider information if rider is assigned
    rider_info = None
    rider_rating = None
    has_rider_feedback = False
    if order.rider_id:
        rider = User.query.get(order.rider_id)
        feedbacks = RiderFeedback.query.filter_by(rider_id=order.rider_id).all()
        avg_rating = sum([f.rating for f in feedbacks]) / len(feedbacks) if feedbacks else 0
        recent_feedbacks = RiderFeedback.query.filter_by(rider_id=order.rider_id).order_by(RiderFeedback.created_at.desc()).limit(3).all()
        
        rider_info = {
            'id': rider.id,
            'full_name': rider.full_name or rider.email,
            'email': rider.email,
            'phone': rider.phone,
            'profile_picture': rider.profile_picture,
            'avg_rating': round(avg_rating, 1),
            'total_feedbacks': len(feedbacks),
            'recent_feedbacks': recent_feedbacks
        }
        
        # Check if customer already gave feedback for this order
        has_rider_feedback = RiderFeedback.query.filter_by(
            order_id=order_id,
            customer_id=session['user_id']
        ).first() is not None
    
    # Get courier information if courier is assigned
    courier_info = None
    if order.courier_id:
        courier = User.query.get(order.courier_id)
        courier_info = {
            'id': courier.id,
            'company_name': courier.company_name,
            'full_name': courier.full_name or courier.email,
            'email': courier.email,
            'phone': courier.phone,
            'profile_picture': courier.profile_picture,
            'vehicle_type': courier.vehicle_type
        }
    
    return render_template('customer_order_detail.html', 
        order=order, 
        qr_data=qr_data,
        reviewable_items=reviewable_items,
        rider_info=rider_info,
        courier_info=courier_info,
        has_rider_feedback=has_rider_feedback
    )


@app.route('/product/<product_id>/review', methods=['POST'])
@login_required
@role_required('customer')
def add_product_review(product_id):
    try:
        import uuid as uuid_lib
        product_id = uuid_lib.UUID(product_id)
    except (ValueError, AttributeError):
        flash('Invalid product ID.', 'danger')
        return redirect(url_for('browse'))
    order_id = request.form.get('order_id')
    rating = request.form.get('rating')
    review_text = request.form.get('review_text')
    
    # Verify customer bought this product in this order
    order = Order.query.get_or_404(order_id)
    if order.customer_id != session['user_id'] or order.status != 'DELIVERED':
        flash('You can only review products from delivered orders.', 'danger')
        return redirect(url_for('customer_order_detail', order_id=order_id))
    
    # Check if already reviewed
    existing = ProductReview.query.filter_by(
        product_id=product_id,
        user_id=session['user_id'],
        order_id=order_id
    ).first()
    
    if existing:
        flash('You have already reviewed this product.', 'warning')
        return redirect(url_for('customer_order_detail', order_id=order_id))
    
    uploaded_images = []
    for i in range(1, 6):  # Support up to 5 images
        image_key = f'review_image_{i}'
        if image_key in request.files:
            file = request.files[image_key]
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"review_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}_{filename}"
                file_path = f"reviews/images/{filename}"
                success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                if success:
                    uploaded_images.append(result)  # Store the public URL
    
    review = ProductReview(
        product_id=product_id,
        user_id=session['user_id'],
        order_id=order_id,
        rating=int(rating),
        review_text=review_text,
        review_images=",".join(uploaded_images)
    )
    
    db.session.add(review)
    db.session.commit()
    
    log_action('PRODUCT_REVIEWED', 'ProductReview', str(review.id), f'{rating} stars')
    flash('Thank you for your review!', 'success')
    return redirect(url_for('customer_order_detail', order_id=order_id))


@app.route('/product/<product_id>')
def product_detail(product_id):
    try:
        import uuid as uuid_lib
        product_id = uuid_lib.UUID(product_id)
    except (ValueError, AttributeError):
        flash('Invalid product ID.', 'danger')
        return redirect(url_for('browse'))
    product = Product.query.get_or_404(product_id)
    
    # Calculate average rating
    reviews = ProductReview.query.filter_by(product_id=product_id).all()
    avg_rating = sum([r.rating for r in reviews]) / len(reviews) if reviews else 0
    rating_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for review in reviews:
        rating_counts[review.rating] += 1
    
    return render_template('product_detail.html',
        product=product,
        reviews=reviews,
        avg_rating=avg_rating,
        rating_counts=rating_counts,
        total_reviews=len(reviews)
    )


@app.route('/order/<order_id>/rider-feedback', methods=['POST'])
@login_required
@role_required('customer')
def add_rider_feedback(order_id):
    """Add feedback for a rider after delivery"""
    try:
        import uuid as uuid_lib
        order_id = uuid_lib.UUID(order_id)
    except (ValueError, AttributeError):
        flash('Invalid order ID.', 'danger')
        return redirect(url_for('customer_orders'))
    order = Order.query.get_or_404(order_id)
    
    # Verify customer owns this order
    if order.customer_id != session['user_id']:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('customer_orders'))
    
    # Verify order is delivered and has a rider
    if order.status != 'DELIVERED':
        flash('You can only rate the rider after delivery.', 'warning')
        return redirect(url_for('customer_order_detail', order_id=order_id))
    
    if not order.rider_id:
        flash('No rider assigned to this order.', 'warning')
        return redirect(url_for('customer_order_detail', order_id=order_id))
    
    # Check if already reviewed
    existing = RiderFeedback.query.filter_by(
        order_id=order_id,
        customer_id=session['user_id']
    ).first()
    
    if existing:
        flash('You have already rated this rider.', 'warning')
        return redirect(url_for('customer_order_detail', order_id=order_id))
    
    rating = request.form.get('rating')
    feedback_text = request.form.get('feedback_text', '')
    
    if not rating:
        flash('Please provide a rating.', 'danger')
        return redirect(url_for('customer_order_detail', order_id=order_id))
    
    feedback = RiderFeedback(
        rider_id=order.rider_id,
        customer_id=session['user_id'],
        order_id=order_id,
        rating=int(rating),
        feedback_text=feedback_text
    )
    
    db.session.add(feedback)
    db.session.commit()
    
    log_action('RIDER_FEEDBACK_ADDED', 'RiderFeedback', str(feedback.id), f'{rating} stars for rider {order.rider_id}')
    flash('Thank you for rating the rider!', 'success')
    return redirect(url_for('customer_order_detail', order_id=order_id))


@app.route('/api/rider/<int:rider_id>/rating')
def get_rider_rating(rider_id):
    """Get rider's average rating and recent feedback"""
    rider = User.query.get_or_404(rider_id)
    
    if rider.role != 'rider':
        return jsonify({'error': 'Not a rider'}), 400
    
    feedbacks = RiderFeedback.query.filter_by(rider_id=rider_id).order_by(RiderFeedback.created_at.desc()).all()
    
    avg_rating = sum([f.rating for f in feedbacks]) / len(feedbacks) if feedbacks else 0
    total_feedbacks = len(feedbacks)
    
    recent_feedbacks = []
    for f in feedbacks[:5]:  # Get last 5 feedback items
        recent_feedbacks.append({
            'rating': f.rating,
            'feedback_text': f.feedback_text,
            'created_at': f.created_at.strftime('%B %d, %Y')
        })
    
    return jsonify({
        'avg_rating': round(avg_rating, 1),
        'total_feedbacks': total_feedbacks,
        'recent_feedbacks': recent_feedbacks
    })


@app.route('/api/riders-by-courier/<path:courier_id>')
def get_riders_by_courier(courier_id):
    """Get list of riders associated with a specific courier company"""
    try:
        import uuid as uuid_lib
        courier_id = uuid_lib.UUID(courier_id)
    except (ValueError, AttributeError):
        return jsonify({'riders': [], 'error': 'Invalid courier ID'}), 400
    
    riders = User.query.filter_by(
        role='rider',
        is_approved=True,
        courier_id=courier_id
    ).all()
    
    riders_data = []
    for rider in riders:
        riders_data.append({
            'id': str(rider.id),
            'full_name': rider.full_name or rider.email,
            'email': rider.email,
            'phone': rider.phone,
            'vehicle_type': rider.vehicle_type
        })
    
    return jsonify({'riders': riders_data})


@app.route('/api/calculate-delivery-fee', methods=['POST'])
@login_required
@role_required('customer')
def api_calculate_delivery_fee():
    """Calculate delivery fee based on selected address and cart items"""
    data = request.get_json()
    address_id = data.get('address_id')
    
    if not address_id:
        return jsonify({'error': 'Address ID required'}), 400
    
    try:
        import uuid as uuid_lib
        address_id = uuid_lib.UUID(address_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid address ID'}), 400
    
    # Get the selected address
    address = Address.query.filter_by(id=address_id, user_id=session['user_id']).first()
    if not address:
        return jsonify({'error': 'Address not found'}), 404
    
    # Get cart items (check for buy now or regular cart)
    user_id = session['user_id']
    buy_now_cart = session.get('buy_now_cart', None)
    
    if buy_now_cart:
        # Buy Now: Create temporary cart items list
        cart_items_db = []
        for product_id_str, quantity in buy_now_cart.items():
            product = Product.query.get(product_id_str)
            if product:
                class TempCartItem:
                    def __init__(self, product, quantity):
                        self.product = product
                        self.quantity = quantity
                cart_items_db.append(TempCartItem(product, quantity))
    else:
        # Regular cart checkout
        selected_item_ids = session.get('selected_cart_items', '')
        if selected_item_ids:
            selected_ids = [id.strip() for id in selected_item_ids.split(',') if id.strip()]
            cart_items_db = CartItem.query.filter(
                CartItem.user_id == user_id,
                CartItem.id.in_(selected_ids)
            ).all()
        else:
            cart_items_db = CartItem.query.filter_by(user_id=user_id).all()
    
    if not cart_items_db:
        return jsonify({'error': 'No items in cart'}), 400
    
    # Group items by shop and calculate delivery fees
    shop_delivery_fees = {}
    total_delivery_fee = 0
    
    # Group items by shop
    shop_orders = {}
    for cart_item in cart_items_db:
        product = cart_item.product
        if product and product.is_active:
            if product.shop_id not in shop_orders:
                shop_orders[product.shop_id] = []
            shop_orders[product.shop_id].append((product, cart_item.quantity))
    
    # Calculate delivery fee for each shop
    for shop_id, items in shop_orders.items():
        shop = Shop.query.get(shop_id)
        if not shop:
            continue
            
        # Get seller's region
        seller = User.query.get(shop.seller_id)
        seller_region = seller.region if seller and seller.region else None
        if not seller_region:
            seller_addr = Address.query.filter_by(user_id=shop.seller_id).first()
            seller_region = seller_addr.region if seller_addr else None
        
        # Calculate delivery fee based on seller vs customer island group
        delivery_fee = calculate_delivery_fee(seller_region, address.region)
        shop_delivery_fees[str(shop_id)] = {
            'shop_name': shop.name,
            'delivery_fee': float(delivery_fee)
        }
        total_delivery_fee += delivery_fee
    
    # Calculate subtotal
    subtotal = sum([float(item.product.price) * item.quantity for item in cart_items_db])
    total_amount = subtotal + total_delivery_fee
    
    return jsonify({
        'success': True,
        'subtotal': float(subtotal),
        'delivery_fee': float(total_delivery_fee),
        'total': float(total_amount),
        'shop_fees': shop_delivery_fees
    })
    total_feedbacks = len(feedbacks)
    
    recent_feedbacks = []
    for f in feedbacks[:5]:  # Get last 5 feedback items
        recent_feedbacks.append({
            'rating': f.rating,
            'feedback_text': f.feedback_text,
            'created_at': f.created_at.strftime('%B %d, %Y')
        })
    
    return jsonify({
        'avg_rating': round(avg_rating, 1),
        'total_feedbacks': total_feedbacks,
        'recent_feedbacks': recent_feedbacks
    })


# @app.route('/customer/order/<int:order_id>')
# @login_required
# @role_required('customer')
# def customer_order_detail(order_id):
#     order = Order.query.get_or_404(order_id)
    
#     if order.customer_id != session['user_id']:
#         flash('Unauthorized access.', 'danger')
#         return redirect(url_for('customer_orders'))
    
#     # Generate QR code for delivery confirmation
#     qr_data = None
#     if order.delivery_token:
#         qr_data = generate_qr_code(order.delivery_token)
    
#     return render_template('customer_order_detail.html', order=order, qr_data=qr_data)


# ==================== SELLER ROUTES ====================

@app.route('/seller/dashboard')
@login_required
@role_required('seller')
def seller_dashboard():
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    user = User.query.get(session['user_id'])
    
    if not user.shop:
        return redirect(url_for('create_shop'))
    
    # Get filter parameters
    time_filter = request.args.get('filter', 'all')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    # Parse custom date range if provided
    now = datetime.utcnow()
    start_date = None
    end_date = None
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            time_filter = 'custom'
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD.', 'warning')
            start_date = None
            end_date = None
    
    # Calculate date range based on predefined filter if no custom range
    if not start_date and not end_date:
        if time_filter == 'day':
            start_date = now - timedelta(days=1)
        elif time_filter == 'week':
            start_date = now - timedelta(weeks=1)
        elif time_filter == 'month':
            start_date = now - timedelta(days=30)
        elif time_filter == 'year':
            start_date = now - timedelta(days=365)
        else:
            start_date = None
    
    # Statistics
    total_products = Product.query.filter_by(shop_id=user.shop.id).count()
    total_orders = Order.query.filter_by(shop_id=user.shop.id).count()
    pending_orders = Order.query.filter_by(
        shop_id=user.shop.id, 
        status='PENDING_PAYMENT'
    ).count()
    ready_orders = Order.query.filter_by(
        shop_id=user.shop.id, 
        status='READY_FOR_PICKUP'
    ).count()
    
    # Revenue calculations
    revenue_query = db.session.query(func.sum(Order.seller_amount))\
        .filter(Order.shop_id == user.shop.id, Order.status == 'DELIVERED')
    if start_date:
        revenue_query = revenue_query.filter(Order.created_at >= start_date)
    if end_date:
        revenue_query = revenue_query.filter(Order.created_at <= end_date)
    total_revenue = revenue_query.scalar() or 0
    
    # Total sales (before commission)
    sales_query = db.session.query(func.sum(Order.subtotal))\
        .filter(Order.shop_id == user.shop.id, Order.status == 'DELIVERED')
    if start_date:
        sales_query = sales_query.filter(Order.created_at >= start_date)
    if end_date:
        sales_query = sales_query.filter(Order.created_at <= end_date)
    total_sales = sales_query.scalar() or 0
    
    # Average order value
    avg_order_query = db.session.query(func.avg(Order.total_amount))\
        .filter(Order.shop_id == user.shop.id, Order.status == 'DELIVERED')
    if start_date:
        avg_order_query = avg_order_query.filter(Order.created_at >= start_date)
    if end_date:
        avg_order_query = avg_order_query.filter(Order.created_at <= end_date)
    avg_order_value = avg_order_query.scalar() or 0
    
    # Revenue data for chart
    revenue_chart_data = []
    if time_filter == 'day' or time_filter == 'week':
        # Daily data for last 7 days
        for i in range(6, -1, -1):
            date = now - timedelta(days=i)
            day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            daily_revenue = db.session.query(func.sum(Order.seller_amount))\
                .filter(Order.shop_id == user.shop.id,
                        Order.created_at >= day_start, 
                        Order.created_at < day_end,
                        Order.status == 'DELIVERED').scalar() or 0
            
            revenue_chart_data.append({
                'label': day_start.strftime('%b %d'),
                'value': float(daily_revenue)
            })
    elif time_filter == 'month':
        # Weekly data for last 4 weeks
        for i in range(3, -1, -1):
            week_start = now - timedelta(weeks=i+1)
            week_end = now - timedelta(weeks=i)
            
            weekly_revenue = db.session.query(func.sum(Order.seller_amount))\
                .filter(Order.shop_id == user.shop.id,
                        Order.created_at >= week_start, 
                        Order.created_at < week_end,
                        Order.status == 'DELIVERED').scalar() or 0
            
            revenue_chart_data.append({
                'label': f'Week {i+1}',
                'value': float(weekly_revenue)
            })
    else:
        # Monthly data for last 12 months
        for i in range(11, -1, -1):
            month_start = (now - timedelta(days=30*i)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if i == 0:
                month_end = now
            else:
                month_end = (now - timedelta(days=30*(i-1))).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            monthly_revenue = db.session.query(func.sum(Order.seller_amount))\
                .filter(Order.shop_id == user.shop.id,
                        Order.created_at >= month_start, 
                        Order.created_at < month_end,
                        Order.status == 'DELIVERED').scalar() or 0
            
            revenue_chart_data.append({
                'label': month_start.strftime('%b %Y'),
                'value': float(monthly_revenue)
            })
    
    # Top selling products
    top_products = db.session.query(
        Product.name, 
        func.sum(OrderItem.quantity).label('total_sold')
    ).join(OrderItem).join(Order)\
        .filter(Product.shop_id == user.shop.id, Order.status == 'DELIVERED')\
        .group_by(Product.id).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()
    
    recent_orders = Order.query.filter_by(shop_id=user.shop.id)\
        .order_by(Order.created_at.desc()).limit(5).all()
    
    # Withdrawal calculations (all time - for accurate accounting)
    # Total sales (subtotal) from delivered orders
    total_delivered_sales = db.session.query(func.sum(Order.subtotal))\
        .filter(Order.shop_id == user.shop.id, Order.status == 'DELIVERED').scalar() or 0
    
    # Commission calculation
    admin_commission = total_delivered_sales * Decimal('0.05')

    # Withdrawable amount
    withdrawable_amount = total_delivered_sales * Decimal('0.95')
    
    return render_template('seller_dashboard.html',
        shop=user.shop,
        total_products=total_products,
        total_orders=total_orders,
        pending_orders=pending_orders,
        ready_orders=ready_orders,
        total_revenue=total_revenue,
        total_sales=total_sales,
        avg_order_value=avg_order_value,
        revenue_chart_data=revenue_chart_data,
        top_products=top_products,
        time_filter=time_filter,
        # Withdrawal data
        total_delivered_sales=total_delivered_sales,
        admin_commission=admin_commission,
        withdrawable_amount=withdrawable_amount,
        start_date=start_date_str,
        end_date=end_date_str,
        recent_orders=recent_orders
    )


@app.route('/seller/sales-report')
@login_required
@role_required('seller')
def seller_sales_report():
    """Detailed sales report with all sections per spec"""
    user = User.query.get(session['user_id'])
    if not user.shop:
        return redirect(url_for('create_shop'))

    # Date range filter
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    start_date = None
    end_date = None
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    # Base queries
    base_q = Order.query.filter_by(shop_id=user.shop.id)
    if start_date:
        base_q = base_q.filter(Order.created_at >= start_date)
    if end_date:
        base_q = base_q.filter(Order.created_at <= end_date)

    delivered_q = base_q.filter(Order.status == 'DELIVERED')
    cancelled_q = base_q.filter(Order.status == 'CANCELLED')

    delivered_orders_list = delivered_q.order_by(Order.created_at.desc()).all()
    cancelled_orders_list = cancelled_q.all()

    # I. Report Overview
    reporting_period = None
    if start_date and end_date:
        reporting_period = f"{start_date.strftime('%B %d, %Y')} – {end_date.strftime('%B %d, %Y')}"
    elif delivered_orders_list:
        oldest = min(o.created_at for o in delivered_orders_list)
        newest = max(o.created_at for o in delivered_orders_list)
        reporting_period = f"{oldest.strftime('%B %d, %Y')} – {newest.strftime('%B %d, %Y')}"

    # II. Sales & Transactions
    gross_sales = sum(float(o.subtotal or 0) for o in delivered_orders_list)
    total_delivery_fees = sum(float(o.delivery_fee or 0) for o in delivered_orders_list)
    total_delivered = len(delivered_orders_list)
    total_commission = sum(float(o.commission_amount or 0) for o in delivered_orders_list)
    total_earnings = sum(float(o.seller_amount or 0) for o in delivered_orders_list)

    # III. Product Performance — aggregate across delivered orders
    product_stats = {}
    for order in delivered_orders_list:
        for item in order.items:
            pid = str(item.product_id)
            if pid not in product_stats:
                product_stats[pid] = {
                    'name': item.product.name if item.product else 'Unknown',
                    'qty_sold': 0,
                    'revenue': 0.0,
                    'stock': item.product.stock if item.product else 0,
                }
            product_stats[pid]['qty_sold'] += item.quantity
            product_stats[pid]['revenue'] += float(item.price or 0) * item.quantity
    product_performance = sorted(product_stats.values(), key=lambda x: x['qty_sold'], reverse=True)

    # IV. RTS / Cancellations
    rts_stats = {}
    for order in cancelled_orders_list:
        for item in order.items:
            pid = str(item.product_id)
            if pid not in rts_stats:
                rts_stats[pid] = {
                    'name': item.product.name if item.product else 'Unknown',
                    'qty_returned': 0,
                }
            rts_stats[pid]['qty_returned'] += item.quantity
    rts_list = sorted(rts_stats.values(), key=lambda x: x['qty_returned'], reverse=True)
    total_cancelled = len(cancelled_orders_list)

    # V. Net Profit = Gross Sales - COGS (COGS not stored; show formula note)
    # Net Profit shown on page as Gross Sales - Commission (platform deduction)
    net_profit = gross_sales - total_commission

    return render_template('seller_sales_report.html',
        shop=user.shop,
        reporting_period=reporting_period,
        start_date=start_date_str,
        end_date=end_date_str,
        gross_sales=gross_sales,
        total_delivered=total_delivered,
        total_delivery_fees=total_delivery_fees,
        total_commission=total_commission,
        total_earnings=total_earnings,
        net_profit=net_profit,
        product_performance=product_performance,
        rts_list=rts_list,
        total_cancelled=total_cancelled,
        generated_on=datetime.now().strftime('%B %d, %Y %I:%M %p'),
        # keep old vars for PDF compat
        total_sales=gross_sales,
        delivered_orders=total_delivered,
        total_orders=base_q.count(),
    )


@app.route('/seller/sales-report/preview-pdf')
@login_required
@role_required('seller')
def seller_sales_report_preview_pdf():
    from flask import send_file
    user = User.query.get(session['user_id'])
    if not user.shop:
        return jsonify({'error': 'No shop'}), 400
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date = None
    end_date = None
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            pass
    pdf_buffer = generate_sales_report_pdf('seller', session['user_id'], start_date, end_date)
    if not pdf_buffer:
        return jsonify({'error': 'Failed'}), 500
    return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=False)


@app.route('/seller/sales-report/export-pdf')
@login_required
@role_required('seller')
def seller_sales_report_export_pdf():
    """Export seller sales report as PDF"""
    from flask import send_file
    user = User.query.get(session['user_id'])
    if not user.shop:
        flash('You need to create a shop first.', 'warning')
        return redirect(url_for('create_shop'))

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date = None
    end_date = None
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    pdf_buffer = generate_sales_report_pdf('seller', session['user_id'], start_date, end_date)
    if not pdf_buffer:
        flash('Unable to generate PDF report.', 'danger')
        return redirect(url_for('seller_sales_report'))

    filename = f"sales_report_{user.shop.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
    from flask import send_file
    return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=False, download_name=filename)


@app.route('/seller/shop/create', methods=['GET', 'POST'])
@login_required
@role_required('seller')
def create_shop():
    user = User.query.get(session['user_id'])
    
    if user.shop:
        flash('You already have a shop.', 'info')
        return redirect(url_for('seller_dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        logo = None
        if 'logo' in request.files:
            file = request.files['logo']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"shop_{user.id}_{filename}"
                file_path = f"shops/logos/{filename}"
                success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                if success:
                    logo = result  # Store the public URL
                else:
                    flash(f'Error uploading shop logo: {result}', 'warning')
        
        shop = Shop(
            seller_id=user.id,
            name=name,
            description=description,
            logo=logo
        )
        db.session.add(shop)
        db.session.commit()
        
        log_action('SHOP_CREATED', 'Shop', str(shop.id), f'Shop: {name}')
        flash('Shop created successfully!', 'success')
        return redirect(url_for('seller_dashboard'))
    
    return render_template('create_shop.html')


@app.route('/seller/products')
@login_required
@role_required('seller')
def seller_products():
    user = User.query.get(session['user_id'])
    products = Product.query.filter_by(shop_id=user.shop.id).all()
    return render_template('seller_products.html', products=products)


@app.route('/seller/product/create', methods=['GET', 'POST'])
@login_required
@role_required('seller')
def create_product():
    user = User.query.get(session['user_id'])
    categories = Category.query.all()
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        stock = request.form.get('stock')
        category_id = request.form.get('category_id')
        
        image = None
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"product_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file_path = f"products/images/{filename}"
                success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                if success:
                    image = result  # Store the public URL
                else:
                    flash(f'Error uploading product image: {result}', 'warning')
        
        product = Product(
            shop_id=user.shop.id,
            category_id=category_id,
            name=name,
            description=description,
            price=price,
            stock=stock,
            image=image
        )
        db.session.add(product)
        db.session.commit()
        
        log_action('PRODUCT_CREATED', 'Product', str(product.id), f'Product: {name}')
        flash('Product created successfully!', 'success')
        return redirect(url_for('seller_products'))
    
    return render_template('create_product.html', categories=categories)


@app.route('/seller/product/<product_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('seller')
def edit_product(product_id):
    try:
        import uuid as uuid_lib
        product_id = uuid_lib.UUID(product_id)
    except (ValueError, AttributeError):
        flash('Invalid product ID.', 'danger')
        return redirect(url_for('seller_products'))
    user = User.query.get(session['user_id'])
    product = Product.query.get_or_404(product_id)
    
    if product.shop_id != user.shop.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('seller_products'))
    
    categories = Category.query.all()
    
    if request.method == 'POST':
        product.name = request.form.get('name')
        product.description = request.form.get('description')
        product.price = request.form.get('price')
        product.stock = request.form.get('stock')
        product.category_id = request.form.get('category_id')
        
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"product_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file_path = f"products/images/{filename}"
                success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                if success:
                    product.image = result  # Store the public URL
                else:
                    flash(f'Error uploading product image: {result}', 'warning')
        
        db.session.commit()
        
        log_action('PRODUCT_UPDATED', 'Product', str(product.id), f'Updated: {product.name}')
        flash('Product updated successfully!', 'success')
        return redirect(url_for('seller_products'))
    
    return render_template('edit_product.html', product=product, categories=categories)


@app.route('/seller/product/<product_id>/delete', methods=['POST'])
@login_required
@role_required('seller')
def delete_product(product_id):
    try:
        import uuid as uuid_lib
        product_id = uuid_lib.UUID(product_id)
    except (ValueError, AttributeError):
        flash('Invalid product ID.', 'danger')
        return redirect(url_for('seller_products'))
    user = User.query.get(session['user_id'])
    product = Product.query.get_or_404(product_id)
    
    if product.shop_id != user.shop.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('seller_products'))
    
    log_action('PRODUCT_DELETED', 'Product', str(product.id), f'Deleted: {product.name}')
    db.session.delete(product)
    db.session.commit()
    
    flash('Product deleted successfully!', 'success')
    return redirect(url_for('seller_products'))


@app.route('/seller/orders')
@login_required
@role_required('seller')
def seller_orders():
    user = User.query.get(session['user_id'])
    orders = Order.query.filter_by(shop_id=user.shop.id)\
        .order_by(Order.created_at.desc()).all()
    return render_template('seller_orders.html', orders=orders)


@app.route('/seller/order/<order_id>')
@login_required
@role_required('seller')
def seller_order_detail(order_id):
    try:
        import uuid as uuid_lib
        order_id = uuid_lib.UUID(order_id)
    except (ValueError, AttributeError):
        flash('Invalid order ID.', 'danger')
        return redirect(url_for('seller_orders'))
    user = User.query.get(session['user_id'])
    order = Order.query.get_or_404(order_id)
    
    if order.shop_id != user.shop.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('seller_orders'))
    
    # Generate QR code for pickup if READY_FOR_PICKUP
    qr_data = None
    if order.status == 'READY_FOR_PICKUP' and order.pickup_token:
        qr_data = generate_qr_code(order.pickup_token)
    
    # Get available couriers for selection
    available_couriers = User.query.filter_by(role='courier', is_approved=True).all()
    
    # Get available riders (if courier is already assigned, filter by that courier)
    if order.courier_id:
        available_riders = User.query.filter_by(
            role='rider', 
            is_approved=True,
            courier_id=order.courier_id
        ).all()
    else:
        available_riders = User.query.filter_by(role='rider', is_approved=True).all()
    
    # Get rider information if rider is assigned
    rider_info = None
    if order.rider_id:
        rider = User.query.get(order.rider_id)
        feedbacks = RiderFeedback.query.filter_by(rider_id=order.rider_id).all()
        avg_rating = sum([f.rating for f in feedbacks]) / len(feedbacks) if feedbacks else 0
        recent_feedbacks = RiderFeedback.query.filter_by(rider_id=order.rider_id).order_by(RiderFeedback.created_at.desc()).limit(3).all()
        
        rider_info = {
            'id': rider.id,
            'full_name': rider.full_name or rider.email,
            'email': rider.email,
            'phone': rider.phone,
            'profile_picture': rider.profile_picture,
            'avg_rating': round(avg_rating, 1),
            'total_feedbacks': len(feedbacks),
            'recent_feedbacks': recent_feedbacks
        }
    
    # Get courier information if courier is assigned
    courier_info = None
    if order.courier_id:
        courier = User.query.get(order.courier_id)
        courier_info = {
            'id': courier.id,
            'company_name': courier.company_name,
            'full_name': courier.full_name or courier.email,
            'email': courier.email,
            'phone': courier.phone,
            'profile_picture': courier.profile_picture,
            'vehicle_type': courier.vehicle_type
        }
    
    return render_template('seller_order_detail.html', 
        order=order, 
        qr_data=qr_data, 
        available_couriers=available_couriers,
        available_riders=available_riders,
        rider_info=rider_info,
        courier_info=courier_info
    )


@app.route('/seller/order/<path:order_id>/mark-ready', methods=['POST'])
@login_required
@role_required('seller')
def mark_order_ready(order_id):
    try:
        import uuid as uuid_lib
        order_id = uuid_lib.UUID(order_id)
    except (ValueError, AttributeError):
        flash('Invalid order ID.', 'danger')
        return redirect(url_for('seller_orders'))
    user = User.query.get(session['user_id'])
    order = Order.query.get_or_404(order_id)
    
    if order.shop_id != user.shop.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('seller_orders'))
    
    if order.status != 'PENDING_PAYMENT':
        flash('Order cannot be marked as ready.', 'warning')
        return redirect(url_for('seller_order_detail', order_id=order_id))
    
    # Get selected courier if provided
    courier_id = request.form.get('courier_id')
    if courier_id and courier_id.strip():
        try:
            courier_id = int(courier_id)
            courier = User.query.filter_by(id=courier_id, role='courier').first()
            if courier:
                order.courier_id = courier_id
                
                # Create conversation between seller and courier
                existing_conv = Conversation.query.filter_by(
                    order_id=order.id,
                    conversation_type='seller_courier'
                ).first()
                
                if not existing_conv:
                    conversation = Conversation(
                        user1_id=user.id,  # Seller
                        user2_id=courier_id,  # Courier
                        order_id=order.id,
                        conversation_type='seller_courier'
                    )
                    db.session.add(conversation)
                    
                    # Add initial message
                    initial_message = Message(
                        conversation_id=conversation.id if conversation.id else None,
                        sender_id=user.id,
                        message_text=f"Order {order.order_number} is ready for pickup. Please coordinate pickup time and location."
                    )
                    # We'll add the message after conversation is committed
                    db.session.flush()  # Get conversation ID
                    initial_message.conversation_id = conversation.id
                    db.session.add(initial_message)
        except (ValueError, TypeError):
            pass
    
    # Generate pickup token for courier
    order.pickup_token = generate_qr_token(order.id, 'pickup')
    # Pre-generate delivery token so rider can scan even if courier skips QR scan
    order.delivery_token = generate_qr_token(order.id, 'delivery')
    order.status = 'READY_FOR_PICKUP'
    db.session.commit()
    
    log_action('ORDER_READY_FOR_PICKUP', 'Order', str(order.id), f'Order {order.order_number}')
    create_notification(order.customer_id, 'Order Ready', f'Your order {order.order_number} is ready for pickup by the courier.', 'info', order.id)
    
    # Notify customer
    send_email(
        order.customer.email,
        'Order Ready for Pickup',
        f'Your order {order.order_number} is ready for pickup!'
    )
    
    flash('Order marked as ready for pickup!', 'success')
    return redirect(url_for('seller_order_detail', order_id=order_id))


@app.route('/seller/order/<path:order_id>/assign-delivery', methods=['POST'])
@login_required
@role_required('seller')
def assign_delivery_personnel(order_id):
    """Assign courier and/or rider to an order"""
    try:
        import uuid as uuid_lib
        order_id_uuid = uuid_lib.UUID(order_id)
    except (ValueError, AttributeError):
        flash('Invalid order ID.', 'danger')
        return redirect(url_for('seller_orders'))
    user = User.query.get(session['user_id'])
    order = Order.query.get_or_404(order_id_uuid)
    
    if order.shop_id != user.shop.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('seller_orders'))
    
    courier_id = request.form.get('courier_id')
    rider_id = request.form.get('rider_id')
    
    # Assign courier if provided
    if courier_id and courier_id.strip():
        try:
            # Validate UUID format
            import uuid as uuid_lib
            try:
                uuid_lib.UUID(courier_id)
            except (ValueError, AttributeError):
                raise ValueError('Invalid UUID format')
            courier = User.query.filter_by(id=courier_id, role='courier', is_approved=True).first()
            if courier:
                order.courier_id = courier_id
                
                # Find existing conversation between seller and courier (any order)
                existing_conv = Conversation.query.filter(
                    db.or_(
                        db.and_(Conversation.user1_id == user.id, Conversation.user2_id == courier_id),
                        db.and_(Conversation.user1_id == courier_id, Conversation.user2_id == user.id)
                    ),
                    Conversation.conversation_type == 'seller_courier'
                ).first()
                
                if not existing_conv:
                    existing_conv = Conversation(
                        user1_id=user.id,
                        user2_id=courier_id,
                        order_id=order.id,
                        conversation_type='seller_courier'
                    )
                    db.session.add(existing_conv)
                    db.session.flush()
                
                initial_message = Message(
                    conversation_id=existing_conv.id,
                    sender_id=user.id,
                    message_text=f"You have been assigned to handle order {order.order_number}. Please coordinate pickup."
                )
                db.session.add(initial_message)
                existing_conv.last_message_at = get_philippines_time()
                
                # Send notification to courier
                send_email(
                    courier.email,
                    'New Order Assignment',
                    f'You have been assigned to pick up order {order.order_number}.'
                )
                
                flash(f'Courier {courier.full_name or courier.email} assigned successfully!', 'success')
            else:
                flash('Invalid courier selected.', 'danger')
        except (ValueError, TypeError, AttributeError):
            flash('Invalid courier ID.', 'danger')
    
    # Assign rider if provided
    if rider_id and rider_id.strip():
        # Check if rider is already locked
        if order.rider_locked:
            flash('Rider has already been locked after courier handoff. Cannot reassign. Contact admin if changes are needed.', 'warning')
        else:
            try:
                # Validate UUID format
                import uuid as uuid_lib
                try:
                    uuid_lib.UUID(rider_id)
                except (ValueError, AttributeError):
                    raise ValueError('Invalid UUID format')
                rider = User.query.filter_by(id=rider_id, role='rider', is_approved=True).first()
                if rider:
                    # Use the newly assigned courier_id (from this same request) for validation
                    effective_courier_id = uuid_lib.UUID(courier_id) if (courier_id and courier_id.strip()) else order.courier_id
                    # Verify rider belongs to selected courier if courier is assigned
                    if effective_courier_id and rider.courier_id != effective_courier_id:
                        flash('Selected rider does not belong to the assigned courier company.', 'warning')
                    else:
                        order.rider_id = rider_id
                        
                        # Find existing conversation between seller and rider (any order)
                        existing_conv = Conversation.query.filter(
                            db.or_(
                                db.and_(Conversation.user1_id == user.id, Conversation.user2_id == rider_id),
                                db.and_(Conversation.user1_id == rider_id, Conversation.user2_id == user.id)
                            ),
                            Conversation.conversation_type == 'seller_rider'
                        ).first()
                        
                        if not existing_conv:
                            existing_conv = Conversation(
                                user1_id=user.id,
                                user2_id=rider_id,
                                order_id=order.id,
                                conversation_type='seller_rider'
                            )
                            db.session.add(existing_conv)
                            db.session.flush()
                        
                        initial_message = Message(
                            conversation_id=existing_conv.id,
                            sender_id=user.id,
                            message_text=f"You have been assigned to deliver order {order.order_number}."
                        )
                        db.session.add(initial_message)
                        existing_conv.last_message_at = get_philippines_time()
                        
                        # Send notification to rider
                        send_email(
                            rider.email,
                            'New Delivery Assignment',
                            f'You have been assigned to deliver order {order.order_number}.'
                        )
                        
                        flash(f'Rider {rider.full_name or rider.email} assigned successfully!', 'success')
                else:
                    flash('Invalid rider selected.', 'danger')
            except (ValueError, TypeError, AttributeError):
                flash('Invalid rider ID.', 'danger')
    
    db.session.commit()
    log_action('DELIVERY_PERSONNEL_ASSIGNED', 'Order', str(order.id), f'Courier: {order.courier_id}, Rider: {order.rider_id}')
    
    return redirect(url_for('seller_order_detail', order_id=order_id))


@app.route('/seller/order/<path:order_id>/cancel', methods=['POST'])
@login_required
@role_required('seller')
def seller_cancel_order(order_id):
    try:
        import uuid as uuid_lib
        order_id = uuid_lib.UUID(order_id)
    except (ValueError, AttributeError):
        flash('Invalid order ID.', 'danger')
        return redirect(url_for('seller_orders'))
    user = User.query.get(session['user_id'])
    order = Order.query.get_or_404(order_id)

    if order.shop_id != user.shop.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('seller_orders'))

    if order.status not in ['PENDING_PAYMENT', 'READY_FOR_PICKUP']:
        flash('Order can no longer be cancelled.', 'warning')
        return redirect(url_for('seller_orders'))

    # Restore stock
    for item in order.items:
        item.product.stock += item.quantity

    reason = request.form.get('cancellation_reason', '').strip()
    order.status = 'CANCELLED'
    order.cancellation_reason = reason
    create_notification(order.customer_id, 'Order Cancelled', f'Your order {order.order_number} was cancelled by the seller. Reason: {reason or "No reason provided"}.', 'danger', order.id)
    db.session.commit()
    log_action('ORDER_CANCELLED', 'Order', str(order.id), f'Cancelled by seller: {order.order_number}')
    flash(f'Order {order.order_number} has been cancelled.', 'success')
    return redirect(url_for('seller_orders'))


@app.route('/customer/order/<path:order_id>/cancel', methods=['POST'])
@login_required
@role_required('customer')
def customer_cancel_order(order_id):
    try:
        import uuid as uuid_lib
        order_id = uuid_lib.UUID(order_id)
    except (ValueError, AttributeError):
        flash('Invalid order ID.', 'danger')
        return redirect(url_for('customer_orders'))
    order = Order.query.get_or_404(order_id)

    if order.customer_id != session['user_id']:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('customer_orders'))

    if order.status != 'PENDING_PAYMENT':
        flash('Order can no longer be cancelled.', 'warning')
        return redirect(url_for('customer_orders'))

    # Restore stock
    for item in order.items:
        item.product.stock += item.quantity

    reason = request.form.get('cancellation_reason', '').strip()
    order.status = 'CANCELLED'
    order.cancellation_reason = reason
    create_notification(order.shop.seller_id, 'Order Cancelled by Customer', f'Order {order.order_number} was cancelled by the customer. Reason: {reason or "No reason provided"}.', 'warning', order.id)
    create_notification(order.customer_id, 'Order Cancelled', f'Your order {order.order_number} has been cancelled. Reason: {reason or "No reason provided"}.', 'danger', order.id)
    db.session.commit()
    log_action('ORDER_CANCELLED', 'Order', str(order.id), f'Cancelled by customer: {order.order_number}')
    flash(f'Order {order.order_number} has been cancelled.', 'success')
    return redirect(url_for('customer_orders'))




@app.route('/courier/dashboard')
@login_required
@role_required('courier')
def courier_dashboard():
    from sqlalchemy import func
    
    user_id = session['user_id']
    
    # Show available orders to pickup
    available_orders = Order.query.filter_by(status='READY_FOR_PICKUP', courier_id=None)\
        .order_by(Order.created_at.desc()).all()
    
    # Show assigned orders
    my_orders = Order.query.filter_by(courier_id=user_id)\
        .filter(Order.status != 'READY_FOR_PICKUP')\
        .order_by(Order.created_at.desc()).all()
    
    # Earnings statistics
    total_deliveries = Order.query.filter_by(courier_id=user_id, status='DELIVERED').count()
    pending_deliveries = Order.query.filter_by(courier_id=user_id)\
        .filter(Order.status.in_(['READY_FOR_PICKUP', 'IN_TRANSIT_TO_RIDER'])).count()
    
    # Total earnings (60% of delivery fee for completed deliveries)
    # Use COALESCE to fallback to 60% of delivery_fee when courier_earnings is NULL
    from sqlalchemy import func as sqlfunc, case
    delivered_orders = Order.query.filter_by(courier_id=user_id, status='DELIVERED').all()
    total_earnings = Decimal('0')
    for o in delivered_orders:
        if o.courier_earnings:
            total_earnings += Decimal(str(o.courier_earnings))
        elif o.delivery_fee:
            total_earnings += Decimal(str(o.delivery_fee)) * Decimal('0.6')
    
    # Pending earnings (not yet delivered)
    pending_orders_list = Order.query.filter(
        Order.courier_id == user_id,
        Order.status.in_(['READY_FOR_PICKUP', 'IN_TRANSIT_TO_RIDER'])
    ).all()
    pending_earnings = Decimal('0')
    for o in pending_orders_list:
        if o.courier_earnings:
            pending_earnings += Decimal(str(o.courier_earnings))
        elif o.delivery_fee:
            pending_earnings += Decimal(str(o.delivery_fee)) * Decimal('0.6')
    
    # Withdrawal information - total delivery fees from completed orders
    total_delivery_fees = sum(
        Decimal(str(o.delivery_fee)) for o in delivered_orders if o.delivery_fee
    )

    # Backfill courier_earnings for any NULL records so future queries are accurate
    for o in delivered_orders:
        if not o.courier_earnings and o.delivery_fee:
            o.courier_earnings = Decimal(str(o.delivery_fee)) * Decimal('0.6')
    db.session.commit()

    # Courier gets 40% commission kept by platform (so 60% goes to courier)
    courier_commission = total_delivery_fees * Decimal('0.40')
    available_to_withdraw = total_earnings  # already based on courier earnings
    
    return render_template(
        'courier_dashboard.html',
        available_orders=available_orders,
        my_orders=my_orders,
        total_deliveries=total_deliveries,
        pending_deliveries=pending_deliveries,
        total_earnings=total_earnings,
        pending_earnings=pending_earnings,
        total_delivery_fees=total_delivery_fees,
        courier_commission=courier_commission,
        available_to_withdraw=available_to_withdraw,
        Decimal=Decimal
    )


@app.route('/courier/earnings-report/export-pdf')
@login_required
@role_required('courier')
def courier_earnings_export_pdf():
    """Export courier earnings report as PDF"""
    from flask import send_file
    
    # Get date range if provided
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    start_date = None
    end_date = None
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            pass
    
    # Generate PDF
    pdf_buffer = generate_sales_report_pdf('courier', session['user_id'], start_date, end_date)
    
    if not pdf_buffer:
        flash('Unable to generate PDF report.', 'danger')
        return redirect(url_for('courier_dashboard'))
    
    # Create filename
    filename = f"courier_earnings_report_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )


@app.route('/courier/pickup-manifest')
@login_required
@role_required('courier')
def courier_pickup_manifest():
    # Orders assigned to this courier that are in transit to rider
    orders = Order.query.filter_by(courier_id=session['user_id'])\
        .filter(Order.status == 'IN_TRANSIT_TO_RIDER')\
        .order_by(Order.created_at.desc()).all()
    return render_template('courier_manifest.html', orders=orders, title='Pickup Manifest')


@app.route('/courier/scan-pickup', methods=['GET', 'POST'])
@login_required
@role_required('courier')
def courier_scan_pickup():
    if request.method == 'POST':
        token = request.form.get('token')
        
        payload = verify_qr_token(token)
        if not payload or payload.get('type') != 'pickup':
            flash('Invalid or expired QR code.', 'danger')
            return redirect(url_for('courier_scan_pickup'))
        
        order = Order.query.get(payload['order_id'])
        if not order or order.status != 'READY_FOR_PICKUP':
            flash('Order not ready for pickup.', 'warning')
            return redirect(url_for('courier_scan_pickup'))
        
        # Assign courier and generate rider token
        order.courier_id = session['user_id']
        order.delivery_token = generate_qr_token(order.id, 'delivery')
        order.status = 'IN_TRANSIT_TO_RIDER'
        db.session.commit()
        
        log_action('ORDER_PICKED_UP', 'Order', order.id, f'Courier picked up {order.order_number}')
        
        create_notification(order.customer_id, 'Order Picked Up', f'Your order {order.order_number} has been picked up by the courier and is on the way!', 'info', order.id)
        if order.rider_id:
            create_notification(order.rider_id, 'New Delivery Assignment', f'Order {order.order_number} is ready for you to pick up from the courier.', 'info', order.id)
        db.session.commit()
        
        # Notify customer
        send_email(
            order.customer.email,
            'Order Picked Up',
            f'Your order {order.order_number} has been picked up and is on the way!'
        )
        
        flash(f'Order {order.order_number} picked up successfully!', 'success')
        return redirect(url_for('courier_dashboard'))
    
    return render_template('courier_scan_pickup.html')


@app.route('/courier/handoff/<path:order_id>')
@login_required
@role_required('courier')
def courier_handoff_qr(order_id):
    try:
        import uuid as uuid_lib
        order_id = uuid_lib.UUID(order_id)
    except (ValueError, AttributeError):
        flash('Invalid order ID.', 'danger')
        return redirect(url_for('courier_dashboard'))
    order = Order.query.get_or_404(order_id)
    
    if order.courier_id != session['user_id']:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('courier_dashboard'))
    
    if order.status != 'IN_TRANSIT_TO_RIDER':
        flash('Order not ready for handoff.', 'warning')
        return redirect(url_for('courier_dashboard'))
    
    # Generate QR for rider to scan (regenerate if missing)
    if not order.delivery_token:
        order.delivery_token = generate_qr_token(order.id, 'delivery')
        db.session.commit()
    qr_data = generate_qr_code(order.delivery_token)
    
    return render_template('courier_handoff.html', order=order, qr_data=qr_data)


@app.route('/courier/profile', methods=['GET', 'POST'])
@login_required
@role_required('courier')
def courier_profile():
    """Courier profile edit page"""
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        # Update courier company information
        user.company_name = request.form.get('company_name', '').strip()
        user.full_name = request.form.get('full_name', '').strip()
        user.phone = request.form.get('phone', '').strip()
        user.email = request.form.get('email', '').strip()
        user.company_address = request.form.get('company_address', '').strip()
        user.company_description = request.form.get('company_description', '').strip()
        user.vehicle_type = request.form.get('vehicle_type', '').strip()
        
        # Handle company logo upload
        if 'company_logo' in request.files:
            file = request.files['company_logo']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"company_logo_{user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file_path = f"couriers/company_logos/{filename}"
                success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                if success:
                    user.company_logo = result  # Store the public URL
                else:
                    flash(f'Error uploading company logo: {result}', 'warning')
        
        # Handle business permit upload (optional for updates)
        if 'business_permit' in request.files:
            file = request.files['business_permit']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"business_permit_courier_{user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file_path = f"users/business_permits/{filename}"
                success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                if success:
                    user.business_permit = result  # Store the public URL
                    flash('Business permit updated successfully!', 'success')
                else:
                    flash(f'Error uploading business permit: {result}', 'warning')
            else:
                flash('Invalid business permit file. Please upload a valid document (PDF, PNG, JPG, JPEG, GIF, WEBP)', 'warning')
        
        # Handle profile picture upload (optional)
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"profile_{user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file_path = f"couriers/profile_pictures/{filename}"
                success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                if success:
                    user.profile_picture = result  # Store the public URL
                else:
                    flash(f'Error uploading profile picture: {result}', 'warning')
        
        db.session.commit()
        log_action('COURIER_PROFILE_UPDATED', 'User', user.id, 'Updated courier profile')
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('courier_profile'))
    
    return render_template('courier_profile.html', user=user)


# ==================== RIDER ROUTES ====================

@app.route('/rider/dashboard')
@login_required
@role_required('rider')
def rider_dashboard():
    from sqlalchemy import func
    
    user_id = session['user_id']
    
    # Orders assigned to this rider (pre-assigned by seller, status IN_TRANSIT_TO_RIDER)
    available_orders = Order.query.filter_by(status='IN_TRANSIT_TO_RIDER', rider_id=user_id)\
        .order_by(Order.created_at.desc()).all()
    
    # Orders assigned to this rider
    my_orders = Order.query.filter_by(rider_id=user_id)\
        .filter(Order.status.in_(['OUT_FOR_DELIVERY']))\
        .order_by(Order.created_at.desc()).all()
    
    # Earnings statistics
    total_deliveries = Order.query.filter_by(rider_id=user_id, status='DELIVERED').count()
    pending_deliveries = Order.query.filter_by(rider_id=user_id, status='OUT_FOR_DELIVERY').count()
    
    # Total earnings (40% of delivery fee for completed deliveries)
    delivered_orders = Order.query.filter_by(rider_id=user_id, status='DELIVERED').all()
    total_earnings = Decimal('0')
    for o in delivered_orders:
        if o.rider_earnings:
            total_earnings += Decimal(str(o.rider_earnings))
        elif o.delivery_fee:
            total_earnings += Decimal(str(o.delivery_fee)) * Decimal('0.4')

    # Pending earnings (not yet delivered)
    pending_orders_list = Order.query.filter_by(rider_id=user_id, status='OUT_FOR_DELIVERY').all()
    pending_earnings = Decimal('0')
    for o in pending_orders_list:
        if o.rider_earnings:
            pending_earnings += Decimal(str(o.rider_earnings))
        elif o.delivery_fee:
            pending_earnings += Decimal(str(o.delivery_fee)) * Decimal('0.4')

    # Backfill rider_earnings for NULL records
    for o in delivered_orders:
        if not o.rider_earnings and o.delivery_fee:
            o.rider_earnings = Decimal(str(o.delivery_fee)) * Decimal('0.4')
    db.session.commit()

    # Withdrawal information
    total_delivery_fees = sum(
        Decimal(str(o.delivery_fee)) for o in delivered_orders if o.delivery_fee
    )
    rider_commission = total_delivery_fees * Decimal('0.60')
    available_to_withdraw = total_earnings
    
    return render_template('rider_dashboard.html',
        available_orders=available_orders,
        my_orders=my_orders,
        total_deliveries=total_deliveries,
        pending_deliveries=pending_deliveries,
        total_earnings=total_earnings,
        pending_earnings=pending_earnings,
        total_delivery_fees=total_delivery_fees,
        rider_commission=rider_commission,
        available_to_withdraw=available_to_withdraw,
        Decimal=Decimal
    )


@app.route('/rider/profile', methods=['GET', 'POST'])
@login_required
@role_required('rider')
def rider_profile():
    """Rider profile edit page"""
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        # Update rider personal information
        user.full_name = request.form.get('full_name', '').strip()
        user.first_name = request.form.get('first_name', '').strip()
        user.middle_name = request.form.get('middle_name', '').strip()
        user.last_name = request.form.get('last_name', '').strip()
        user.phone = request.form.get('phone', '').strip()
        user.email = request.form.get('email', '').strip()
        user.vehicle_type = request.form.get('vehicle_type', '').strip()
        user.plate_number = request.form.get('plate_number', '').strip()
        
        # Handle profile picture upload
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"rider_profile_{user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file_path = f"riders/profile_pictures/{filename}"
                success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                if success:
                    user.profile_picture = result  # Store the public URL
                else:
                    flash(f'Error uploading profile picture: {result}', 'warning')
        
        # Handle driver's license upload (optional)
        if 'drivers_license' in request.files:
            file = request.files['drivers_license']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"drivers_license_{user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file_path = f"riders/drivers_licenses/{filename}"
                success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                if success:
                    user.drivers_license = result  # Store the public URL
                else:
                    flash(f"Error uploading driver's license: {result}", 'warning')
        
        db.session.commit()
        log_action('RIDER_PROFILE_UPDATED', 'User', user.id, 'Updated rider profile')
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('rider_profile'))
    
    return render_template('rider_profile.html', user=user)


@app.route('/rider/earnings-report/export-pdf')
@login_required
@role_required('rider')
def rider_earnings_export_pdf():
    """Export rider earnings report as PDF"""
    from flask import send_file
    
    # Get date range if provided
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    start_date = None
    end_date = None
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            pass
    
    # Generate PDF
    pdf_buffer = generate_sales_report_pdf('rider', session['user_id'], start_date, end_date)
    
    if not pdf_buffer:
        flash('Unable to generate PDF report.', 'danger')
        return redirect(url_for('rider_dashboard'))
    
    # Create filename
    filename = f"rider_earnings_report_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )


@app.route('/rider/delivery-manifest')
@login_required
@role_required('rider')
def rider_delivery_manifest():
    orders = Order.query.filter_by(rider_id=session['user_id'], status='OUT_FOR_DELIVERY').all()
    return render_template('rider_manifest.html', orders=orders, title='Delivery Manifest')


@app.route('/rider/scan-from-courier', methods=['GET', 'POST'])
@login_required
@role_required('rider')
def rider_scan_from_courier():
    if request.method == 'POST':
        token = request.form.get('token')
        
        payload = verify_qr_token(token)
        if not payload or payload.get('type') != 'delivery':
            flash('Invalid or expired QR code.', 'danger')
            return redirect(url_for('rider_scan_from_courier'))
        
        order = Order.query.get(payload['order_id'])
        if not order or order.status != 'IN_TRANSIT_TO_RIDER':
            flash('Order not available for pickup.', 'warning')
            return redirect(url_for('rider_scan_from_courier'))
        
        # Check if rider is already locked to a specific rider
        if order.rider_locked and order.rider_id and order.rider_id != session['user_id']:
            flash('This order has already been assigned to another rider and cannot be reassigned.', 'danger')
            return redirect(url_for('rider_scan_from_courier'))
        
        # Assign rider and lock the assignment
        order.rider_id = session['user_id']
        order.rider_locked = True  # Lock rider assignment - no further changes allowed
        order.status = 'OUT_FOR_DELIVERY'
        db.session.commit()
        
        log_action('ORDER_OUT_FOR_DELIVERY', 'Order', order.id, f'Rider received {order.order_number} - LOCKED')
        
        create_notification(order.customer_id, 'Out for Delivery', f'Your order {order.order_number} is out for delivery! Your rider is on the way.', 'info', order.id)
        db.session.commit()
        
        # Notify customer
        send_email(
            order.customer.email,
            'Order Out for Delivery',
            f'Your order {order.order_number} is out for delivery!'
        )
        
        flash(f'Order {order.order_number} received for delivery!', 'success')
        return redirect(url_for('rider_dashboard'))
    
    return render_template('rider_scan_courier.html')


@app.route('/rider/confirm-delivery/<path:order_id>', methods=['GET', 'POST'])
@login_required
@role_required('rider')
def rider_confirm_delivery(order_id):
    try:
        import uuid as uuid_lib
        order_id = uuid_lib.UUID(order_id)
    except (ValueError, AttributeError):
        flash('Invalid order ID.', 'danger')
        return redirect(url_for('rider_dashboard'))
    order = Order.query.get_or_404(order_id)
    
    if order.rider_id != session['user_id']:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('rider_dashboard'))
    
    if order.status != 'OUT_FOR_DELIVERY':
        flash('Order not ready for delivery confirmation.', 'warning')
        return redirect(url_for('rider_dashboard'))
    
    if request.method == 'POST':
        # Check if proof of delivery photo is uploaded
        if 'proof_of_delivery' not in request.files:
            flash('Please upload proof of delivery photo.', 'warning')
            return redirect(url_for('rider_confirm_delivery', order_id=order_id))
        
        file = request.files['proof_of_delivery']
        
        if file.filename == '':
            flash('Please upload proof of delivery photo.', 'warning')
            return redirect(url_for('rider_confirm_delivery', order_id=order_id))
        
        if file and allowed_file(file.filename):
            # Validate file size (max 10MB for photos)
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)
            
            max_size = 10 * 1024 * 1024  # 10MB
            if file_size > max_size:
                flash('File size must be less than 10MB.', 'danger')
                return redirect(url_for('rider_confirm_delivery', order_id=order_id))
            
            # Save proof of delivery photo
            filename = secure_filename(file.filename)
            unique_filename = f"proof_delivery_{order.order_number}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            file_path = f"deliveries/proof_of_delivery/{unique_filename}"
            success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
            if success:
                order.proof_of_delivery = result  # Store the public URL
                order.status = 'DELIVERED'
                db.session.commit()
                
                log_action('ORDER_DELIVERED', 'Order', order.id, f'Order {order.order_number} delivered with proof')
                create_notification(order.customer_id, 'Order Delivered!', f'Your order {order.order_number} has been delivered successfully. Please leave a review!', 'success', order.id)
                create_notification(order.shop.seller_id, 'Order Delivered', f'Order {order.order_number} has been delivered to the customer.', 'success', order.id)
                db.session.commit()
                
                # Notify customer and seller
                send_email(
                    order.customer.email,
                    'Order Delivered',
                    f'Your order {order.order_number} has been delivered successfully!'
                )
                
                flash(f'Order {order.order_number} delivered successfully!', 'success')
                return redirect(url_for('rider_dashboard'))
            else:
                flash(f'Error uploading proof of delivery: {result}', 'danger')
                return redirect(url_for('rider_confirm_delivery', order_id=order_id))
        else:
            flash('Invalid file type. Please upload an image (PNG, JPG, JPEG, GIF, WEBP).', 'danger')
            return redirect(url_for('rider_confirm_delivery', order_id=order_id))
    
    # Show delivery confirmation form with photo upload
    return render_template('rider_delivery_confirm.html', order=order)


@app.route('/rider/history')
@login_required
@role_required('rider')
def rider_history():
    orders = Order.query.filter_by(rider_id=session['user_id'])\
        .order_by(Order.updated_at.desc()).all()
    return render_template('rider_history.html', orders=orders)


# ==================== NOTIFICATION ROUTES ====================

@app.route('/notifications')
@login_required
def notifications():
    """View all notifications for current user"""
    user_id = session['user_id']
    notifications = Notification.query.filter_by(user_id=user_id)\
        .order_by(Notification.created_at.desc()).all()
    
    # Mark all as read when viewing
    for notif in notifications:
        if not notif.is_read:
            notif.is_read = True
    db.session.commit()
    
    return render_template('notifications.html', notifications=notifications)


@app.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read for current user"""
    user_id = session['user_id']
    Notification.query.filter_by(user_id=user_id, is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/notifications/unread-count')
@login_required
def get_unread_notifications_count():
    """Get count of unread notifications for current user"""
    user_id = session['user_id']
    count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    return jsonify({'count': count})


# ==================== ADMIN ROUTES ====================

@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    # Get filter parameters
    time_filter = request.args.get('filter', 'all')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    # Parse custom date range if provided
    now = datetime.utcnow()
    start_date = None
    end_date = None
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            time_filter = 'custom'
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD.', 'warning')
            start_date = None
            end_date = None
    
    # Calculate date range based on predefined filter if no custom range
    if not start_date and not end_date:
        if time_filter == 'day':
            start_date = now - timedelta(days=1)
        elif time_filter == 'week':
            start_date = now - timedelta(weeks=1)
        elif time_filter == 'month':
            start_date = now - timedelta(days=30)
        elif time_filter == 'year':
            start_date = now - timedelta(days=365)
        else:
            start_date = None
    
    # Base query for orders
    order_query = Order.query
    if start_date:
        order_query = order_query.filter(Order.created_at >= start_date)
    if end_date:
        order_query = order_query.filter(Order.created_at <= end_date)
    
    # Statistics
    total_users = User.query.count()
    total_buyers = User.query.filter_by(role='customer').count()
    total_sellers = User.query.filter_by(role='seller').count()
    total_riders = User.query.filter_by(role='rider').count()
    total_couriers = User.query.filter_by(role='courier').count()
    total_orders = Order.query.count()
    total_products = Product.query.count()
    pending_approvals = User.query.filter_by(is_approved=False).count()
    
    # Revenue and commission tracking
    total_revenue = db.session.query(func.sum(Order.total_amount))\
        .filter(Order.status == 'DELIVERED')
    if start_date:
        total_revenue = total_revenue.filter(Order.created_at >= start_date)
    if end_date:
        total_revenue = total_revenue.filter(Order.created_at <= end_date)
    total_revenue = total_revenue.scalar() or 0
    
    # Commission received (from delivered orders)
    commission_received = db.session.query(func.sum(Order.commission_amount))\
        .filter(Order.status == 'DELIVERED')
    if start_date:
        commission_received = commission_received.filter(Order.created_at >= start_date)
    if end_date:
        commission_received = commission_received.filter(Order.created_at <= end_date)
    commission_received = commission_received.scalar() or 0
    
    # Commission pending (from non-delivered orders)
    commission_pending = db.session.query(func.sum(Order.commission_amount))\
        .filter(Order.status.in_(['PENDING_PAYMENT', 'READY_FOR_PICKUP', 'IN_TRANSIT_TO_RIDER', 'OUT_FOR_DELIVERY']))
    if start_date:
        commission_pending = commission_pending.filter(Order.created_at >= start_date)
    if end_date:
        commission_pending = commission_pending.filter(Order.created_at <= end_date)
    commission_pending = commission_pending.scalar() or 0
    
    # Revenue data for chart - monthly, yearly, weekly all built server-side
    def build_series(bucket_list):
        rev_data, comm_data, ord_data = [], [], []
        for label, s, e in bucket_list:
            rev = db.session.query(func.sum(Order.total_amount)).filter(
                Order.created_at >= s, Order.created_at < e, Order.status == 'DELIVERED').scalar() or 0
            cnt = db.session.query(func.count(Order.id)).filter(
                Order.created_at >= s, Order.created_at < e, Order.status == 'DELIVERED').scalar() or 0
            rev_data.append({'label': label, 'value': float(rev)})
            comm_data.append({'label': label, 'value': round(float(rev) * 0.05, 2)})
            ord_data.append({'label': label, 'value': int(cnt)})
        return rev_data, comm_data, ord_data

    # Weekly buckets (last 12 weeks)
    weekly_buckets = []
    for i in range(11, -1, -1):
        s = (now - timedelta(weeks=i+1)).replace(hour=0, minute=0, second=0, microsecond=0)
        e = (now - timedelta(weeks=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        weekly_buckets.append((s.strftime('%b %d'), s, e))

    # Monthly buckets (last 12 months)
    monthly_buckets = []
    for i in range(11, -1, -1):
        s = (now - timedelta(days=30*i)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        e = now if i == 0 else (now - timedelta(days=30*(i-1))).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_buckets.append((s.strftime('%b %Y'), s, e))

    # Yearly buckets (last 5 years)
    yearly_buckets = []
    for i in range(4, -1, -1):
        s = now.replace(year=now.year - i, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        e = now.replace(year=now.year - i + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0) if i > 0 else now
        yearly_buckets.append((str(now.year - i), s, e))

    # Date range buckets (daily within selected range)
    date_range_buckets = []
    if start_date and end_date:
        try:
            from datetime import date as date_type
            sd = datetime.strptime(start_date, '%Y-%m-%d').replace(hour=0, minute=0, second=0, microsecond=0)
            ed = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59, microsecond=0)
            delta = (ed - sd).days + 1
            for i in range(min(delta, 60)):
                day = sd + timedelta(days=i)
                date_range_buckets.append((day.strftime('%b %d'), day, day + timedelta(days=1)))
        except Exception:
            pass

    rev_w, comm_w, ord_w = build_series(weekly_buckets)
    rev_m, comm_m, ord_m = build_series(monthly_buckets)
    rev_y, comm_y, ord_y = build_series(yearly_buckets)
    rev_d, comm_d, ord_d = build_series(date_range_buckets) if date_range_buckets else ([], [], [])

    revenue_chart_data = rev_m
    commission_chart_data = comm_m
    orders_chart_data = ord_m
    chart_data_all = {
        'weekly':     {'all': rev_w, 'commission': comm_w, 'orders': ord_w},
        'monthly':    {'all': rev_m, 'commission': comm_m, 'orders': ord_m},
        'yearly':     {'all': rev_y, 'commission': comm_y, 'orders': ord_y},
        'daterange':  {'all': rev_d, 'commission': comm_d, 'orders': ord_d},
    }
    
    recent_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()

    return render_template('admin_dashboard.html',
        total_users=total_users,
        total_buyers=total_buyers,
        total_sellers=total_sellers,
        total_riders=total_riders,
        total_couriers=total_couriers,
        total_orders=total_orders,
        total_products=total_products,
        pending_approvals=pending_approvals,
        total_revenue=total_revenue,
        commission_received=commission_received,
        commission_pending=commission_pending,
        revenue_chart_data=revenue_chart_data,
        commission_chart_data=commission_chart_data,
        chart_data_all=chart_data_all,
        orders_chart_data=orders_chart_data,
        time_filter=time_filter,
        start_date=start_date_str,
        end_date=end_date_str,
        recent_logs=recent_logs
    )


@app.route('/admin/chart-data')
@login_required
@role_required('admin')
def admin_chart_data():
    from sqlalchemy import func

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    try:
        sd = datetime.strptime(start_date, '%Y-%m-%d').replace(hour=0, minute=0, second=0, microsecond=0)
        ed = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59, microsecond=0)
    except Exception:
        return jsonify({'all': [], 'commission': [], 'orders': []})

    delta = (ed - sd).days + 1
    rev_data, comm_data, ord_data = [], [], []
    for i in range(min(delta, 60)):
        day = sd + timedelta(days=i)
        day_end = day + timedelta(days=1)
        rev = db.session.query(func.sum(Order.total_amount)).filter(
            Order.created_at >= day, Order.created_at < day_end, Order.status == 'DELIVERED').scalar() or 0
        cnt = db.session.query(func.count(Order.id)).filter(
            Order.created_at >= day, Order.created_at < day_end, Order.status == 'DELIVERED').scalar() or 0
        label = day.strftime('%b %d')
        rev_data.append({'label': label, 'value': float(rev)})
        comm_data.append({'label': label, 'value': round(float(rev) * 0.05, 2)})
        ord_data.append({'label': label, 'value': int(cnt)})

    return jsonify({'all': rev_data, 'commission': comm_data, 'orders': ord_data})


@app.route('/admin/change-password', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_change_password():
    """Admin password change with email verification"""
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'request_code':
            # Generate and send verification code
            verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            user.verification_code = verification_code
            user.verification_code_expires = datetime.utcnow() + timedelta(minutes=15)
            db.session.commit()
            
            # Send email with verification code
            send_email(
                user.email,
                'Admin Password Change Verification',
                f'Your password change verification code is: {verification_code}\n\n'
                f'This code will expire in 15 minutes.\n\n'
                f'If you did not request a password change, please ignore this email and ensure your account is secure.'
            )
            
            flash('A verification code has been sent to your email address.', 'success')
            return render_template('admin_change_password.html', current_user=user, step='verify')
        
        elif action == 'verify_and_change':
            # Verify code and change password
            code = request.form.get('verification_code', '').strip()
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            # Validate verification code
            if not user.verification_code or user.verification_code != code:
                flash('Invalid verification code. Please try again.', 'danger')
                return render_template('admin_change_password.html', current_user=user, step='verify')
            
            # Check if code expired
            if user.verification_code_expires and datetime.utcnow() > user.verification_code_expires:
                flash('Verification code has expired. Please request a new one.', 'danger')
                return render_template('admin_change_password.html', current_user=user, step='request')
            
            # Validate passwords
            if not new_password or len(new_password) < 6:
                flash('Password must be at least 6 characters long.', 'danger')
                return render_template('admin_change_password.html', current_user=user, step='verify')
            
            if new_password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return render_template('admin_change_password.html', current_user=user, step='verify')
            
            # Update password in both database and Supabase Auth
            update_password_both(user, new_password)
            user.verification_code = None
            user.verification_code_expires = None
            db.session.commit()
            
            # Log the password change
            log_entry = f"ADMIN PASSWORD CHANGE - User: {user.email} - IP: {request.remote_addr}"
            print(log_entry)
            
            flash('Your password has been successfully changed!', 'success')
            return redirect(url_for('admin_dashboard'))
    
    return render_template('admin_change_password.html', current_user=user, step='request')


@app.route('/seller/change-password', methods=['GET', 'POST'])
@login_required
@role_required('seller')
def seller_change_password():
    """Seller password change with email verification"""
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'request_code':
            # Generate and send verification code
            verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            user.verification_code = verification_code
            user.verification_code_expires = datetime.utcnow() + timedelta(minutes=15)
            db.session.commit()
            
            # Send email with verification code
            send_email(
                user.email,
                'Password Change Verification',
                f'Your password change verification code is: {verification_code}\n\n'
                f'This code will expire in 15 minutes.\n\n'
                f'If you did not request a password change, please ignore this email and ensure your account is secure.'
            )
            
            flash('A verification code has been sent to your email address.', 'success')
            return render_template('seller_change_password.html', current_user=user, step='verify')
        
        elif action == 'verify_and_change':
            # Verify code and change password
            code = request.form.get('verification_code', '').strip()
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            # Validate verification code
            if not user.verification_code or user.verification_code != code:
                flash('Invalid verification code. Please try again.', 'danger')
                return render_template('seller_change_password.html', current_user=user, step='verify')
            
            # Check if code expired
            if user.verification_code_expires and datetime.utcnow() > user.verification_code_expires:
                flash('Verification code has expired. Please request a new one.', 'danger')
                return render_template('seller_change_password.html', current_user=user, step='request')
            
            # Validate passwords
            if not new_password or len(new_password) < 6:
                flash('Password must be at least 6 characters long.', 'danger')
                return render_template('seller_change_password.html', current_user=user, step='verify')
            
            if new_password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return render_template('seller_change_password.html', current_user=user, step='verify')
            
            # Update password in both database and Supabase Auth
            update_password_both(user, new_password)
            user.verification_code = None
            user.verification_code_expires = None
            db.session.commit()
            
            # Log the password change
            log_entry = f"PASSWORD CHANGE - User: {user.email} - IP: {request.remote_addr}"
            print(log_entry)
            
            flash('Your password has been successfully changed!', 'success')
            return redirect(url_for('seller_dashboard'))
    
    return render_template('seller_change_password.html', current_user=user, step='request')


@app.route('/courier/change-password', methods=['GET', 'POST'])
@login_required
@role_required('courier')
def courier_change_password():
    """Courier password change with email verification"""
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'request_code':
            # Generate and send verification code
            verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            user.verification_code = verification_code
            user.verification_code_expires = datetime.utcnow() + timedelta(minutes=15)
            db.session.commit()
            
            # Send email with verification code
            send_email(
                user.email,
                'Password Change Verification',
                f'Your password change verification code is: {verification_code}\n\n'
                f'This code will expire in 15 minutes.\n\n'
                f'If you did not request a password change, please ignore this email and ensure your account is secure.'
            )
            
            flash('A verification code has been sent to your email address.', 'success')
            return render_template('courier_change_password.html', current_user=user, step='verify')
        
        elif action == 'verify_and_change':
            # Verify code and change password
            code = request.form.get('verification_code', '').strip()
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            # Validate verification code
            if not user.verification_code or user.verification_code != code:
                flash('Invalid verification code. Please try again.', 'danger')
                return render_template('courier_change_password.html', current_user=user, step='verify')
            
            # Check if code expired
            if user.verification_code_expires and datetime.utcnow() > user.verification_code_expires:
                flash('Verification code has expired. Please request a new one.', 'danger')
                return render_template('courier_change_password.html', current_user=user, step='request')
            
            # Validate passwords
            if not new_password or len(new_password) < 6:
                flash('Password must be at least 6 characters long.', 'danger')
                return render_template('courier_change_password.html', current_user=user, step='verify')
            
            if new_password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return render_template('courier_change_password.html', current_user=user, step='verify')
            
            # Update password in both database and Supabase Auth
            update_password_both(user, new_password)
            user.verification_code = None
            user.verification_code_expires = None
            db.session.commit()
            
            # Log the password change
            log_entry = f"PASSWORD CHANGE - User: {user.email} - IP: {request.remote_addr}"
            print(log_entry)
            
            flash('Your password has been successfully changed!', 'success')
            return redirect(url_for('courier_dashboard'))
    
    return render_template('courier_change_password.html', current_user=user, step='request')


@app.route('/rider/change-password', methods=['GET', 'POST'])
@login_required
@role_required('rider')
def rider_change_password():
    """Rider password change with email verification"""
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'request_code':
            # Generate and send verification code
            verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            user.verification_code = verification_code
            user.verification_code_expires = datetime.utcnow() + timedelta(minutes=15)
            db.session.commit()
            
            # Send email with verification code
            send_email(
                user.email,
                'Password Change Verification',
                f'Your password change verification code is: {verification_code}\n\n'
                f'This code will expire in 15 minutes.\n\n'
                f'If you did not request a password change, please ignore this email and ensure your account is secure.'
            )
            
            flash('A verification code has been sent to your email address.', 'success')
            return render_template('rider_change_password.html', current_user=user, step='verify')
        
        elif action == 'verify_and_change':
            # Verify code and change password
            code = request.form.get('verification_code', '').strip()
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            # Validate verification code
            if not user.verification_code or user.verification_code != code:
                flash('Invalid verification code. Please try again.', 'danger')
                return render_template('rider_change_password.html', current_user=user, step='verify')
            
            # Check if code expired
            if user.verification_code_expires and datetime.utcnow() > user.verification_code_expires:
                flash('Verification code has expired. Please request a new one.', 'danger')
                return render_template('rider_change_password.html', current_user=user, step='request')
            
            # Validate passwords
            if not new_password or len(new_password) < 6:
                flash('Password must be at least 6 characters long.', 'danger')
                return render_template('rider_change_password.html', current_user=user, step='verify')
            
            if new_password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return render_template('rider_change_password.html', current_user=user, step='verify')
            
            # Update password in both database and Supabase Auth
            update_password_both(user, new_password)
            user.verification_code = None
            user.verification_code_expires = None
            db.session.commit()
            
            # Log the password change
            log_entry = f"PASSWORD CHANGE - User: {user.email} - IP: {request.remote_addr}"
            print(log_entry)
            
            flash('Your password has been successfully changed!', 'success')
            return redirect(url_for('rider_dashboard'))
    
    return render_template('rider_change_password.html', current_user=user, step='request')


@app.route('/customer/change-password', methods=['GET', 'POST'])
@login_required
@role_required('customer')
def customer_change_password():
    """Customer password change with email verification"""
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'request_code':
            # Generate and send verification code
            verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            user.verification_code = verification_code
            user.verification_code_expires = datetime.utcnow() + timedelta(minutes=15)
            db.session.commit()
            
            # Send email with verification code
            send_email(
                user.email,
                'Password Change Verification',
                f'Your password change verification code is: {verification_code}\n\n'
                f'This code will expire in 15 minutes.\n\n'
                f'If you did not request a password change, please ignore this email and ensure your account is secure.'
            )
            
            flash('A verification code has been sent to your email address.', 'success')
            return render_template('customer_change_password.html', current_user=user, step='verify')
        
        elif action == 'verify_and_change':
            # Verify code and change password
            code = request.form.get('verification_code', '').strip()
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            # Validate verification code
            if not user.verification_code or user.verification_code != code:
                flash('Invalid verification code. Please try again.', 'danger')
                return render_template('customer_change_password.html', current_user=user, step='verify')
            
            # Check if code expired
            if user.verification_code_expires and datetime.utcnow() > user.verification_code_expires:
                flash('Verification code has expired. Please request a new one.', 'danger')
                return render_template('customer_change_password.html', current_user=user, step='request')
            
            # Validate passwords
            if not new_password or len(new_password) < 6:
                flash('Password must be at least 6 characters long.', 'danger')
                return render_template('customer_change_password.html', current_user=user, step='verify')
            
            if new_password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return render_template('customer_change_password.html', current_user=user, step='verify')
            
            # Update password in both database and Supabase Auth
            update_password_both(user, new_password)
            user.verification_code = None
            user.verification_code_expires = None
            db.session.commit()
            
            # Log the password change
            log_entry = f"PASSWORD CHANGE - User: {user.email} - IP: {request.remote_addr}"
            print(log_entry)
            
            flash('Your password has been successfully changed!', 'success')
            return redirect(url_for('customer_profile'))
    
    return render_template('customer_change_password.html', current_user=user, step='request')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password - request reset code"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Please enter your email address.', 'danger')
            return render_template('forgot_password.html')
        
        # Find user by email
        user = User.query.filter_by(email=email).first()
        
        # Always show success message (security - don't reveal if email exists)
        flash('If an account exists with this email, a password reset code has been sent.', 'success')
        
        if user:
            # Generate and send reset code
            reset_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            user.verification_code = reset_code
            user.verification_code_expires = datetime.utcnow() + timedelta(minutes=15)
            db.session.commit()
            
            # Send email with reset code
            send_email(
                user.email,
                'Password Reset Request',
                f'Your password reset code is: {reset_code}\n\n'
                f'This code will expire in 15 minutes.\n\n'
                f'If you did not request a password reset, please ignore this email and ensure your account is secure.'
            )
        
        # Redirect to reset page
        return redirect(url_for('reset_password'))
    
    return render_template('forgot_password.html')


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Reset password using verification code"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        code = request.form.get('verification_code', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        if not user:
            flash('Invalid email address or verification code.', 'danger')
            return render_template('reset_password.html')
        
        # Validate verification code
        if not user.verification_code or user.verification_code != code:
            flash('Invalid verification code. Please try again.', 'danger')
            return render_template('reset_password.html')
        
        # Check if code expired
        if user.verification_code_expires and datetime.utcnow() > user.verification_code_expires:
            flash('Verification code has expired. Please request a new reset code.', 'danger')
            return redirect(url_for('forgot_password'))
        
        # Validate passwords
        if not new_password or len(new_password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('reset_password.html')
        
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html')
        
        # Update password in both database and Supabase Auth
        update_password_both(user, new_password)
        user.verification_code = None
        user.verification_code_expires = None
        db.session.commit()
        
        # Log the password reset
        log_entry = f"PASSWORD RESET - User: {user.email} - IP: {request.remote_addr}"
        print(log_entry)
        
        flash('Your password has been successfully reset! You can now log in with your new password.', 'success')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html')


@app.route('/admin/sales-report/export-pdf')
@login_required
@role_required('admin')
def admin_sales_report_export_pdf():
    """Export admin sales report as PDF"""
    from flask import send_file
    from datetime import timedelta

    filter_type = request.args.get('filter_type', 'all')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    now = get_philippines_time()

    start_date = None
    end_date = None

    if filter_type == 'weekly':
        start_date = (now - timedelta(weeks=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif filter_type == 'monthly':
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif filter_type == 'yearly':
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif filter_type == 'daterange' and start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    pdf_buffer = generate_sales_report_pdf('admin', session['user_id'], start_date, end_date)

    if not pdf_buffer:
        flash('Unable to generate PDF report.', 'danger')
        return redirect(url_for('admin_dashboard'))

    label = {'weekly': 'weekly', 'monthly': 'monthly', 'yearly': 'yearly', 'daterange': f'{start_date_str}_to_{end_date_str}'}.get(filter_type, 'all')
    filename = f"admin_sales_report_{label}_{datetime.now().strftime('%Y%m%d')}.pdf"

    return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=False, download_name=filename)


@app.route('/admin/approvals')
@login_required
@role_required('admin')
def admin_approvals():
    pending_users = User.query.filter_by(is_approved=False).all()
    return render_template('admin_approvals.html', pending_users=pending_users)


@app.route('/admin/approve/<user_id>', methods=['POST'])
@login_required
@role_required('admin')
def approve_user(user_id):
    import uuid as uuid_lib
    try:
        user_id = uuid_lib.UUID(user_id)
    except (ValueError, AttributeError):
        flash('Invalid user ID.', 'danger')
        return redirect(url_for('admin_approvals'))
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    
    log_action('USER_APPROVED', 'User', user.id, f'Approved {user.role}: {user.email}')
    
    # Send approval email
    send_email(
        user.email,
        'Account Approved',
        f'Your {user.role} account has been approved! You can now log in.'
    )
    
    flash(f'{user.role.capitalize()} account approved!', 'success')
    return redirect(url_for('admin_approvals'))


@app.route('/admin/reject/<user_id>', methods=['POST'])
@login_required
@role_required('admin')
def reject_user(user_id):
    import uuid as uuid_lib
    try:
        user_id = uuid_lib.UUID(user_id)
    except (ValueError, AttributeError):
        flash('Invalid user ID.', 'danger')
        return redirect(url_for('admin_approvals'))
    user = User.query.get_or_404(user_id)
    
    log_action('USER_REJECTED', 'User', user.id, f'Rejected {user.role}: {user.email}')
    
    send_email(
        user.email,
        'Account Application',
        f'Unfortunately, your {user.role} account application was not approved.'
    )
    
    # Clean up foreign key references before deleting user
    # 1. Set audit logs to NULL
    AuditLog.query.filter_by(user_id=user.id).update({'user_id': None}, synchronize_session=False)
    
    # 2. Messages and conversations
    Message.query.filter_by(sender_id=user.id).delete(synchronize_session=False)
    Conversation.query.filter(db.or_(Conversation.user1_id == user.id, Conversation.user2_id == user.id)).delete(synchronize_session=False)
    
    # 3. Cart items if seller
    if user.role == 'seller' and user.shop:
        product_ids = [p.id for p in user.shop.products]
        if product_ids:
            CartItem.query.filter(CartItem.product_id.in_(product_ids)).delete(synchronize_session=False)
    
    # Now delete the user
    db.session.delete(user)
    db.session.commit()
    
    flash('User account rejected and removed.', 'info')
    return redirect(url_for('admin_approvals'))


@app.route('/admin/users')
@login_required
@role_required('admin')
def admin_users():
    role_filter = request.args.get('role', 'all')
    
    query = User.query
    if role_filter != 'all':
        query = query.filter_by(role=role_filter)
    
    users = query.order_by(User.created_at.desc()).all()
    
    # Count by role
    role_counts = {
        'all': User.query.count(),
        'customer': User.query.filter_by(role='customer').count(),
        'seller': User.query.filter_by(role='seller').count(),
        'rider': User.query.filter_by(role='rider').count(),
        'courier': User.query.filter_by(role='courier').count(),
    }
    
    return render_template('admin_users.html', 
        users=users, 
        role_filter=role_filter,
        role_counts=role_counts
    )


@app.route('/admin/start-conversation/<path:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_start_conversation(user_id):
    """Admin starts a conversation with any user"""
    try:
        import uuid as uuid_lib
        user_id = uuid_lib.UUID(user_id)
    except (ValueError, AttributeError):
        flash('Invalid user ID.', 'danger')
        return redirect(url_for('admin_users'))
    admin = User.query.get(session['user_id'])
    target_user = User.query.get_or_404(user_id)
    
    if target_user.id == admin.id:
        flash('Cannot start a conversation with yourself.', 'warning')
        return redirect(url_for('admin_users'))
    
    # Check for existing conversation
    existing_conv = Conversation.query.filter(
        db.or_(
            db.and_(Conversation.user1_id == admin.id, Conversation.user2_id == target_user.id),
            db.and_(Conversation.user1_id == target_user.id, Conversation.user2_id == admin.id)
        ),
        Conversation.conversation_type == 'user_admin'
    ).first()
    
    if existing_conv:
        return redirect(url_for('view_conversation', conversation_id=existing_conv.id))
    
    # Create new conversation
    conversation = Conversation(
        user1_id=admin.id,
        user2_id=target_user.id,
        conversation_type='user_admin'
    )
    db.session.add(conversation)
    db.session.commit()
    
    log_action('ADMIN_CONVERSATION_STARTED', 'Conversation', conversation.id, 
               f'Admin started conversation with {target_user.email}')
    
    flash(f'Conversation started with {target_user.full_name or target_user.email}', 'success')
    return redirect(url_for('view_conversation', conversation_id=conversation.id))


@app.route('/admin/user/suspend/<user_id>', methods=['POST'])
@login_required
@role_required('admin')
def suspend_user(user_id):
    """Suspend a user account"""
    # Convert to UUID if needed
    try:
        import uuid as uuid_lib
        if isinstance(user_id, str) and '-' not in user_id:
            user_id = uuid_lib.UUID(int=int(user_id))
    except:
        pass
    
    user = User.query.get_or_404(user_id)
    
    if user.role == 'admin':
        flash('Cannot suspend admin accounts.', 'danger')
        return redirect(url_for('admin_users'))
    
    reason = request.form.get('reason', 'Account suspended by admin')
    
    user.is_suspended = True
    user.suspension_reason = reason
    db.session.commit()
    
    log_action('USER_SUSPENDED', 'User', user.id, f'Suspended: {reason}')
    
    # Send email notification
    send_email(
        user.email,
        'Account Suspended',
        f'Your account has been suspended.\nReason: {reason}\n\nPlease contact support if you have questions.'
    )
    
    flash(f'User account suspended successfully.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/user/unsuspend/<user_id>', methods=['POST'])
@login_required
@role_required('admin')
def unsuspend_user(user_id):
    """Unsuspend a user account"""
    # Convert to UUID if needed
    try:
        import uuid as uuid_lib
        if isinstance(user_id, str) and '-' not in user_id:
            user_id = uuid_lib.UUID(int=int(user_id))
    except:
        pass
    
    user = User.query.get_or_404(user_id)
    
    user.is_suspended = False
    user.suspension_reason = None
    db.session.commit()
    
    log_action('USER_UNSUSPENDED', 'User', user.id, 'Account reactivated')
    
    # Send email notification
    send_email(
        user.email,
        'Account Reactivated',
        'Your account has been reactivated. You can now log in and use all features.'
    )
    
    flash(f'User account reactivated successfully.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/user/delete/<user_id>', methods=['POST'])
@login_required
@role_required('admin')
def delete_user(user_id):
    """Delete a user account and all associated data"""
    try:
        import uuid as uuid_lib
        if isinstance(user_id, str) and '-' not in user_id:
            user_id = uuid_lib.UUID(int=int(user_id))
    except:
        pass
    
    user = User.query.get_or_404(user_id)
    
    if user.role == 'admin':
        flash('Cannot delete admin accounts.', 'danger')
        return redirect(url_for('admin_users'))
    
    user_email = user.email
    user_name = user.full_name
    user_role = user.role
    supabase_user_id = user.supabase_user_id
    
    # Delete all foreign key references
    # 1. Cart items referencing seller's products
    if user.role == 'seller' and user.shop:
        product_ids = [p.id for p in user.shop.products]
        if product_ids:
            CartItem.query.filter(CartItem.product_id.in_(product_ids)).delete(synchronize_session=False)
    
    # 2. Messages and conversations
    Message.query.filter_by(sender_id=user.id).delete(synchronize_session=False)
    Conversation.query.filter(db.or_(Conversation.user1_id == user.id, Conversation.user2_id == user.id)).delete(synchronize_session=False)
    
    # 3. Orders where user is courier/rider (set to NULL)
    Order.query.filter_by(courier_id=user.id).update({'courier_id': None}, synchronize_session=False)
    Order.query.filter_by(rider_id=user.id).update({'rider_id': None}, synchronize_session=False)
    
    # 4. Withdrawal requests processed by user (set to NULL)
    WithdrawalRequest.query.filter_by(processed_by=user.id).update({'processed_by': None}, synchronize_session=False)
    
    # 5. Riders belonging to courier company (set to NULL)
    User.query.filter_by(courier_id=user.id).update({'courier_id': None}, synchronize_session=False)
    
    # 6. Audit logs (set to NULL)
    AuditLog.query.filter_by(user_id=user.id).update({'user_id': None}, synchronize_session=False)
    
    # 7. Handle addresses - either delete orphaned ones or set delivery_address_id to NULL
    # Find all addresses belonging to this user
    user_addresses = Address.query.filter_by(user_id=user.id).all()
    
    # For each address, set delivery_address_id to NULL in orders that reference it
    # This preserves order history while allowing the user to be deleted
    for address in user_addresses:
        Order.query.filter_by(delivery_address_id=address.id).update(
            {'delivery_address_id': None}, 
            synchronize_session=False
        )
    
    # 8. Delete user's addresses
    Address.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    
    # Delete user from database
    db.session.delete(user)
    db.session.commit()
    
    # Delete from Supabase Auth if exists
    if supabase_user_id:
        try:
            import requests
            
            supabase_url = os.environ.get('SUPABASE_URL')
            service_role_key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
            
            if not service_role_key:
                print("[WARNING] SUPABASE_SERVICE_ROLE_KEY not configured - user not deleted from Supabase Auth")
                print(f"[WARNING] User {user_email} still exists in Supabase with ID: {supabase_user_id}")
                flash(f'User deleted from database but still exists in Supabase Auth. Please configure SUPABASE_SERVICE_ROLE_KEY.', 'warning')
            else:
                headers = {
                    'apikey': service_role_key,
                    'Authorization': f'Bearer {service_role_key}',
                    'Content-Type': 'application/json'
                }
                
                delete_url = f"{supabase_url}/auth/v1/admin/users/{supabase_user_id}"
                response = requests.delete(delete_url, headers=headers)
                
                if response.status_code == 200 or response.status_code == 204:
                    print(f"[SUCCESS] Deleted from Supabase Auth: {user_email}")
                    flash(f'User account "{user_name}" deleted successfully from both database and Supabase Auth.', 'success')
                else:
                    print(f"[WARNING] Supabase delete failed (Status {response.status_code}): {response.text}")
                    flash(f'User deleted from database but Supabase deletion failed. User may not be able to re-register with this email.', 'warning')
        except Exception as e:
            print(f"[WARNING] Supabase delete error: {e}")
            flash(f'User deleted from database but Supabase deletion encountered an error.', 'warning')
    else:
        flash(f'User account "{user_name}" deleted successfully.', 'success')
    
    log_action('USER_DELETED', 'User', user_id, f'Deleted {user_role}: {user_name}')
    return redirect(url_for('admin_users'))


@app.route('/admin/categories', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_categories():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        icon = request.form.get('icon')
        
        # Handle background image upload
        background_image = None
        if 'background_image' in request.files:
            file = request.files['background_image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"category_bg_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file_path = f"categories/backgrounds/{unique_filename}"
                success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
                if success:
                    background_image = result  # Store the public URL
                else:
                    flash(f'Error uploading category background image: {result}', 'warning')
        
        category = Category(
            name=name, 
            description=description, 
            icon=icon,
            background_image=background_image
        )
        db.session.add(category)
        db.session.commit()
        
        log_action('CATEGORY_CREATED', 'Category', category.id, f'Created: {name}')
        flash('Category created successfully!', 'success')
        return redirect(url_for('admin_categories'))
    
    categories = Category.query.all()
    return render_template('admin_categories.html', categories=categories, category_icons=CATEGORY_ICONS)


@app.route('/admin/category/<category_id>/update', methods=['POST'])
@login_required
@role_required('admin')
def update_category(category_id):
    try:
        category_uuid = parse_uuid_value(category_id)
    except ValueError:
        abort(404)
    category = Category.query.get_or_404(category_uuid)
    
    # Get form data
    name = request.form.get('name')
    description = request.form.get('description')
    icon = request.form.get('icon')
    
    # Handle background image upload
    if 'background_image' in request.files:
        file = request.files['background_image']
        if file and file.filename and allowed_file(file.filename):
            # Save new background image
            filename = secure_filename(file.filename)
            unique_filename = f"category_bg_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            file_path = f"categories/backgrounds/{unique_filename}"
            success, result = upload_to_supabase(file, 'epicuremart-uploads', file_path)
            if success:
                category.background_image = result  # Store the public URL
            else:
                flash(f'Error uploading category background image: {result}', 'warning')
    
    # Update category fields
    category.name = name
    category.description = description
    category.icon = icon
    
    db.session.commit()
    
    log_action('CATEGORY_UPDATED', 'Category', category.id, f'Updated: {name}')
    flash('Category updated successfully!', 'success')
    return redirect(url_for('admin_categories'))


@app.route('/admin/category/<category_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_category(category_id):
    try:
        category_uuid = parse_uuid_value(category_id)
    except ValueError:
        abort(404)
    category = Category.query.get_or_404(category_uuid)
    
    log_action('CATEGORY_DELETED', 'Category', category.id, f'Deleted: {category.name}')
    
    db.session.delete(category)
    db.session.commit()
    
    flash('Category deleted successfully!', 'success')
    return redirect(url_for('admin_categories'))


@app.route('/admin/orders')
@login_required
@role_required('admin')
def admin_orders():
    # Get sort parameters
    sort_by = request.args.get('sort', 'date')
    direction = request.args.get('direction', 'desc')
    
    # Base query
    query = Order.query
    
    # Apply sorting
    if sort_by == 'order_number':
        if direction == 'asc':
            query = query.order_by(Order.order_number.asc())
        else:
            query = query.order_by(Order.order_number.desc())
    elif sort_by == 'shop':
        query = query.join(Shop).order_by(Shop.name.asc() if direction == 'asc' else Shop.name.desc())
    elif sort_by == 'customer':
        query = query.join(User, Order.customer_id == User.id).order_by(User.full_name.asc() if direction == 'asc' else User.full_name.desc())
    elif sort_by == 'amount':
        if direction == 'asc':
            query = query.order_by(Order.total_amount.asc())
        else:
            query = query.order_by(Order.total_amount.desc())
    elif sort_by == 'status':
        if direction == 'asc':
            query = query.order_by(Order.status.asc())
        else:
            query = query.order_by(Order.status.desc())
    else:  # date (default)
        if direction == 'asc':
            query = query.order_by(Order.created_at.asc())
        else:
            query = query.order_by(Order.created_at.desc())
    
    orders = query.all()
    return render_template('admin_orders.html', orders=orders, sort_by=sort_by, direction=direction)


@app.route('/admin/analytics')
@login_required
@role_required('admin')
def admin_analytics():
    # Sales analytics
    from sqlalchemy import func
    
    total_revenue = db.session.query(func.sum(Order.total_amount))\
        .filter(Order.status == 'DELIVERED').scalar() or 0
        
    total_commission = db.session.query(
        func.sum(Order.commission_amount)
    ).filter(Order.status == 'DELIVERED').scalar() or 0

    seller_earnings = db.session.query(
        func.sum(Order.seller_amount)
    ).filter(Order.status == 'DELIVERED').scalar() or 0
    
    orders_by_status = db.session.query(
        Order.status, func.count(Order.id)
    ).group_by(Order.status).all()
    
    top_products = db.session.query(
        Product.name, func.sum(OrderItem.quantity).label('total')
    ).join(OrderItem).group_by(Product.id)\
        .order_by(func.sum(OrderItem.quantity).desc()).limit(10).all()
    
    # Get seller-specific earnings with sorting
    sort_by = request.args.get('sort', 'earnings')
    direction = request.args.get('direction', 'desc')
    
    seller_earnings_query = db.session.query(
        User.id,
        User.full_name,
        Shop.name.label('shop_name'),
        func.count(Order.id).label('total_orders'),
        func.sum(Order.total_amount).label('total_revenue'),
        func.sum(Order.commission_amount).label('total_commission'),
        func.sum(Order.seller_amount).label('total_earnings')
    ).join(Shop, User.id == Shop.seller_id)\
     .join(Order, Shop.id == Order.shop_id)\
     .filter(Order.status == 'DELIVERED')\
     .group_by(User.id, User.full_name, Shop.name)
    
    # Apply sorting
    if sort_by == 'seller':
        seller_earnings_query = seller_earnings_query.order_by(
            User.full_name.asc() if direction == 'asc' else User.full_name.desc()
        )
    elif sort_by == 'shop':
        seller_earnings_query = seller_earnings_query.order_by(
            Shop.name.asc() if direction == 'asc' else Shop.name.desc()
        )
    elif sort_by == 'orders':
        seller_earnings_query = seller_earnings_query.order_by(
            func.count(Order.id).asc() if direction == 'asc' else func.count(Order.id).desc()
        )
    elif sort_by == 'revenue':
        seller_earnings_query = seller_earnings_query.order_by(
            func.sum(Order.total_amount).asc() if direction == 'asc' else func.sum(Order.total_amount).desc()
        )
    elif sort_by == 'commission':
        seller_earnings_query = seller_earnings_query.order_by(
            func.sum(Order.commission_amount).asc() if direction == 'asc' else func.sum(Order.commission_amount).desc()
        )
    else:  # earnings (default)
        seller_earnings_query = seller_earnings_query.order_by(
            func.sum(Order.seller_amount).asc() if direction == 'asc' else func.sum(Order.seller_amount).desc()
        )
    
    seller_earnings_data = seller_earnings_query.all()
    
    return render_template('admin_analytics.html',
        total_revenue=total_revenue,
        total_commission=total_commission,
        seller_earnings=seller_earnings,
        orders_by_status=orders_by_status,
        top_products=top_products,
        seller_earnings_data=seller_earnings_data,
        sort_by=sort_by,
        direction=direction
    )


@app.route('/messages')
@login_required
def messages_inbox():
    user = User.query.get(session['user_id'])

    # Get all conversations where user is participant, ordered by latest message
    conversations = Conversation.query.filter(
        db.or_(
            Conversation.user1_id == user.id,
            Conversation.user2_id == user.id
        )
    ).order_by(Conversation.last_message_at.desc()).all()

    # Group by other_user — keep only the most recent conversation per user
    seen_users = set()
    conversation_data = []
    total_unread = 0

    for conv in conversations:
        other_user = conv.user2 if conv.user1_id == user.id else conv.user1
        if other_user.id in seen_users:
            continue
        seen_users.add(other_user.id)

        # Count ALL unread messages from this user across ALL conversations
        all_convs_with_user = Conversation.query.filter(
            db.or_(
                db.and_(Conversation.user1_id == user.id, Conversation.user2_id == other_user.id),
                db.and_(Conversation.user1_id == other_user.id, Conversation.user2_id == user.id)
            )
        ).all()
        conv_ids = [c.id for c in all_convs_with_user]

        unread_count = Message.query.filter(
            Message.conversation_id.in_(conv_ids),
            Message.sender_id != user.id,
            Message.is_read == False
        ).count()

        total_unread += unread_count

        last_message = Message.query.filter(
            Message.conversation_id.in_(conv_ids)
        ).order_by(Message.created_at.desc()).first()

        online_status = get_user_online_status(other_user)

        conversation_data.append({
            'conversation': conv,
            'other_user': other_user,
            'unread_count': unread_count,
            'last_message': last_message,
            'online_status': online_status
        })

    return render_template('messages_inbox.html',
        conversation_data=conversation_data,
        unread_count=total_unread
    )



@app.route('/messages/conversation/<path:conversation_id>')
@login_required
def view_conversation(conversation_id):
    from datetime import datetime, timedelta
    try:
        import uuid as uuid_lib
        conversation_id = uuid_lib.UUID(conversation_id)
    except (ValueError, AttributeError):
        flash('Invalid conversation ID.', 'danger')
        return redirect(url_for('messages_inbox'))

    conversation = Conversation.query.get_or_404(conversation_id)
    user = User.query.get(session['user_id'])

    if user.role != 'admin' and user.id not in [conversation.user1_id, conversation.user2_id]:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('messages_inbox'))

    other_user = conversation.user2 if conversation.user1_id == user.id else conversation.user1

    # Get ALL conversations between these two users
    all_convs = Conversation.query.filter(
        db.or_(
            db.and_(Conversation.user1_id == user.id, Conversation.user2_id == other_user.id),
            db.and_(Conversation.user1_id == other_user.id, Conversation.user2_id == user.id)
        )
    ).all()
    all_conv_ids = [c.id for c in all_convs]

    # Mark ALL unread messages from other user as read
    unread = Message.query.filter(
        Message.conversation_id.in_(all_conv_ids),
        Message.sender_id != user.id,
        Message.is_read == False
    ).all()
    for msg in unread:
        msg.is_read = True
        if msg.status == 'delivered':
            msg.status = 'seen'
            msg.seen_at = get_philippines_time()
    db.session.commit()

    # Load ALL messages from ALL conversations between these two users
    messages = Message.query.filter(
        Message.conversation_id.in_(all_conv_ids)
    ).order_by(Message.created_at.asc()).all()

    online_status = get_user_online_status(other_user)
    is_read_only = conversation.is_read_only or (user.role == 'admin' and user.id not in [conversation.user1_id, conversation.user2_id])

    return render_template('conversation.html',
        conversation=conversation,
        messages=messages,
        other_user=other_user,
        online_status=online_status,
        is_read_only=is_read_only,
        now=datetime.utcnow(),
        timedelta=timedelta,
        all_conv_ids=[str(c) for c in all_conv_ids],
    )


@app.route('/messages/send/<path:conversation_id>', methods=['POST'])
@login_required
def send_message(conversation_id):
    """Send a message in a conversation"""
    print(f"\n{'='*60}")
    print(f"[send_message] Called with conversation_id: {conversation_id}")
    print(f"[send_message] User ID: {session.get('user_id')}")
    print(f"[send_message] Request method: {request.method}")
    print(f"[send_message] Form data: {dict(request.form)}")
    print(f"[send_message] Files: {list(request.files.keys())}")
    
    try:
        import uuid as uuid_lib
        conversation_id = uuid_lib.UUID(conversation_id)
    except (ValueError, AttributeError):
        print(f"[ERROR] Invalid conversation ID format")
        return jsonify({'success': False, 'error': 'Invalid conversation ID'}), 400
    
    conversation = Conversation.query.get_or_404(conversation_id)
    user = User.query.get(session['user_id'])
    print(f"[send_message] Conversation found: {conversation.id}")
    print(f"[send_message] User: {user.email}, Role: {user.role}")
    print(f"[send_message] Conversation is_read_only: {conversation.is_read_only}")
    
    # Check authorization - allow admins, support agents, and conversation participants
    is_participant = user.id in [conversation.user1_id, conversation.user2_id]
    is_admin = user.role == 'admin'
    print(f"[send_message] Is participant: {is_participant}, Is admin: {is_admin}")
    
    if not (is_participant or is_admin):
        print(f"[ERROR] Access denied")
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    # Check if conversation is read-only
    if conversation.is_read_only:
        print(f"[ERROR] Conversation is read-only")
        return jsonify({'success': False, 'error': 'This conversation is read-only'}), 403
    
    # Get message text from form data
    message_text = request.form.get('message_text', '').strip()
    print(f"[send_message] Message text: '{message_text[:50]}...' (length: {len(message_text)})")
    
    message_type = 'text'
    image_url = None
    
    # Handle image upload
    if 'image' in request.files:
        file = request.files['image']
        print(f"[send_message] Image file detected: {file.filename}")
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"chat_{timestamp}_{filename}"
            
            # Upload to Supabase
            supabase_path = f"messages/{conversation_id}/{unique_filename}"
            success, result = upload_to_supabase(file, 'epicuremart-uploads', supabase_path)
            
            if success:
                image_url = result  # This is the public URL from Supabase
                message_type = 'image'
                print(f"[send_message] Image uploaded to Supabase: {image_url}")
                # If no text provided with image, use placeholder
                if not message_text:
                    message_text = '[Image]'
            else:
                print(f"[send_message] Image upload failed: {result}")
                return jsonify({'success': False, 'error': f'Failed to upload image: {result}'}), 500
    
    # Validate that we have either text or image
    if not message_text:
        print(f"[ERROR] Message is empty")
        return jsonify({'success': False, 'error': 'Message cannot be empty'}), 400
    
    try:
        # Create message
        message = Message(
            conversation_id=conversation_id,
            sender_id=user.id,
            message_text=message_text,
            message_type=message_type,
            image_url=image_url,
            status='sent'
        )
        print(f"[send_message] Message object created: {message.id}")
        print(f"[send_message] Message.message_type value: '{message.message_type}'")
        print(f"[send_message] Message.image_url value: '{message.image_url}'")
        print(f"[send_message] Message.message_text value: '{message.message_text}'")
        
        # Update conversation timestamp
        old_timestamp = conversation.last_message_at
        conversation.last_message_at = get_philippines_time()
        print(f"[send_message] Conversation last_message_at updated from {old_timestamp} to {conversation.last_message_at}")
        
        # Add both message and conversation to session and commit
        print(f"[send_message] Adding message and conversation to session...")
        db.session.add(message)
        db.session.add(conversation)
        print(f"[send_message] Committing transaction...")
        db.session.commit()
        print(f"[send_message] ✓ Transaction committed successfully")
        
        # Update last activity for support agents and admins
        if user.is_support_agent or user.role == 'admin':
            user.last_activity = get_philippines_time()
            db.session.commit()
        
        # Log admin participation in conversation
        if is_admin and not is_participant:
            log_action('ADMIN_SEND_SUPPORT_MESSAGE', 'Message', message.id, 
                      f'Admin sent message in conversation {conversation_id}')
        
        print(f"[send_message] ✓ Preparing response...")
        
        # Return success with message data
        response_data = {
            'success': True,
            'message': {
                'id': str(message.id),
                'sender_name': user.full_name or user.email,
                'message_text': message.message_text,
                'message_type': message_type,
                'image_url': image_url,
                'created_at': message.created_at.strftime('%I:%M %p'),
                'timestamp': message.created_at.isoformat(),
                'is_own': True,
                'status': 'sent'
            }
        }
        print(f"[send_message] ✓ Sending response: {response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        print(f"[ERROR] Exception occurred: {str(e)}")
        db.session.rollback()
        import traceback
        print(f"[ERROR] Traceback:\n{traceback.format_exc()}")
        return jsonify({'success': False, 'error': f'Failed to send message: {str(e)}'}), 500
    finally:
        print(f"{'='*60}\n")


@app.route('/messages/start/<path:shop_id>', methods=['POST'])
@login_required
@role_required('customer')
def start_conversation(shop_id):
    try:
        import uuid as uuid_lib
        shop_id = uuid_lib.UUID(shop_id)
    except (ValueError, AttributeError):
        flash('Invalid shop ID.', 'danger')
        return redirect(url_for('browse'))
    
    shop = Shop.query.get_or_404(shop_id)
    customer_id = session['user_id']
    seller_id = shop.seller_id
    
    # Defensive check: ensure seller_id is not the same as customer_id
    if seller_id == customer_id:
        print(f"[ERROR] start_conversation: seller_id ({seller_id}) equals customer_id ({customer_id})")
        flash('Cannot start conversation with yourself.', 'danger')
        return redirect(url_for('browse'))
    
    # Ensure seller_id is not None or empty
    if not seller_id:
        print(f"[ERROR] start_conversation: shop.seller_id is None or empty!")
        flash('Shop owner not found.', 'danger')
        return redirect(url_for('browse'))
    
    # Check if conversation already exists
    existing = Conversation.query.filter(
        db.or_(
            db.and_(Conversation.user1_id == customer_id, Conversation.user2_id == seller_id),
            db.and_(Conversation.user1_id == seller_id, Conversation.user2_id == customer_id)
        ),
        Conversation.conversation_type == 'buyer_seller',
        Conversation.shop_id == shop_id
    ).first()
    
    if existing:
        return redirect(url_for('view_conversation', conversation_id=existing.id))
    
    # Create new conversation with explicit IDs
    conversation = Conversation(
        user1_id=customer_id,
        user2_id=seller_id,
        shop_id=shop_id,
        conversation_type='buyer_seller'
    )
    
    db.session.add(conversation)
    db.session.flush()  # Get conversation ID before commit
    
    # Verify the conversation was created correctly before committing
    if conversation.user1_id == conversation.user2_id:
        print(f"[ERROR] Conversation has user1_id == user2_id ({conversation.user1_id})")
        db.session.rollback()
        flash('Error creating conversation. Please try again.', 'danger')
        return redirect(url_for('browse'))
    
    db.session.commit()
    
    log_action('CONVERSATION_STARTED', 'Conversation', conversation.id, f'With shop {shop.name}')
    
    return redirect(url_for('view_conversation', conversation_id=conversation.id))


@app.route('/messages/start-with-rider/<path:order_id>', methods=['POST'])
@login_required
def start_conversation_with_rider(order_id):
    """Start conversation between buyer/seller and rider for an order"""
    try:
        import uuid as uuid_lib
        order_id = uuid_lib.UUID(order_id)
    except (ValueError, AttributeError):
        flash('Invalid order ID.', 'danger')
        return redirect(url_for('browse'))
    order = Order.query.get_or_404(order_id)
    user = User.query.get(session['user_id'])
    
    # Verify user is buyer or seller of this order
    if user.role == 'customer' and order.customer_id != user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('index'))
    
    if user.role == 'seller' and order.shop.seller_id != user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('index'))
    
    if not order.rider_id:
        flash('No rider assigned to this order yet.', 'warning')
        return redirect(url_for('customer_order_detail', order_id=order_id) if user.role == 'customer' else url_for('seller_order_detail', order_id=order_id))
    
    # Determine conversation type
    if user.role == 'customer':
        conv_type = 'buyer_rider'
        other_user_id = order.rider_id
    else:  # seller
        conv_type = 'seller_rider'
        other_user_id = order.rider_id
    
    # Check if conversation already exists
    existing = Conversation.query.filter(
        db.or_(
            db.and_(Conversation.user1_id == user.id, Conversation.user2_id == other_user_id),
            db.and_(Conversation.user1_id == other_user_id, Conversation.user2_id == user.id)
        ),
        Conversation.conversation_type == conv_type,
        Conversation.order_id == order_id
    ).first()
    
    if existing:
        return redirect(url_for('view_conversation', conversation_id=existing.id))
    
    # Create new conversation
    conversation = Conversation(
        user1_id=user.id,
        user2_id=other_user_id,
        order_id=order_id,
        conversation_type=conv_type
    )
    
    db.session.add(conversation)
    db.session.commit()
    
    log_action('CONVERSATION_STARTED', 'Conversation', conversation.id, f'With rider for order {order.order_number}')
    
    return redirect(url_for('view_conversation', conversation_id=conversation.id))


@app.route('/messages/start-with-courier/<path:order_id>')
@login_required
def start_conversation_with_courier(order_id):
    """Start or continue a conversation with the courier for an order"""
    try:
        import uuid as uuid_lib
        order_id = uuid_lib.UUID(order_id)
    except (ValueError, AttributeError):
        flash('Invalid order ID.', 'danger')
        return redirect(url_for('browse'))
    user = User.query.get(session['user_id'])
    order = Order.query.get_or_404(order_id)
    
    # Check authorization - only customer, seller, or courier can access
    if user.role not in ['customer', 'seller'] and user.id != order.courier_id:
        flash('You are not authorized to view this conversation.', 'danger')
        return redirect(url_for('index'))
    
    # Check if order has a courier assigned
    if not order.courier_id:
        flash('No courier has been assigned to this order yet.', 'warning')
        if user.role == 'seller':
            return redirect(url_for('seller_order_detail', order_id=order_id))
        return redirect(url_for('customer_orders'))
    
    courier = User.query.get(order.courier_id)
    
    # Determine conversation type based on who is initiating
    if user.role == 'customer':
        conv_type = 'buyer_courier'
        user1_id = user.id
        user2_id = courier.id
    elif user.role == 'seller':
        conv_type = 'seller_courier'
        user1_id = user.id
        user2_id = courier.id
    else:  # User is the courier
        # Find existing conversation
        if user.id == order.courier_id:
            # Courier responding to buyer or seller
            existing_conv = Conversation.query.filter(
                Conversation.order_id == order_id,
                Conversation.conversation_type.in_(['buyer_courier', 'seller_courier']),
                Conversation.user2_id == user.id
            ).first()
            if existing_conv:
                return redirect(url_for('view_conversation', conversation_id=existing_conv.id))
        flash('Conversation not found.', 'danger')
        return redirect(url_for('courier_dashboard'))
    
    # Check for existing conversation
    existing_conv = Conversation.query.filter(
        Conversation.order_id == order_id,
        Conversation.conversation_type == conv_type,
        Conversation.user1_id == user1_id,
        Conversation.user2_id == user2_id
    ).first()
    
    if existing_conv:
        return redirect(url_for('view_conversation', conversation_id=existing_conv.id))
    
    # Create new conversation
    conversation = Conversation(
        user1_id=user1_id,
        user2_id=user2_id,
        order_id=order.id,
        conversation_type=conv_type
    )
    db.session.add(conversation)
    db.session.commit()
    
    log_action('CONVERSATION_STARTED', 'Conversation', conversation.id, f'With courier for order {order.order_number}')
    
    return redirect(url_for('view_conversation', conversation_id=conversation.id))


# Alias for seller convenience
@app.route('/messages/start-courier-conversation/<path:order_id>')
@login_required
def start_courier_conversation(order_id):
    """Alias for start_conversation_with_courier for easier access"""
    return start_conversation_with_courier(order_id)


@app.route('/messages/start-courier-rider-chat/<path:order_id>')
@login_required
@role_required('courier', 'rider')
def start_courier_rider_chat(order_id):
    """Start conversation between courier and rider for an order"""
    try:
        import uuid as uuid_lib
        order_id = uuid_lib.UUID(order_id)
    except (ValueError, AttributeError):
        flash('Invalid order ID.', 'danger')
        return redirect(url_for('courier_dashboard'))
    order = Order.query.get_or_404(order_id)
    user = User.query.get(session['user_id'])
    
    # Verify user is courier or rider of this order
    if user.role == 'courier' and order.courier_id != user.id:
        flash('You are not the courier for this order.', 'danger')
        return redirect(url_for('courier_dashboard'))
    
    if user.role == 'rider' and order.rider_id != user.id:
        flash('You are not the rider for this order.', 'danger')
        return redirect(url_for('rider_dashboard'))
    
    # Check if both courier and rider are assigned
    if not order.courier_id or not order.rider_id:
        flash('Both courier and rider must be assigned to start chat.', 'warning')
        if user.role == 'courier':
            return redirect(url_for('courier_dashboard'))
        return redirect(url_for('rider_dashboard'))
    
    # Determine the other user
    if user.role == 'courier':
        other_user_id = order.rider_id
    else:  # rider
        other_user_id = order.courier_id
    
    # Check if conversation already exists
    existing = Conversation.query.filter(
        db.or_(
            db.and_(Conversation.user1_id == user.id, Conversation.user2_id == other_user_id),
            db.and_(Conversation.user1_id == other_user_id, Conversation.user2_id == user.id)
        ),
        Conversation.conversation_type == 'courier_rider',
        Conversation.order_id == order_id
    ).first()
    
    if existing:
        return redirect(url_for('view_conversation', conversation_id=existing.id))
    
    # Create new conversation
    conversation = Conversation(
        user1_id=user.id,
        user2_id=other_user_id,
        order_id=order_id,
        conversation_type='courier_rider'
    )
    
    db.session.add(conversation)
    db.session.commit()
    
    log_action('CONVERSATION_STARTED', 'Conversation', conversation.id, f'Courier-Rider chat for order {order.order_number}')
    
    return redirect(url_for('view_conversation', conversation_id=conversation.id))


@app.route('/messages/check-new/<path:conversation_id>')
@login_required
def check_new_messages(conversation_id):
    try:
        import uuid as uuid_lib
        conversation_id = uuid_lib.UUID(conversation_id)
    except (ValueError, AttributeError):
        return jsonify({'success': False, 'error': 'Invalid conversation ID'}), 400
    
    """AJAX endpoint to check for new messages"""
    conversation = Conversation.query.get_or_404(conversation_id)
    user = User.query.get(session['user_id'])
    
    if user.id not in [conversation.user1_id, conversation.user2_id]:
        return jsonify({'success': False}), 403
    
    # Get messages based on timestamp to fetch only new messages
    last_timestamp = request.args.get('last_timestamp', None)
    
    if last_timestamp:
        try:
            from datetime import datetime
            last_time = datetime.fromisoformat(last_timestamp)
            new_messages = Message.query.filter(
                Message.conversation_id == conversation_id,
                Message.created_at > last_time
            ).order_by(Message.created_at.asc()).all()
        except (ValueError, AttributeError):
            new_messages = Message.query.filter(
                Message.conversation_id == conversation_id
            ).order_by(Message.created_at.asc()).all()
    else:
        new_messages = Message.query.filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at.asc()).all()
    
    messages_data = []
    for msg in new_messages:
        messages_data.append({
            'id': str(msg.id),
            'sender_name': msg.sender.full_name or msg.sender.email,
            'message_text': msg.message_text,
            'message_type': msg.message_type,
            'image_url': msg.image_url,
            'created_at': msg.created_at.strftime('%I:%M %p'),
            'timestamp': msg.created_at.isoformat(),
            'is_own': msg.sender_id == user.id
        })
    
    return jsonify({
        'success': True,
        'messages': messages_data
    })


# ==================== SUPPORT CHAT ROUTES ====================


@app.route('/messages/check-new-multi')
@login_required
def check_new_messages_multi():
    """Check new messages across multiple conversations"""
    user = User.query.get(session['user_id'])
    conv_ids_str = request.args.get('conv_ids', '')
    last_timestamp = request.args.get('last_timestamp', None)

    try:
        import uuid as uuid_lib
        conv_ids = [uuid_lib.UUID(c.strip()) for c in conv_ids_str.split(',') if c.strip()]
    except Exception:
        return jsonify({'success': False}), 400

    # Verify user is participant in all these conversations
    valid_ids = []
    for cid in conv_ids:
        conv = Conversation.query.get(cid)
        if conv and user.id in [conv.user1_id, conv.user2_id]:
            valid_ids.append(cid)

    if not valid_ids:
        return jsonify({'success': True, 'messages': []})

    query = Message.query.filter(Message.conversation_id.in_(valid_ids))
    if last_timestamp:
        try:
            from datetime import datetime
            last_time = datetime.fromisoformat(last_timestamp)
            query = query.filter(Message.created_at > last_time)
        except Exception:
            pass

    new_messages = query.order_by(Message.created_at.asc()).all()

    # Mark as read
    for msg in new_messages:
        if msg.sender_id != user.id and not msg.is_read:
            msg.is_read = True
    db.session.commit()

    messages_data = []
    for msg in new_messages:
        messages_data.append({
            'id': str(msg.id),
            'sender_name': msg.sender.full_name or msg.sender.email,
            'message_text': msg.message_text,
            'created_at': msg.created_at.isoformat() if msg.created_at else None,
            'is_own': msg.sender_id == user.id,
            'sender_role': msg.sender.role,
            'image_url': msg.image_url or None,
        })

    return jsonify({'success': True, 'messages': messages_data})

@app.route('/support/start', methods=['GET', 'POST'])
@login_required
def start_support_chat():
    """User initiates a support chat"""
    user = User.query.get(session['user_id'])
    
    # Check if user already has an active support conversation
    existing_conv = Conversation.query.filter(
        Conversation.conversation_type == 'user_support',
        db.or_(Conversation.user1_id == user.id, Conversation.user2_id == user.id)
    ).first()
    
    if existing_conv:
        return redirect(url_for('support_conversation', conversation_id=existing_conv.id))
    
    # Find an available support agent
    support_agent = User.query.filter_by(is_support_agent=True).first()
    
    if not support_agent:
        flash('No support agents are currently available. Please try again later.', 'warning')
        return redirect(request.referrer or url_for('index'))
    
    # Create new support conversation
    conversation = Conversation(
        user1_id=user.id,
        user2_id=support_agent.id,
        conversation_type='user_support'
    )
    db.session.add(conversation)
    db.session.commit()
    
    log_action('SUPPORT_CHAT_STARTED', 'Conversation', conversation.id, f'User {user.full_name} started support chat')
    
    flash('Connected to support. How can we help you?', 'success')
    return redirect(url_for('support_conversation', conversation_id=conversation.id))


@app.route('/support/conversation/<path:conversation_id>')
@login_required
def support_conversation(conversation_id):
    try:
        import uuid as uuid_lib
        conversation_id = uuid_lib.UUID(conversation_id)
    except (ValueError, AttributeError):
        flash('Invalid conversation ID.', 'danger')
        return redirect(url_for('support_dashboard'))
    """View support conversation (for both users, agents, and admins)"""
    conversation = Conversation.query.get_or_404(conversation_id)
    user = User.query.get(session['user_id'])
    
    # Verify access - allow admins, support agents, and conversation participants
    is_participant = user.id in [conversation.user1_id, conversation.user2_id]
    is_admin = user.role == 'admin'
    
    if not (is_participant or is_admin):
        flash('You do not have access to this conversation.', 'danger')
        return redirect(url_for('index'))
    
    # Mark messages as read
    Message.query.filter(
        Message.conversation_id == conversation_id,
        Message.sender_id != user.id,
        Message.is_read == False
    ).update({'is_read': True})
    db.session.commit()
    
    # Get other user - for admins viewing conversations
    if is_admin and not is_participant:
        # Admin is viewing a conversation they're not part of
        # Identify the customer (user1) and support agent (user2)
        customer = conversation.user1
        support_agent = conversation.user2
        other_user = customer  # Default to showing customer info
    else:
        other_user = conversation.user1 if conversation.user2_id == user.id else conversation.user2
    
    # Update last activity for support agents and admins
    if user.is_support_agent or user.role == 'admin':
        user.last_activity = get_philippines_time()
        db.session.commit()
    
    # Log admin access to conversation
    if is_admin and not is_participant:
        log_action('ADMIN_VIEW_SUPPORT_CHAT', 'Conversation', conversation.id, 
                  f'Admin viewed support conversation between {conversation.user1.full_name or conversation.user1.email} and {conversation.user2.full_name or conversation.user2.email}')
    
    return render_template('support_conversation.html',
        conversation=conversation,
        other_user=other_user,
        messages=conversation.messages,
        now=datetime.utcnow,
        current_user=user,
        is_admin=is_admin
    )


@app.route('/support/send-message/<path:conversation_id>', methods=['POST'])
@login_required
def send_support_message(conversation_id):
    """Send a message in support conversation"""
    try:
        import uuid as uuid_lib
        conversation_id = uuid_lib.UUID(conversation_id)
    except (ValueError, AttributeError):
        return jsonify({'success': False, 'error': 'Invalid conversation ID'}), 400
    conversation = Conversation.query.get_or_404(conversation_id)
    user = User.query.get(session['user_id'])
    
    # Verify access - allow admins, support agents, and conversation participants
    is_participant = user.id in [conversation.user1_id, conversation.user2_id]
    is_admin = user.role == 'admin'
    
    if not (is_participant or is_admin):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    message_text = request.form.get('message_text', '').strip()
    
    if not message_text:
        return jsonify({'success': False, 'error': 'Message cannot be empty'}), 400
    
    # Create message
    message = Message(
        conversation_id=conversation_id,
        sender_id=user.id,
        message_text=message_text
    )
    db.session.add(message)
    
    # Update conversation timestamp
    conversation.last_message_at = get_philippines_time()
    db.session.commit()
    
    # Update last activity for support agents and admins
    if user.is_support_agent or user.role == 'admin':
        user.last_activity = get_philippines_time()
        db.session.commit()
    
    # Log admin participation in conversation
    if is_admin and not is_participant:
        log_action('ADMIN_SEND_SUPPORT_MESSAGE', 'Message', message.id, 
                  f'Admin sent message in support conversation {conversation_id}')
    
    return jsonify({'success': True, 'message_id': message.id})


@app.route('/support/dashboard')
@login_required
def support_dashboard():
    """Support agent dashboard showing all support conversations"""
    user = User.query.get(session['user_id'])
    
    if not user.is_support_agent and user.role != 'admin':
        flash('You do not have access to the support dashboard.', 'danger')
        return redirect(url_for('index'))
    
    # Get all support conversations
    conversations = Conversation.query.filter_by(
        conversation_type='user_support'
    ).order_by(Conversation.last_message_at.desc()).all()
    
    # Get unread counts for each conversation
    conv_data = []
    for conv in conversations:
        user_info = conv.user1 if conv.user1_id != user.id else conv.user2
        if conv.user2.is_support_agent or conv.user2.role == 'admin':
            user_info = conv.user1
        
        unread_count = Message.query.filter(
            Message.conversation_id == conv.id,
            Message.sender_id != user.id,
            Message.is_read == False
        ).count()
        
        last_msg = conv.messages[-1] if conv.messages else None
        
        conv_data.append({
            'conversation': conv,
            'user': user_info,
            'unread_count': unread_count,
            'last_message': last_msg
        })
    
    # Update last activity
    user.last_activity = get_philippines_time()
    db.session.commit()
    
    # Get all support agents for status display
    support_agents = User.query.filter_by(is_support_agent=True).all()
    
    # Calculate active agents (last activity within 5 minutes)
    now = datetime.utcnow()
    active_agents_count = sum(
        1 for agent in support_agents 
        if agent.last_activity and (now - agent.last_activity).total_seconds() < 300
    )
    
    return render_template('support_dashboard.html',
        conversations=conv_data,
        support_agents=support_agents,
        active_agents_count=active_agents_count,
        now=now
    )


@app.route('/support/mark-read/<path:conversation_id>', methods=['POST'])
@login_required
def mark_support_read(conversation_id):
    try:
        import uuid as uuid_lib
        conversation_id = uuid_lib.UUID(conversation_id)
    except (ValueError, AttributeError):
        return jsonify({'success': False, 'error': 'Invalid conversation ID'}), 400
    """Mark all messages in conversation as read"""
    conversation = Conversation.query.get_or_404(conversation_id)
    user = User.query.get(session['user_id'])
    
    # Verify access
    if user.id not in [conversation.user1_id, conversation.user2_id]:
        return jsonify({'success': False}), 403
    
    Message.query.filter(
        Message.conversation_id == conversation_id,
        Message.sender_id != user.id,
        Message.is_read == False
    ).update({'is_read': True})
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/admin/manage-support-agents')
@login_required
@role_required('admin')
def manage_support_agents():
    """Admin page to manage support agents"""
    support_agents = User.query.filter_by(is_support_agent=True).all()
    all_users = User.query.filter(User.role != 'admin').order_by(User.full_name).all()
    
    return render_template('admin_support_agents.html',
        support_agents=support_agents,
        all_users=all_users,
        now=datetime.utcnow()
    )


@app.route('/admin/toggle-support-agent/<path:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def toggle_support_agent(user_id):
    """Toggle support agent status for a user"""
    try:
        import uuid as uuid_lib
        user_id = uuid_lib.UUID(user_id)
    except (ValueError, AttributeError):
        flash('Invalid user ID.', 'danger')
        return redirect(url_for('manage_support_agents'))
    user = User.query.get_or_404(user_id)
    admin = User.query.get(session['user_id'])
    
    if user.role == 'admin':
        flash('Cannot modify admin users.', 'danger')
        return redirect(url_for('manage_support_agents'))
    
    # Validation: Check if user is verified
    if not user.is_verified:
        flash(f'Cannot assign support agent role to unverified user {user.full_name or user.email}.', 'danger')
        return redirect(url_for('manage_support_agents'))
    
    # Validation: Check if user is approved
    if not user.is_approved:
        flash(f'Cannot assign support agent role to unapproved user {user.full_name or user.email}.', 'danger')
        return redirect(url_for('manage_support_agents'))
    
    # Validation: Check if user is suspended
    if user.is_suspended:
        flash(f'Cannot assign support agent role to suspended user {user.full_name or user.email}.', 'danger')
        return redirect(url_for('manage_support_agents'))
    
    old_status = user.is_support_agent
    user.is_support_agent = not user.is_support_agent
    new_status = user.is_support_agent
    db.session.commit()
    
    action = 'granted' if user.is_support_agent else 'revoked'
    flash(f'Support agent access {action} for {user.full_name or user.email}.', 'success')
    
    # Enhanced activity logging
    log_action(
        'SUPPORT_AGENT_STATUS_CHANGE', 
        'User', 
        user.id, 
        f'Admin {admin.full_name or admin.email} (ID: {admin.id}) {action} support agent access for {user.full_name or user.email} (ID: {user.id}). Previous status: {old_status}, New status: {new_status}'
    )
    
    return redirect(url_for('manage_support_agents'))


@app.route('/admin/support-conversations')
@login_required
@role_required('admin')
def admin_support_conversations():
    """Admin page to view and manage all support conversations"""
    # Get all support conversations
    conversations = Conversation.query.filter_by(
        conversation_type='user_support'
    ).order_by(Conversation.last_message_at.desc()).all()
    
    # Get conversation data with details
    conv_data = []
    for conv in conversations:
        customer = conv.user1  # Customer is user1
        support_agent = conv.user2  # Support agent is user2
        
        # Get last message
        last_msg = conv.messages[-1] if conv.messages else None
        
        # Count total messages
        total_messages = len(conv.messages)
        
        # Get assigned support agent details
        assigned_agent = support_agent if support_agent.is_support_agent or support_agent.role == 'admin' else None
        
        conv_data.append({
            'conversation': conv,
            'customer': customer,
            'support_agent': assigned_agent,
            'last_message': last_msg,
            'total_messages': total_messages,
            'created_at': conv.created_at,
            'last_message_at': conv.last_message_at
        })
    
    # Get all support agents for statistics
    support_agents = User.query.filter_by(is_support_agent=True).all()
    
    # Calculate active agents (last activity within 5 minutes)
    now = datetime.utcnow()
    active_agents_count = sum(
        1 for agent in support_agents 
        if agent.last_activity and (now - agent.last_activity).total_seconds() < 300
    )
    
    log_action('ADMIN_VIEW_SUPPORT_CONVERSATIONS', 'Conversation', None, 
              f'Admin accessed support conversations overview. Total conversations: {len(conversations)}')
    
    return render_template('admin_support_conversations.html',
        conversations=conv_data,
        support_agents=support_agents,
        active_agents_count=active_agents_count,
        now=now
    )


@app.route('/admin/logs')
@login_required
@role_required('admin')
def admin_logs():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.created_at.desc())\
        .paginate(page=page, per_page=50)
    return render_template('admin_logs.html', logs=logs)

@app.route('/admin/delivery-fees')
@login_required
@role_required('admin')
def admin_delivery_fees():
    base_fee = app.config.get('DELIVERY_BASE_FEE', 50.0)
    inter_island_fee = app.config.get('DELIVERY_INTER_ISLAND_FEE', 30.0)
    return render_template('admin_delivery_fees.html',
        base_fee=base_fee,
        inter_island_fee=inter_island_fee
    )


@app.route('/admin/delivery-fees/update', methods=['POST'])
@login_required
@role_required('admin')
def admin_update_delivery_fees():
    import json
    base_fee = float(request.form.get('base_fee', 50.0))
    inter_island_fee = float(request.form.get('inter_island_fee', 30.0))
    app.config['DELIVERY_BASE_FEE'] = base_fee
    app.config['DELIVERY_INTER_ISLAND_FEE'] = inter_island_fee
    config_path = os.path.join(os.path.dirname(__file__), 'delivery_config.json')
    with open(config_path, 'w') as f:
        json.dump({'base_fee': base_fee, 'inter_island_fee': inter_island_fee}, f)
    log_action('DELIVERY_FEES_UPDATED', 'Config', None, 'Rates updated')
    flash('Delivery fee rates updated successfully.', 'success')
    return redirect(url_for('admin_delivery_fees'))


# ==================== API ROUTES FOR QR SCANNING ====================

@app.route('/api/qr/verify', methods=['POST'])
@login_required
def api_verify_qr():
    """Verify QR token and return order info"""
    token = request.json.get('token')
    
    payload = verify_qr_token(token)
    if not payload:
        return jsonify({'success': False, 'message': 'Invalid or expired token'}), 400
    
    order = Order.query.get(payload['order_id'])
    if not order:
        return jsonify({'success': False, 'message': 'Order not found'}), 404
    
    return jsonify({
        'success': True,
        'order_id': order.id,
        'order_number': order.order_number,
        'status': order.status,
        'type': payload['type']
    })


# Withdrawal endpoints removed; withdrawal feature is disabled.


# ==================== INITIALIZE DATABASE ====================

@app.before_request
def create_tables():
    """Create tables on first request"""
    if not hasattr(app, 'tables_created'):
        db.create_all()
        
        # Create default admin if not exists
        admin = User.query.filter_by(email='admin@epicuremart.com').first()
        if not admin:
            admin = User(
                email='admin@epicuremart.com',
                role='admin',
                full_name='System Admin',
                is_verified=True,
                is_approved=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
        
        # Create default categories
        if Category.query.count() == 0:
            categories = [
                Category(name='Baking Supplies & Ingredients', icon='🧁'),
                Category(name='Coffee, Tea & Beverages', icon='☕'),
                Category(name='Snacks & Candy', icon='🍬'),
                Category(name='Specialty Foods & International Cuisines', icon='🌍'),
                Category(name='Organic and Health Foods', icon='🥗'),
                Category(name='Meal Kits & Prepped Foods', icon='🍱')
            ]
            db.session.add_all(categories)
        
        db.session.commit()
        app.tables_created = True
    
    # Update user activity on every request
    update_user_activity()


@app.route('/api/calabarzon-addresses')
def get_calabarzon_addresses():
    """API endpoint to get CALABARZON address data"""
    import json
    filepath = os.path.join(app.static_folder, 'calabarzon_addresses.json')
    with open(filepath, 'r') as f:
        data = json.load(f)
    return jsonify(data)





# ==================== MOBILE API ENDPOINTS ====================

@app.route('/api/mobile/login', methods=['POST'])
def mobile_login():
    """Mobile app login endpoint - Hybrid Auth (Supabase + Local passwords)"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    user = User.query.filter_by(email=email).first()
    
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # ===== HYBRID AUTH: Try Supabase first, fallback to local password =====
    authenticated = False
    
    # If user has Supabase ID, try Supabase Auth
    if user.supabase_user_id:
        try:
            if supabase:
                auth_response = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
                authenticated = True
                
        except Exception as e:
            # Fall back to local password check if Supabase fails
            if user.check_password(password):
                authenticated = True
    else:
        # No Supabase ID - use old password hash (backwards compatibility)
        if user.check_password(password):
            authenticated = True
    
    if not authenticated:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Check if email is verified
    if not user.is_verified:
        return jsonify({'error': 'Email not verified'}), 403
    
    # Check if account is suspended
    if user.is_suspended:
        return jsonify({'error': 'Account suspended'}), 403
    
    # Check approval status for non-customers
    if user.role in ['seller', 'courier', 'rider'] and not user.is_approved:
        return jsonify({'error': 'Account pending admin approval'}), 403
    
    # Generate JWT token (valid for 30 days)
    token = jwt.encode({
        'user_id': str(user.id),
        'email': user.email,
        'role': user.role,
        'exp': datetime.utcnow() + timedelta(days=30)
    }, app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': str(user.id),
            'email': user.email,
            'role': user.role,
            'full_name': user.full_name,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'phone': user.phone,
            'profile_picture': user.profile_picture,
            'is_approved': user.is_approved
        }
    })

@app.route('/api/mobile/signup', methods=['POST'])
def mobile_signup():
    """Mobile app signup endpoint - Uses Supabase Auth"""
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['email', 'password', 'first_name', 'last_name', 'phone', 'role']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    email = data.get('email')
    password = data.get('password')
    
    # Check if email already exists
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 400
    
    try:
        # Create user in Supabase Auth
        if not supabase:
            return jsonify({'error': 'Authentication service unavailable'}), 503
        
        auth_response = supabase.auth.sign_up({
            "email": email,
            "password": password
        })
        
        supabase_user_id = auth_response.user.id
        
        # Create user record in local database
        user = User(
            email=email,
            supabase_user_id=supabase_user_id,
            first_name=data.get('first_name', ''),
            middle_name=data.get('middle_name', ''),
            last_name=data.get('last_name', ''),
            full_name=f"{data.get('first_name', '')} {data.get('last_name', '')}".strip(),
            phone=data.get('phone', ''),
            role=data.get('role', 'customer'),
            company_name=data.get('company_name'),
            plate_number=data.get('plate_number'),
            vehicle_type=data.get('vehicle_type'),
            is_verified=True,  # Supabase handles verification
            is_approved=data.get('role') == 'customer'  # Customers auto-approved, others need admin approval
        )
        
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Account created successfully. Please verify your email.',
            'user': {
                'id': user.id,
                'email': user.email,
                'role': user.role,
                'full_name': user.full_name,
                'is_approved': user.is_approved
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        error_msg = str(e).lower()
        
        if 'email already exists' in error_msg or 'already registered' in error_msg:
            return jsonify({'error': 'Email already registered'}), 400
        elif 'invalid' in error_msg and 'email' in error_msg:
            return jsonify({'error': 'Invalid email address'}), 400
        else:
            return jsonify({'error': f'Signup failed: {str(e)}'}), 500

@app.route('/api/mobile/user/<path:user_id>', methods=['GET'])
def mobile_get_user(user_id):
    """Get user profile"""
    try:
        import uuid as uuid_lib
        user_id = uuid_lib.UUID(user_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid user ID'}), 400
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'id': user.id,
        'email': user.email,
        'first_name': user.first_name,
        'middle_name': user.middle_name,
        'last_name': user.last_name,
        'full_name': user.full_name,
        'phone': user.phone,
        'role': user.role,
        'company_name': user.company_name,
        'vehicle_type': user.vehicle_type,
        'plate_number': user.plate_number,
        'is_verified': user.is_verified,
        'is_approved': user.is_approved
    })

@app.route('/api/mobile/products', methods=['GET'])
def mobile_get_products():
    """Get all active products"""
    products = Product.query.filter_by(is_active=True).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'description': p.description,
        'price': float(p.price),
        'stock': p.stock,
        'image': p.image,
        'shop_name': p.shop.name
    } for p in products])

@app.route('/api/mobile/categories', methods=['GET'])
def mobile_get_categories():
    """Get all categories"""
    categories = Category.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'icon': c.icon
    } for c in categories])


# ==================== API ENDPOINTS FOR FLUTTER ====================

@app.route('/api/verify-code/<path:user_id>', methods=['POST'])
def api_verify_code(user_id):
    """API endpoint for Flutter app to verify email code"""
    try:
        import uuid as uuid_lib
        user_id = uuid_lib.UUID(user_id)
    except (ValueError, AttributeError):
        return jsonify({'success': False, 'message': 'Invalid user ID'}), 400
    user = User.query.get_or_404(user_id)
    
    if user.is_verified:
        return jsonify({'success': True, 'message': 'Already verified'}), 200
    
    data = request.get_json()
    code = data.get('verification_code', '').strip()
    
    if not code:
        return jsonify({'success': False, 'error': 'Verification code required'}), 400
    
    if user.verification_code != code:
        return jsonify({'success': False, 'error': 'Invalid verification code'}), 400
    
    if user.verification_code_expires and datetime.utcnow() > user.verification_code_expires:
        return jsonify({'success': False, 'error': 'Verification code expired'}), 400
    
    # Verify user
    user.is_verified = True
    user.verification_code = None
    user.verification_code_expires = None
    db.session.commit()
    

    # Auto-confirm in Supabase so account works on both web and app
    if user.supabase_user_id:
        try:
            import requests as _req
            _req.put(
                f"{os.environ.get('SUPABASE_URL')}/auth/v1/admin/users/{user.supabase_user_id}",
                headers={
                    'apikey': os.environ.get('SUPABASE_SERVICE_ROLE_KEY'),
                    'Authorization': f"Bearer {os.environ.get('SUPABASE_SERVICE_ROLE_KEY')}",
                    'Content-Type': 'application/json'
                },
                json={'email_confirm': True}
            )
        except Exception:
            pass
    log_action('EMAIL_VERIFIED', 'User', user.id, 'Verified via Flutter app')
    
    return jsonify({
        'success': True,
        'message': 'Email verified successfully',
        'user': {
            'id': user.id,
            'email': user.email,
            'is_verified': user.is_verified
        }
    }), 200


@app.route('/api/resend-code/<path:user_id>', methods=['POST'])
def api_resend_code(user_id):
    """API endpoint for Flutter app to resend verification code"""
    try:
        import uuid as uuid_lib
        user_id = uuid_lib.UUID(user_id)
    except (ValueError, AttributeError):
        return jsonify({'success': False, 'message': 'Invalid user ID'}), 400
    user = User.query.get_or_404(user_id)
    
    if user.is_verified:
        return jsonify({'success': False, 'error': 'Already verified'}), 400
    
    # Generate new code
    verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    user.verification_code = verification_code
    user.verification_code_expires = datetime.utcnow() + timedelta(hours=48)
    db.session.commit()
    
    # Send email
    send_email(
        user.email,
        'Email Verification Code - Epicuremart',
        f'Your new verification code is: {verification_code}\n\n'
        f'This code will expire in 48 hours.'
    )
    
    return jsonify({
        'success': True,
        'message': 'Verification code sent to email'
    }), 200


@app.route('/api/register', methods=['POST'])
def api_register():
    """API endpoint for Flutter app registration"""
    data = request.get_json()
    
    email = data.get('email')
    supabase_user_id = data.get('supabase_user_id')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    phone = data.get('phone')
    role = data.get('role', 'customer')
    
    # Check if user already exists
    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'error': 'Email already registered'}), 400
    
    # Generate verification code
    verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    full_name = f"{first_name} {last_name}"
    
    # Create user
    user = User(
        email=email,
        supabase_user_id=supabase_user_id,
        password_hash='SUPABASE_AUTH',
        role=role,
        full_name=full_name,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        is_verified=False,
        is_approved=True,
        verification_code=verification_code,
        verification_code_expires=datetime.utcnow() + timedelta(hours=48)
    )
    
    db.session.add(user)
    db.session.commit()
    
    # Send verification email
    send_email(
        user.email,
        'Email Verification Code - Epicuremart',
        f'Welcome to Epicuremart!\n\n'
        f'Your email verification code is: {verification_code}\n\n'
        f'This code will expire in 48 hours.'
    )
    
    log_action('USER_REGISTERED', 'User', user.id, 'Registered via Flutter app')
    
    return jsonify({
        'success': True,
        'user_id': user.id,
        'message': 'Registration successful. Check email for verification code.'
    }), 201


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    # Kukunin nito ang PORT mula sa Railway, o gagamit ng 8080 kung wala
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=False, host='0.0.0.0', port=port)
