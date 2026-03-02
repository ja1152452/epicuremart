from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from functools import wraps
from decimal import Decimal
import jwt
import qrcode
import io
import base64
import os
import secrets
import pymysql
pymysql.install_as_MySQLdb()
from sqlalchemy import Numeric


app = Flask(__name__)
# Use environment variable or generate a persistent secret key
# IMPORTANT: In production, set this as an environment variable
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'epicuremart-secret-key-change-in-production-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/epicuremart'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024


# Flask-Mail Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'reynaldo.yasona06@gmail.com'
app.config['MAIL_PASSWORD'] = 'urantilhbyppxpqe'
app.config['MAIL_DEFAULT_SENDER'] = 'Epicuremart <noreply@epicuremart.com>'

db = SQLAlchemy(app)
mail = Mail(app)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

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
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('admin', 'seller', 'customer', 'courier', 'rider'), nullable=False)
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    shop = db.relationship('Shop', backref='owner', uselist=False, cascade='all, delete-orphan')
    addresses = db.relationship('Address', backref='user', cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='customer', foreign_keys='Order.customer_id')
    cart_items = db.relationship('CartItem', backref='user', cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Shop(db.Model):
    __tablename__ = 'shops'
    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    logo = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    products = db.relationship('Product', backref='shop', cascade='all, delete-orphan')


class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))
    background_image = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    products = db.relationship('Product', backref='category')




class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(Numeric(10, 2), nullable=False)  # ✅ FIXED
    stock = db.Column(db.Integer, default=0)
    image = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CartItem(db.Model):
    """Transaction-based cart - each add creates a separate entry"""
    __tablename__ = 'cart_items'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    product = db.relationship('Product')


class Address(db.Model):
    __tablename__ = 'addresses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    courier_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    rider_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    status = db.Column(db.Enum(
        'PENDING_PAYMENT', 'READY_FOR_PICKUP', 'IN_TRANSIT_TO_RIDER',
        'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED'
    ), default='PENDING_PAYMENT')
    
    delivery_address_id = db.Column(db.Integer, db.ForeignKey('addresses.id'))
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
    
    # Proof of Delivery
    proof_of_delivery = db.Column(db.String(255))  # Photo uploaded by rider as proof
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    items = db.relationship('OrderItem', backref='order', cascade='all, delete-orphan')
    delivery_address = db.relationship('Address', foreign_keys=[delivery_address_id])
    shop = db.relationship('Shop', foreign_keys=[shop_id])
    courier = db.relationship('User', foreign_keys=[courier_id])
    rider = db.relationship('User', foreign_keys=[rider_id])


class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(Numeric(10, 2), nullable=False)
    
    product = db.relationship('Product')

class ProductReview(db.Model):
    __tablename__ = 'product_reviews'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    review_text = db.Column(db.Text)
    review_images = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    product = db.relationship('Product', backref='reviews')
    user = db.relationship('User')
    order = db.relationship('Order')


class DeliveryFee(db.Model):
    __tablename__ = 'delivery_fees'
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(100), nullable=False, unique=True)
    province = db.Column(db.String(50), nullable=False)
    fee = db.Column(Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User')

class Conversation(db.Model):
    __tablename__ = 'conversations'
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'))  # Optional, for buyer-seller conversations
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))  # Optional, for order-related conversations
    conversation_type = db.Column(db.Enum('buyer_seller', 'seller_rider', 'buyer_rider', 'user_support', 'user_admin'), nullable=False)
    last_message_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user1 = db.relationship('User', foreign_keys=[user1_id])
    user2 = db.relationship('User', foreign_keys=[user2_id])
    shop = db.relationship('Shop', foreign_keys=[shop_id])
    order = db.relationship('Order', foreign_keys=[order_id])
    messages = db.relationship('Message', backref='conversation', cascade='all, delete-orphan', order_by='Message.created_at')


class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    sender = db.relationship('User')


class WithdrawalRequest(db.Model):
    __tablename__ = 'withdrawal_requests'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(Numeric(10, 2), nullable=False)
    payout_method = db.Column(db.String(50), nullable=False)  # e.g., 'bank_transfer', 'gcash', 'paymaya'
    account_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.Text)
    status = db.Column(db.Enum('pending', 'processing', 'completed', 'rejected'), default='pending')
    rejection_reason = db.Column(db.Text)
    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    processed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
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
            if user.role not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('index'))
            
            if not user.is_approved and user.role in ['seller', 'courier', 'rider']:
                flash('Your account is pending approval.', 'warning')
                return redirect(url_for('pending_approval'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


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
    """Send email notification"""
    try:
        msg = Message(subject, recipients=[to])
        msg.body = body
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def generate_qr_token(order_id, token_type, expiry_hours=24):
    """Generate JWT token for QR code"""
    payload = {
        'order_id': order_id,
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


def generate_order_number():
    """Generate unique order number"""
    import random
    timestamp = datetime.now().strftime('%Y%m%d')
    random_part = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    return f"EM{timestamp}{random_part}"


@app.context_processor
def inject_cart_and_messages():
    """Make cart count and unread messages available to all templates"""
    cart_count = 0
    unread_messages = 0
    
    if 'user_id' in session:
        user_id = session['user_id']
        # Cart count = number of cart item transactions
        cart_count = CartItem.query.filter_by(user_id=user_id).count()
        
        # Unread messages count - messages where user is recipient and not read
        unread_messages = Message.query.join(Conversation).filter(
            db.or_(
                db.and_(Conversation.user1_id == user_id, Message.sender_id != user_id),
                db.and_(Conversation.user2_id == user_id, Message.sender_id != user_id)
            ),
            Message.is_read == False
        ).count()
    
    return dict(cart_count=cart_count, unread_messages=unread_messages)


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
        
        # Validate password match
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))
        
        # Phone validation - required for riders and customers
        if role in ['customer', 'rider', 'courier'] and not phone:
            flash('Contact number is required for this role.', 'danger')
            return redirect(url_for('register'))
        
        # Sellers, couriers, riders need admin approval
        is_approved = True if role == 'customer' else False
        
        # Construct full name
        full_name = f"{first_name} {middle_name} {last_name}".replace('  ', ' ').strip()
        
        user = User(
            email=email,
            role=role,
            full_name=full_name,
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            phone=phone,
            plate_number=plate_number,
            vehicle_type=vehicle_type,
            is_approved=is_approved
        )
        user.set_password(password)
        
        # Handle ID document upload for all roles (including buyers/customers)
        if role in ['customer', 'seller', 'courier', 'rider']:
            if 'id_document' in request.files:
                file = request.files['id_document']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"id_{role}_{email.split('@')[0]}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    user.id_document = filename
                elif role in ['seller', 'courier', 'rider']:
                    flash('Valid ID document is required for this role.', 'danger')
                    return redirect(url_for('register'))
            elif role in ['seller', 'courier', 'rider']:
                flash('ID document upload is required for sellers, couriers, and riders.', 'danger')
                return redirect(url_for('register'))
        
        # Handle business permit for sellers
        if role == 'seller':
            if 'business_permit' in request.files:
                file = request.files['business_permit']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"business_permit_{email.split('@')[0]}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    user.business_permit = filename
                else:
                    flash('Valid business permit is required for sellers.', 'danger')
                    return redirect(url_for('register'))
            else:
                flash('Business permit upload is required for sellers.', 'danger')
                return redirect(url_for('register'))
        
        # Handle driver's license and OR/CR for riders and couriers
        if role in ['rider', 'courier']:
            # Driver's License
            if 'drivers_license' in request.files:
                file = request.files['drivers_license']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"drivers_license_{role}_{email.split('@')[0]}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    user.drivers_license = filename
                else:
                    flash('Valid driver\'s license is required for riders and couriers.', 'danger')
                    return redirect(url_for('register'))
            else:
                flash('Driver\'s license upload is required for riders and couriers.', 'danger')
                return redirect(url_for('register'))
            
            # OR/CR
            if 'or_cr' in request.files:
                file = request.files['or_cr']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"or_cr_{role}_{email.split('@')[0]}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    user.or_cr = filename
                else:
                    flash('Valid OR/CR is required for riders and couriers.', 'danger')
                    return redirect(url_for('register'))
            else:
                flash('OR/CR upload is required for riders and couriers.', 'danger')
                return redirect(url_for('register'))
            
            # Validate plate number and vehicle type
            if not plate_number or not vehicle_type:
                flash('Plate number and vehicle type are required for riders and couriers.', 'danger')
                return redirect(url_for('register'))
        
        db.session.add(user)
        db.session.commit()
        
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
        
        # Generate 6-digit verification code
        verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        user.verification_code = verification_code
        user.verification_code_expires = datetime.utcnow() + timedelta(hours=48)
        db.session.commit()
        
        # Send verification email with code
        send_email(
            user.email,
            'Verify your Epicuremart account',
            f'Your verification code is: {verification_code}\n\nThis code will expire in 48 hours.\nPlease enter this code on the verification page to activate your account.'
        )
        
        log_action('USER_REGISTERED', 'User', user.id, f'New {role} registered')
        
        flash('Registration successful! Please check your email for your verification code.', 'success')
        return redirect(url_for('verify_email_code', user_id=user.id))
    
    return render_template('register.html')


@app.route('/verify-email/<token>')
def verify_email(token):
    """Legacy email verification via token link (kept for backwards compatibility)"""
    payload = verify_qr_token(token)
    if not payload or payload.get('type') != 'email_verify':
        flash('Invalid or expired verification link.', 'danger')
        return redirect(url_for('login'))
    
    user = User.query.get(payload['order_id'])  # Reusing order_id field for user_id
    if user:
        user.is_verified = True
        db.session.commit()
        log_action('EMAIL_VERIFIED', 'User', user.id)
        flash('Email verified successfully! You can now log in.', 'success')
    
    return redirect(url_for('login'))


@app.route('/verify-code/<int:user_id>', methods=['GET', 'POST'])
def verify_email_code(user_id):
    """Email verification using 6-digit code"""
    user = User.query.get_or_404(user_id)
    
    if user.is_verified:
        flash('Your account is already verified.', 'info')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        code = request.form.get('verification_code', '').strip()
        
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
        
        log_action('EMAIL_VERIFIED', 'User', user.id, 'Verified via code')
        flash('Email verified successfully! You can now log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('verify_code.html', user=user)


@app.route('/resend-verification/<int:user_id>', methods=['POST'])
def resend_verification_code(user_id):
    """Resend verification code"""
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


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            if not user.is_verified:
                flash('Please verify your email before logging in.', 'warning')
                return redirect(url_for('login'))
            
            # Check if account is suspended
            if user.is_suspended:
                reason = user.suspension_reason or 'No reason provided'
                flash(f'Your account has been suspended. Reason: {reason}', 'danger')
                return redirect(url_for('login'))
            
            session['user_id'] = user.id
            session['role'] = user.role
            session['profile_picture'] = user.profile_picture  # Add profile picture to session
            session['is_support_agent'] = user.is_support_agent if hasattr(user, 'is_support_agent') else False  # Add support agent status
            
            log_action('USER_LOGIN', 'User', user.id)
            
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
        else:
            flash('Invalid email or password.', 'danger')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    log_action('USER_LOGOUT', 'User', session.get('user_id'))
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


@app.route('/cart/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    """Add product to cart with stock validation"""
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


@app.route('/buy-now/<int:product_id>', methods=['POST'])
@login_required
@role_required('customer')
def buy_now(product_id):
    """Buy Now - Skip cart and go directly to checkout with this product"""
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


@app.route('/cart/remove/<int:cart_item_id>')
@login_required
def remove_from_cart(cart_item_id):
    """Remove a specific cart item transaction"""
    user_id = session['user_id']
    cart_item = CartItem.query.filter_by(id=cart_item_id, user_id=user_id).first_or_404()
    
    db.session.delete(cart_item)
    db.session.commit()
    
    flash('Item removed from cart.', 'info')
    return redirect(url_for('view_cart'))


@app.route('/cart/update/<int:cart_item_id>', methods=['POST'])
@login_required
def update_cart_quantity(cart_item_id):
    """Update quantity of a specific cart item with stock validation"""
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
    city = request.form.get('city')
    postal_code = request.form.get('postal_code')
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
        is_default=is_default
    )
    
    db.session.add(address)
    db.session.commit()
    
    log_action('ADDRESS_ADDED', 'Address', address.id, f'Added {label} address')
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


@app.route('/customer/address/<int:address_id>/set-default', methods=['POST'])
@login_required
@role_required('customer')
def set_default_address(address_id):
    # Unset all defaults
    Address.query.filter_by(user_id=session['user_id']).update({'is_default': False})
    
    # Set new default
    address = Address.query.get_or_404(address_id)
    if address.user_id != session['user_id']:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('customer_profile'))
    
    address.is_default = True
    db.session.commit()
    
    log_action('ADDRESS_SET_DEFAULT', 'Address', address.id)
    flash(f'{address.label} address set as default.', 'success')
    return redirect(url_for('customer_profile'))


@app.route('/customer/address/<int:address_id>/delete', methods=['POST'])
@login_required
@role_required('customer')
def delete_address(address_id):
    address = Address.query.get_or_404(address_id)
    
    if address.user_id != session['user_id']:
        flash('Unauthorized access.', 'danger')
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
    
    log_action('ADDRESS_DELETED', 'Address', address_id, f'Deleted {label} address')
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
        
        # Delete old profile picture if exists
        if user.profile_picture:
            old_file_path = os.path.join(app.config['UPLOAD_FOLDER'], user.profile_picture)
            if os.path.exists(old_file_path):
                try:
                    os.remove(old_file_path)
                except Exception as e:
                    print(f"Error deleting old profile picture: {e}")
        
        # Save new profile picture
        filename = secure_filename(file.filename)
        unique_filename = f"profile_{user.role}_{user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        
        user.profile_picture = unique_filename
        db.session.commit()
        
        # Update session with new profile picture
        session['profile_picture'] = unique_filename
        
        log_action('PROFILE_PICTURE_UPLOADED', 'User', user.id, f'Uploaded profile picture')
        flash('Profile picture updated successfully!', 'success')
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
        
        log_action('PROFILE_PICTURE_DELETED', 'User', user.id, 'Deleted profile picture')
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
            product = Product.query.get(int(product_id_str))
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
            selected_ids = [int(id) for id in session['selected_cart_items'].split(',') if id]
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
        
        # Calculate delivery fee based on address
        delivery_fee_obj = DeliveryFee.query.filter_by(
            province=delivery_address.province
        ).first()
        
        if not delivery_fee_obj and delivery_address.municipality:
            # Try to find by municipality if province not found
            delivery_fee_obj = DeliveryFee.query.filter_by(
                province=delivery_address.province
            ).first()
        
        delivery_fee = float(delivery_fee_obj.fee) if delivery_fee_obj else 50.00  # Default 50 pesos
        
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
            
            # Calculate total with delivery fee
            total_amount = subtotal + delivery_fee
            
            # Calculate commission on subtotal (not including delivery fee) - 5% per transaction
            commission = subtotal * 0.05
            seller_amount = subtotal - commission
            
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
                
                log_action('STOCK_DEDUCTED', 'Product', product.id, 
                          f'Deducted {quantity} units for order {order.order_number}')
            
            log_action('ORDER_CREATED', 'Order', order.id, f'Order {order.order_number}')
        
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
        
        # Send confirmation email
        user = User.query.get(user_id)
        send_email(
            user.email,
            'Order Confirmation',
            f'Your orders have been placed successfully!'
        )
        
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
    
    # Get delivery fee estimate if user has a default address
    default_address = Address.query.filter_by(
        user_id=user_id, 
        is_default=True
    ).first()
    
    estimated_delivery_fee = 50.00  # Default
    if default_address:
        delivery_fee_obj = DeliveryFee.query.filter_by(
            city=default_address.city
        ).first()
        if delivery_fee_obj:
            estimated_delivery_fee = float(delivery_fee_obj.fee)
    
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


@app.route('/customer/order/<int:order_id>')
@login_required
@role_required('customer')
def customer_order_detail(order_id):
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
    
    return render_template('customer_order_detail.html', 
        order=order, 
        qr_data=qr_data,
        reviewable_items=reviewable_items
    )


@app.route('/product/<int:product_id>/review', methods=['POST'])
@login_required
@role_required('customer')
def add_product_review(product_id):
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
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                uploaded_images.append(filename)
    
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
    
    log_action('PRODUCT_REVIEWED', 'ProductReview', review.id, f'{rating} stars')
    flash('Thank you for your review!', 'success')
    return redirect(url_for('customer_order_detail', order_id=order_id))


@app.route('/product/<int:product_id>')
def product_detail(product_id):
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
    """Detailed sales report showing 5% commission breakdown per transaction"""
    user = User.query.get(session['user_id'])
    
    if not user.shop:
        return redirect(url_for('create_shop'))
    
    # Get filter parameters
    status_filter = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Build query
    query = Order.query.filter_by(shop_id=user.shop.id)
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    # Get paginated orders
    orders_pagination = query.order_by(Order.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Calculate totals
    total_orders = query.count()
    delivered_orders = Order.query.filter_by(shop_id=user.shop.id, status='DELIVERED').count()
    
    # Revenue summary
    total_sales = db.session.query(func.sum(Order.subtotal))\
        .filter(Order.shop_id == user.shop.id, Order.status == 'DELIVERED').scalar() or 0
    total_commission = db.session.query(func.sum(Order.commission_amount))\
        .filter(Order.shop_id == user.shop.id, Order.status == 'DELIVERED').scalar() or 0
    total_earnings = db.session.query(func.sum(Order.seller_amount))\
        .filter(Order.shop_id == user.shop.id, Order.status == 'DELIVERED').scalar() or 0
    
    return render_template('seller_sales_report.html',
        shop=user.shop,
        orders=orders_pagination.items,
        pagination=orders_pagination,
        status_filter=status_filter,
        total_orders=total_orders,
        delivered_orders=delivered_orders,
        total_sales=total_sales,
        total_commission=total_commission,
        total_earnings=total_earnings
    )


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
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                logo = filename
        
        shop = Shop(
            seller_id=user.id,
            name=name,
            description=description,
            logo=logo
        )
        db.session.add(shop)
        db.session.commit()
        
        log_action('SHOP_CREATED', 'Shop', shop.id, f'Shop: {name}')
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
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image = filename
        
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
        
        log_action('PRODUCT_CREATED', 'Product', product.id, f'Product: {name}')
        flash('Product created successfully!', 'success')
        return redirect(url_for('seller_products'))
    
    return render_template('create_product.html', categories=categories)


@app.route('/seller/product/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('seller')
def edit_product(product_id):
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
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                product.image = filename
        
        db.session.commit()
        
        log_action('PRODUCT_UPDATED', 'Product', product.id, f'Updated: {product.name}')
        flash('Product updated successfully!', 'success')
        return redirect(url_for('seller_products'))
    
    return render_template('edit_product.html', product=product, categories=categories)


@app.route('/seller/product/<int:product_id>/delete', methods=['POST'])
@login_required
@role_required('seller')
def delete_product(product_id):
    user = User.query.get(session['user_id'])
    product = Product.query.get_or_404(product_id)
    
    if product.shop_id != user.shop.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('seller_products'))
    
    log_action('PRODUCT_DELETED', 'Product', product.id, f'Deleted: {product.name}')
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


@app.route('/seller/order/<int:order_id>')
@login_required
@role_required('seller')
def seller_order_detail(order_id):
    user = User.query.get(session['user_id'])
    order = Order.query.get_or_404(order_id)
    
    if order.shop_id != user.shop.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('seller_orders'))
    
    # Generate QR code for pickup if READY_FOR_PICKUP
    qr_data = None
    if order.status == 'READY_FOR_PICKUP' and order.pickup_token:
        qr_data = generate_qr_code(order.pickup_token)
    
    return render_template('seller_order_detail.html', order=order, qr_data=qr_data)


@app.route('/seller/order/<int:order_id>/mark-ready', methods=['POST'])
@login_required
@role_required('seller')
def mark_order_ready(order_id):
    user = User.query.get(session['user_id'])
    order = Order.query.get_or_404(order_id)
    
    if order.shop_id != user.shop.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('seller_orders'))
    
    if order.status != 'PENDING_PAYMENT':
        flash('Order cannot be marked as ready.', 'warning')
        return redirect(url_for('seller_order_detail', order_id=order_id))
    
    # Generate pickup token for courier
    order.pickup_token = generate_qr_token(order.id, 'pickup')
    order.status = 'READY_FOR_PICKUP'
    db.session.commit()
    
    log_action('ORDER_READY_FOR_PICKUP', 'Order', order.id, f'Order {order.order_number}')
    
    # Notify customer
    send_email(
        order.customer.email,
        'Order Ready for Pickup',
        f'Your order {order.order_number} is ready for pickup!'
    )
    
    flash('Order marked as ready for pickup!', 'success')
    return redirect(url_for('seller_order_detail', order_id=order_id))


# ==================== COURIER ROUTES ====================

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
        .filter(Order.status.in_(['READY_FOR_PICKUP', 'IN_TRANSIT_TO_RIDER']))\
        .order_by(Order.created_at.desc()).all()
    
    # Earnings statistics
    total_deliveries = Order.query.filter_by(courier_id=user_id, status='DELIVERED').count()
    pending_deliveries = Order.query.filter_by(courier_id=user_id)\
        .filter(Order.status.in_(['READY_FOR_PICKUP', 'IN_TRANSIT_TO_RIDER'])).count()
    
    # Total earnings (60% of delivery fee for completed deliveries)
    total_earnings = db.session.query(func.sum(Order.courier_earnings))\
        .filter(Order.courier_id == user_id, Order.status == 'DELIVERED').scalar() or Decimal('0')
    
    # Pending earnings (not yet delivered)
    pending_earnings = db.session.query(func.sum(Order.courier_earnings))\
        .filter(Order.courier_id == user_id, 
                Order.status.in_(['READY_FOR_PICKUP', 'IN_TRANSIT_TO_RIDER'])).scalar() or Decimal('0')
    
    # Withdrawal information - total delivery fees from completed orders
    total_delivery_fees = db.session.query(func.sum(Order.delivery_fee))\
        .filter(Order.courier_id == user_id, Order.status == 'DELIVERED').scalar() or Decimal('0')

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


@app.route('/courier/pickup-manifest')
@login_required
@role_required('courier')
def courier_pickup_manifest():
    # Orders assigned to this courier that are ready for pickup or in transit to rider
    orders = Order.query.filter_by(courier_id=session['user_id'])\
        .filter(Order.status.in_(['READY_FOR_PICKUP', 'IN_TRANSIT_TO_RIDER']))\
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
        
        # Notify customer
        send_email(
            order.customer.email,
            'Order Picked Up',
            f'Your order {order.order_number} has been picked up and is on the way!'
        )
        
        flash(f'Order {order.order_number} picked up successfully!', 'success')
        return redirect(url_for('courier_dashboard'))
    
    return render_template('courier_scan_pickup.html')


@app.route('/courier/handoff/<int:order_id>')
@login_required
@role_required('courier')
def courier_handoff_qr(order_id):
    order = Order.query.get_or_404(order_id)
    
    if order.courier_id != session['user_id']:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('courier_dashboard'))
    
    if order.status != 'IN_TRANSIT_TO_RIDER':
        flash('Order not ready for handoff.', 'warning')
        return redirect(url_for('courier_dashboard'))
    
    # Generate QR for rider to scan
    qr_data = generate_qr_code(order.delivery_token)
    
    return render_template('courier_handoff.html', order=order, qr_data=qr_data)


# ==================== RIDER ROUTES ====================

@app.route('/rider/dashboard')
@login_required
@role_required('rider')
def rider_dashboard():
    from sqlalchemy import func
    
    user_id = session['user_id']
    
    # Show available orders to pickup
    available_orders = Order.query.filter_by(status='IN_TRANSIT_TO_RIDER', rider_id=None)\
        .order_by(Order.created_at.desc()).all()
    
    # Calculate potential earnings for available orders
    for order in available_orders:
        order.potential_earnings = order.delivery_fee * Decimal('0.4')
    
    # Show assigned orders
    my_orders = Order.query.filter_by(rider_id=user_id)\
        .filter(Order.status.in_(['OUT_FOR_DELIVERY']))\
        .order_by(Order.created_at.desc()).all()
    
    # Earnings statistics
    total_deliveries = Order.query.filter_by(rider_id=user_id, status='DELIVERED').count()
    pending_deliveries = Order.query.filter_by(rider_id=user_id, status='OUT_FOR_DELIVERY').count()
    
    # Total earnings (40% of delivery fee for completed deliveries)
    total_earnings = db.session.query(func.sum(Order.rider_earnings))\
        .filter(Order.rider_id == user_id, Order.status == 'DELIVERED').scalar() or Decimal('0')
    
    # Pending earnings (not yet delivered)
    pending_earnings = db.session.query(func.sum(Order.rider_earnings))\
        .filter(Order.rider_id == user_id, Order.status == 'OUT_FOR_DELIVERY').scalar() or Decimal('0')
    
    # Withdrawal information - total delivery fees from completed orders
    total_delivery_fees = db.session.query(func.sum(Order.delivery_fee))\
        .filter(Order.rider_id == user_id, Order.status == 'DELIVERED').scalar() or Decimal('0')
    
    # Rider gets 40% of delivery fees (courier gets 60%)
    rider_commission = total_delivery_fees * Decimal('0.60')  # This is courier's share
    available_to_withdraw = total_earnings  # Already calculated as 40% of delivery fees
    
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
        
        # Assign rider
        order.rider_id = session['user_id']
        order.status = 'OUT_FOR_DELIVERY'
        db.session.commit()
        
        log_action('ORDER_OUT_FOR_DELIVERY', 'Order', order.id, f'Rider received {order.order_number}')
        
        # Notify customer
        send_email(
            order.customer.email,
            'Order Out for Delivery',
            f'Your order {order.order_number} is out for delivery!'
        )
        
        flash(f'Order {order.order_number} received for delivery!', 'success')
        return redirect(url_for('rider_dashboard'))
    
    return render_template('rider_scan_courier.html')


@app.route('/rider/confirm-delivery/<int:order_id>', methods=['GET', 'POST'])
@login_required
@role_required('rider')
def rider_confirm_delivery(order_id):
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
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            
            order.proof_of_delivery = unique_filename
            order.status = 'DELIVERED'
            db.session.commit()
            
            log_action('ORDER_DELIVERED', 'Order', order.id, f'Order {order.order_number} delivered with proof')
            
            # Notify customer and seller
            send_email(
                order.customer.email,
                'Order Delivered',
                f'Your order {order.order_number} has been delivered successfully!'
            )
            
            flash(f'Order {order.order_number} delivered successfully!', 'success')
            return redirect(url_for('rider_dashboard'))
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
    total_riders = User.query.filter(User.role.in_(['rider', 'courier'])).count()
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
    
    # Revenue data for chart (last 7 days/weeks/months depending on filter)
    revenue_chart_data = []
    if time_filter == 'day' or time_filter == 'week':
        # Daily data for last 7 days
        for i in range(6, -1, -1):
            date = now - timedelta(days=i)
            day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            daily_revenue = db.session.query(func.sum(Order.total_amount))\
                .filter(Order.created_at >= day_start, Order.created_at < day_end,
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
            
            weekly_revenue = db.session.query(func.sum(Order.total_amount))\
                .filter(Order.created_at >= week_start, Order.created_at < week_end,
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
            
            monthly_revenue = db.session.query(func.sum(Order.total_amount))\
                .filter(Order.created_at >= month_start, Order.created_at < month_end,
                        Order.status == 'DELIVERED').scalar() or 0
            
            revenue_chart_data.append({
                'label': month_start.strftime('%b %Y'),
                'value': float(monthly_revenue)
            })
    
    recent_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()
    
    return render_template('admin_dashboard.html',
        total_users=total_users,
        total_buyers=total_buyers,
        total_sellers=total_sellers,
        total_riders=total_riders,
        total_orders=total_orders,
        total_products=total_products,
        pending_approvals=pending_approvals,
        total_revenue=total_revenue,
        commission_received=commission_received,
        commission_pending=commission_pending,
        revenue_chart_data=revenue_chart_data,
        time_filter=time_filter,
        start_date=start_date_str,
        end_date=end_date_str,
        recent_logs=recent_logs
    )


@app.route('/admin/approvals')
@login_required
@role_required('admin')
def admin_approvals():
    pending_users = User.query.filter_by(is_approved=False).all()
    return render_template('admin_approvals.html', pending_users=pending_users)


@app.route('/admin/approve/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def approve_user(user_id):
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


@app.route('/admin/reject/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def reject_user(user_id):
    user = User.query.get_or_404(user_id)
    
    log_action('USER_REJECTED', 'User', user.id, f'Rejected {user.role}: {user.email}')
    
    send_email(
        user.email,
        'Account Application',
        f'Unfortunately, your {user.role} account application was not approved.'
    )
    
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
        'rider': User.query.filter(User.role.in_(['rider', 'courier'])).count(),
    }
    
    return render_template('admin_users.html', 
        users=users, 
        role_filter=role_filter,
        role_counts=role_counts
    )


@app.route('/admin/user/suspend/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def suspend_user(user_id):
    """Suspend a user account"""
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


@app.route('/admin/user/unsuspend/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def unsuspend_user(user_id):
    """Unsuspend a user account"""
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


@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def delete_user(user_id):
    """Delete a user account and all associated data"""
    user = User.query.get_or_404(user_id)
    
    if user.role == 'admin':
        flash('Cannot delete admin accounts.', 'danger')
        return redirect(url_for('admin_users'))
    
    user_email = user.email
    user_name = user.full_name
    user_role = user.role
    
    # Delete user (cascading will handle related records)
    db.session.delete(user)
    db.session.commit()
    
    log_action('USER_DELETED', 'User', user_id, f'Deleted {user_role}: {user_name}')
    
    flash(f'User account "{user_name}" deleted successfully.', 'info')
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
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                background_image = unique_filename
        
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


@app.route('/admin/category/<int:category_id>/update', methods=['POST'])
@login_required
@role_required('admin')
def update_category(category_id):
    category = Category.query.get_or_404(category_id)
    
    # Get form data
    name = request.form.get('name')
    description = request.form.get('description')
    icon = request.form.get('icon')
    
    # Handle background image upload
    if 'background_image' in request.files:
        file = request.files['background_image']
        if file and file.filename and allowed_file(file.filename):
            # Delete old background image if exists
            if category.background_image:
                old_file_path = os.path.join(app.config['UPLOAD_FOLDER'], category.background_image)
                try:
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)
                except Exception as e:
                    print(f"Error deleting old background image: {e}")
            
            # Save new background image
            filename = secure_filename(file.filename)
            unique_filename = f"category_bg_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            category.background_image = unique_filename
    
    # Update category fields
    category.name = name
    category.description = description
    category.icon = icon
    
    db.session.commit()
    
    log_action('CATEGORY_UPDATED', 'Category', category.id, f'Updated: {name}')
    flash('Category updated successfully!', 'success')
    return redirect(url_for('admin_categories'))


@app.route('/admin/category/<int:category_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    
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
    
    # Get all conversations where user is either user1 or user2
    conversations = Conversation.query.filter(
        db.or_(
            Conversation.user1_id == user.id,
            Conversation.user2_id == user.id
        )
    ).order_by(Conversation.last_message_at.desc()).all()
    
    # Build conversation data with the "other user" and unread count
    conversation_data = []
    total_unread = 0
    
    for conv in conversations:
        # Determine who the "other user" is
        other_user = conv.user2 if conv.user1_id == user.id else conv.user1
        
        # Count unread messages in this conversation
        unread_count = Message.query.filter(
            Message.conversation_id == conv.id,
            Message.sender_id != user.id,
            Message.is_read == False
        ).count()
        
        total_unread += unread_count
        
        # Get last message
        last_message = Message.query.filter_by(conversation_id=conv.id)\
            .order_by(Message.created_at.desc()).first()
        
        conversation_data.append({
            'conversation': conv,
            'other_user': other_user,
            'unread_count': unread_count,
            'last_message': last_message
        })
    
    return render_template('messages_inbox.html', 
        conversation_data=conversation_data,
        unread_count=total_unread
    )


@app.route('/messages/conversation/<int:conversation_id>')
@login_required
def view_conversation(conversation_id):
    conversation = Conversation.query.get_or_404(conversation_id)
    user = User.query.get(session['user_id'])
    
    # Check authorization
    if user.id not in [conversation.user1_id, conversation.user2_id]:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('messages_inbox'))
    
    # Mark messages as read
    Message.query.filter(
        Message.conversation_id == conversation_id,
        Message.sender_id != user.id,
        Message.is_read == False
    ).update({'is_read': True})
    db.session.commit()
    
    messages = Message.query.filter_by(conversation_id=conversation_id)\
        .order_by(Message.created_at.asc()).all()
    
    return render_template('conversation.html',
        conversation=conversation,
        messages=messages
    )


@app.route('/messages/send/<int:conversation_id>', methods=['POST'])
@login_required
def send_message(conversation_id):
    conversation = Conversation.query.get_or_404(conversation_id)
    user = User.query.get(session['user_id'])
    
    # Check authorization
    if user.id not in [conversation.user1_id, conversation.user2_id]:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    message_text = request.form.get('message_text', '').strip()
    print("DEBUG received message_text =", message_text)
    if not message_text:
        return jsonify({'success': False, 'message': 'Message cannot be empty'}), 400
    
    message = Message(
        conversation_id=conversation_id,
        sender_id=user.id,
        message_text=message_text
    )
    
    conversation.last_message_at = datetime.utcnow()
    
    db.session.add(message)
    db.session.commit()
    
    log_action('MESSAGE_SENT', 'Message', message.id, f'To conversation {conversation_id}')
    
    return jsonify({
        'success': True,
        'message': {
            'id': message.id,
            'sender_name': user.full_name,
            'message_text': message.message_text,
            'created_at': message.created_at.strftime('%I:%M %p'),
            'is_own': True
        }
    })


@app.route('/messages/start/<int:shop_id>', methods=['POST'])
@login_required
@role_required('customer')
def start_conversation(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    
    # Check if conversation already exists
    existing = Conversation.query.filter(
        db.or_(
            db.and_(Conversation.user1_id == session['user_id'], Conversation.user2_id == shop.seller_id),
            db.and_(Conversation.user1_id == shop.seller_id, Conversation.user2_id == session['user_id'])
        ),
        Conversation.conversation_type == 'buyer_seller',
        Conversation.shop_id == shop_id
    ).first()
    
    if existing:
        return redirect(url_for('view_conversation', conversation_id=existing.id))
    
    # Create new conversation
    conversation = Conversation(
        user1_id=session['user_id'],
        user2_id=shop.seller_id,
        shop_id=shop_id,
        conversation_type='buyer_seller'
    )
    
    db.session.add(conversation)
    db.session.commit()
    
    log_action('CONVERSATION_STARTED', 'Conversation', conversation.id, f'With shop {shop.name}')
    
    return redirect(url_for('view_conversation', conversation_id=conversation.id))


@app.route('/messages/start-with-rider/<int:order_id>', methods=['POST'])
@login_required
def start_conversation_with_rider(order_id):
    """Start conversation between buyer/seller and rider for an order"""
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


@app.route('/messages/start-with-courier/<int:order_id>')
@login_required
def start_conversation_with_courier(order_id):
    """Start or continue a conversation with the courier for an order"""
    user = User.query.get(session['user_id'])
    order = Order.query.get_or_404(order_id)
    
    # Check authorization - only buyer or seller can message courier
    if user.role not in ['buyer', 'seller'] and user.id != order.courier_id:
        flash('You are not authorized to view this conversation.', 'danger')
        return redirect(url_for('index'))
    
    # Check if order has a courier assigned
    if not order.courier_id:
        flash('No courier has been assigned to this order yet.', 'warning')
        return redirect(url_for('order_details', order_id=order_id))
    
    courier = User.query.get(order.courier_id)
    
    # Determine conversation type based on who is initiating
    if user.role == 'buyer':
        conv_type = 'buyer_courier'
        user1_id = user.id
        user2_id = courier.id
    elif user.role == 'seller':
        conv_type = 'seller_courier'
        user1_id = order.seller_id
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


@app.route('/messages/check-new/<int:conversation_id>')
@login_required
def check_new_messages(conversation_id):
    """AJAX endpoint to check for new messages"""
    conversation = Conversation.query.get_or_404(conversation_id)
    user = User.query.get(session['user_id'])
    
    if user.id not in [conversation.user1_id, conversation.user2_id]:
        return jsonify({'success': False}), 403
    
    last_message_id = request.args.get('last_id', 0, type=int)
    
    new_messages = Message.query.filter(
        Message.conversation_id == conversation_id,
        Message.id > last_message_id
    ).order_by(Message.created_at.asc()).all()
    
    messages_data = []
    for msg in new_messages:
        messages_data.append({
            'id': msg.id,
            'sender_name': msg.sender.full_name,
            'message_text': msg.message_text,
            'created_at': msg.created_at.strftime('%I:%M %p'),
            'is_own': msg.sender_id == user.id
        })
    
    return jsonify({
        'success': True,
        'messages': messages_data
    })


# ==================== SUPPORT CHAT ROUTES ====================

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


@app.route('/support/conversation/<int:conversation_id>')
@login_required
def support_conversation(conversation_id):
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
        user.last_activity = datetime.utcnow()
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


@app.route('/support/send-message/<int:conversation_id>', methods=['POST'])
@login_required
def send_support_message(conversation_id):
    """Send a message in support conversation"""
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
    conversation.last_message_at = datetime.utcnow()
    db.session.commit()
    
    # Update last activity for support agents and admins
    if user.is_support_agent or user.role == 'admin':
        user.last_activity = datetime.utcnow()
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
    user.last_activity = datetime.utcnow()
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


@app.route('/support/mark-read/<int:conversation_id>', methods=['POST'])
@login_required
def mark_support_read(conversation_id):
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


@app.route('/admin/toggle-support-agent/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def toggle_support_agent(user_id):
    """Toggle support agent status for a user"""
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
    from sqlalchemy import func
    delivery_fees = DeliveryFee.query.order_by(DeliveryFee.province, DeliveryFee.city).all()
    
    avg_fee = db.session.query(func.avg(DeliveryFee.fee)).scalar() or 0
    min_fee = db.session.query(func.min(DeliveryFee.fee)).scalar() or 0
    max_fee = db.session.query(func.max(DeliveryFee.fee)).scalar() or 0
    
    return render_template('admin_delivery_fees.html',
        delivery_fees=delivery_fees,
        avg_fee=avg_fee,
        min_fee=min_fee,
        max_fee=max_fee
    )


@app.route('/admin/delivery-fees/add', methods=['POST'])
@login_required
@role_required('admin')
def add_delivery_fee():
    city = request.form.get('city')
    province = request.form.get('province')
    fee = request.form.get('fee')
    
    existing = DeliveryFee.query.filter_by(city=city).first()
    if existing:
        flash('Delivery fee for this city already exists.', 'warning')
        return redirect(url_for('admin_delivery_fees'))
    
    delivery_fee = DeliveryFee(city=city, province=province, fee=fee)
    db.session.add(delivery_fee)
    db.session.commit()
    
    log_action('DELIVERY_FEE_ADDED', 'DeliveryFee', delivery_fee.id, f'{city}: ₱{fee}')
    flash(f'Delivery fee added for {city}.', 'success')
    return redirect(url_for('admin_delivery_fees'))


@app.route('/admin/delivery-fees/<int:fee_id>/update', methods=['POST'])
@login_required
@role_required('admin')
def update_delivery_fee(fee_id):
    delivery_fee = DeliveryFee.query.get_or_404(fee_id)
    new_fee = request.form.get('fee')
    old_fee = delivery_fee.fee
    
    delivery_fee.fee = new_fee
    db.session.commit()
    
    log_action('DELIVERY_FEE_UPDATED', 'DeliveryFee', fee_id, 
               f'{delivery_fee.city}: ₱{old_fee} → ₱{new_fee}')
    flash(f'Delivery fee updated for {delivery_fee.city}.', 'success')
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


# ==================== WITHDRAWAL REQUEST ROUTES ====================

@app.route('/withdrawal/request', methods=['GET', 'POST'])
@login_required
def withdrawal_request():
    """Handle withdrawal request form for sellers, couriers, riders, and admins"""
    from sqlalchemy import func
    
    user = User.query.get(session['user_id'])
    
    # Check if user is eligible for withdrawals
    if user.role not in ['seller', 'courier', 'rider', 'admin']:
        flash('You are not authorized to make withdrawal requests.', 'danger')
        return redirect(url_for('index'))
    
    # Calculate available balance based on user role
    available_balance = 0
    if user.role == 'seller':
        if not user.shop:
            flash('You need to create a shop before requesting withdrawals.', 'warning')
            return redirect(url_for('create_shop'))
        # Sum of seller_amount from delivered orders minus pending/completed withdrawals
        total_earnings = db.session.query(func.sum(Order.seller_amount))\
            .filter(Order.shop_id == user.shop.id, Order.status == 'DELIVERED').scalar() or 0
        withdrawn = db.session.query(func.sum(WithdrawalRequest.amount))\
            .filter(WithdrawalRequest.user_id == user.id, 
                   WithdrawalRequest.status.in_(['pending', 'processing', 'completed'])).scalar() or 0
        available_balance = float(total_earnings) - float(withdrawn)
        
    elif user.role == 'courier':
        # Sum of courier_earnings from delivered orders minus withdrawals
        total_earnings = db.session.query(func.sum(Order.courier_earnings))\
            .filter(Order.courier_id == user.id, Order.status == 'DELIVERED').scalar() or 0
        withdrawn = db.session.query(func.sum(WithdrawalRequest.amount))\
            .filter(WithdrawalRequest.user_id == user.id, 
                   WithdrawalRequest.status.in_(['pending', 'processing', 'completed'])).scalar() or 0
        available_balance = float(total_earnings) - float(withdrawn)
        
    elif user.role == 'rider':
        # Sum of rider_earnings from delivered orders minus withdrawals
        total_earnings = db.session.query(func.sum(Order.rider_earnings))\
            .filter(Order.rider_id == user.id, Order.status == 'DELIVERED').scalar() or 0
        withdrawn = db.session.query(func.sum(WithdrawalRequest.amount))\
            .filter(WithdrawalRequest.user_id == user.id, 
                   WithdrawalRequest.status.in_(['pending', 'processing', 'completed'])).scalar() or 0
        available_balance = float(total_earnings) - float(withdrawn)
        
    elif user.role == 'admin':
        # Admins can see total commission earnings
        total_earnings = db.session.query(func.sum(Order.commission_amount))\
            .filter(Order.status == 'DELIVERED').scalar() or 0
        withdrawn = db.session.query(func.sum(WithdrawalRequest.amount))\
            .filter(WithdrawalRequest.user_id == user.id, 
                   WithdrawalRequest.status.in_(['pending', 'processing', 'completed'])).scalar() or 0
        available_balance = float(total_earnings) - float(withdrawn)
    
    if request.method == 'POST':
        amount = request.form.get('amount', type=float)
        payout_method = request.form.get('payout_method')
        account_name = request.form.get('account_name')
        account_number = request.form.get('account_number')
        notes = request.form.get('notes', '')
        
        # Validation
        errors = []
        if not amount or amount <= 0:
            errors.append('Please enter a valid amount.')
        elif amount < 100:
            errors.append('Minimum withdrawal amount is ₱100.00')
        elif amount > available_balance:
            errors.append(f'Insufficient balance. Available: ₱{available_balance:.2f}')
        
        if not payout_method:
            errors.append('Please select a payout method.')
        if not account_name or len(account_name.strip()) < 3:
            errors.append('Please enter a valid account name.')
        if not account_number or len(account_number.strip()) < 5:
            errors.append('Please enter a valid account number.')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
        else:
            # Create withdrawal request
            # Admin withdrawals are automatically completed, others are pending
            withdrawal_status = 'completed' if user.role == 'admin' else 'pending'
            
            withdrawal = WithdrawalRequest(
                user_id=user.id,
                amount=amount,
                payout_method=payout_method,
                account_name=account_name.strip(),
                account_number=account_number.strip(),
                notes=notes.strip() if notes else None,
                status=withdrawal_status
            )
            
            # If admin, set processed_by and processed_at automatically
            if user.role == 'admin':
                withdrawal.processed_by = user.id
                withdrawal.processed_at = datetime.utcnow()
            
            db.session.add(withdrawal)
            db.session.commit()
            
            # Different messages for admin vs other roles
            if user.role == 'admin':
                flash(f'Withdrawal request for ₱{amount:.2f} completed successfully! Your commission has been processed.', 'success')
            else:
                flash(f'Withdrawal request for ₱{amount:.2f} submitted successfully! It will be processed within 1-3 business days.', 'success')
            
            return redirect(url_for('withdrawal_history'))
    
    return render_template('withdrawal_request.html', 
                         user=user, 
                         available_balance=available_balance)


@app.route('/withdrawal/history')
@login_required
def withdrawal_history():
    """Display withdrawal history for the current user"""
    from sqlalchemy import func
    
    user = User.query.get(session['user_id'])
    
    # Check if user is eligible for withdrawals
    if user.role not in ['seller', 'courier', 'rider', 'admin']:
        flash('You are not authorized to view withdrawal history.', 'danger')
        return redirect(url_for('index'))
    
    # Get withdrawal requests
    withdrawals = WithdrawalRequest.query.filter_by(user_id=user.id)\
        .order_by(WithdrawalRequest.created_at.desc()).all()
    
    # Calculate statistics
    total_withdrawn = db.session.query(func.sum(WithdrawalRequest.amount))\
        .filter(WithdrawalRequest.user_id == user.id, 
               WithdrawalRequest.status == 'completed').scalar() or 0
    
    pending_amount = db.session.query(func.sum(WithdrawalRequest.amount))\
        .filter(WithdrawalRequest.user_id == user.id, 
               WithdrawalRequest.status.in_(['pending', 'processing'])).scalar() or 0
    
    # Calculate available balance
    available_balance = 0
    if user.role == 'seller' and user.shop:
        total_earnings = db.session.query(func.sum(Order.seller_amount))\
            .filter(Order.shop_id == user.shop.id, Order.status == 'DELIVERED').scalar() or 0
        withdrawn = db.session.query(func.sum(WithdrawalRequest.amount))\
            .filter(WithdrawalRequest.user_id == user.id, 
                   WithdrawalRequest.status.in_(['pending', 'processing', 'completed'])).scalar() or 0
        available_balance = float(total_earnings) - float(withdrawn)
    elif user.role == 'courier':
        total_earnings = db.session.query(func.sum(Order.courier_earnings))\
            .filter(Order.courier_id == user.id, Order.status == 'DELIVERED').scalar() or 0
        withdrawn = db.session.query(func.sum(WithdrawalRequest.amount))\
            .filter(WithdrawalRequest.user_id == user.id, 
                   WithdrawalRequest.status.in_(['pending', 'processing', 'completed'])).scalar() or 0
        available_balance = float(total_earnings) - float(withdrawn)
    elif user.role == 'rider':
        total_earnings = db.session.query(func.sum(Order.rider_earnings))\
            .filter(Order.rider_id == user.id, Order.status == 'DELIVERED').scalar() or 0
        withdrawn = db.session.query(func.sum(WithdrawalRequest.amount))\
            .filter(WithdrawalRequest.user_id == user.id, 
                   WithdrawalRequest.status.in_(['pending', 'processing', 'completed'])).scalar() or 0
        available_balance = float(total_earnings) - float(withdrawn)
    elif user.role == 'admin':
        total_earnings = db.session.query(func.sum(Order.commission_amount))\
            .filter(Order.status == 'DELIVERED').scalar() or 0
        withdrawn = db.session.query(func.sum(WithdrawalRequest.amount))\
            .filter(WithdrawalRequest.user_id == user.id, 
                   WithdrawalRequest.status.in_(['pending', 'processing', 'completed'])).scalar() or 0
        available_balance = float(total_earnings) - float(withdrawn)
    
    return render_template('withdrawal_history.html',
                         user=user,
                         withdrawals=withdrawals,
                         total_withdrawn=float(total_withdrawn),
                         pending_amount=float(pending_amount),
                         available_balance=available_balance)


@app.route('/admin/withdrawals')
@login_required
@role_required('admin')
def admin_withdrawals():
    """Admin view of all withdrawal requests"""
    from sqlalchemy import func
    
    status_filter = request.args.get('status', 'all')
    
    # Build query
    query = WithdrawalRequest.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    withdrawals = query.order_by(WithdrawalRequest.created_at.desc()).all()
    
    # Statistics
    total_pending = WithdrawalRequest.query.filter_by(status='pending').count()
    total_processing = WithdrawalRequest.query.filter_by(status='processing').count()
    total_completed = WithdrawalRequest.query.filter_by(status='completed').count()
    
    pending_amount = db.session.query(func.sum(WithdrawalRequest.amount))\
        .filter(WithdrawalRequest.status == 'pending').scalar() or 0
    
    return render_template('admin_withdrawals.html',
                         withdrawals=withdrawals,
                         status_filter=status_filter,
                         total_pending=total_pending,
                         total_processing=total_processing,
                         total_completed=total_completed,
                         pending_amount=float(pending_amount))


@app.route('/admin/withdrawals/<int:withdrawal_id>/update', methods=['POST'])
@login_required
@role_required('admin')
def admin_update_withdrawal(withdrawal_id):
    """Admin updates withdrawal status"""
    withdrawal = WithdrawalRequest.query.get_or_404(withdrawal_id)
    
    new_status = request.form.get('status')
    rejection_reason = request.form.get('rejection_reason', '')
    
    if new_status not in ['pending', 'processing', 'completed', 'rejected']:
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_withdrawals'))
    
    old_status = withdrawal.status
    withdrawal.status = new_status
    withdrawal.processed_by = session['user_id']
    withdrawal.processed_at = datetime.utcnow()
    
    if new_status == 'rejected' and rejection_reason:
        withdrawal.rejection_reason = rejection_reason
    
    db.session.commit()
    
    log_action('WITHDRAWAL_STATUS_UPDATED', 'WithdrawalRequest', withdrawal_id,
              f'Status: {old_status} → {new_status}')
    
    flash(f'Withdrawal request #{withdrawal_id} updated to {new_status}.', 'success')
    return redirect(url_for('admin_withdrawals'))


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


@app.route('/api/calabarzon-addresses')
def get_calabarzon_addresses():
    """API endpoint to get CALABARZON address data"""
    import json
    filepath = os.path.join(app.static_folder, 'calabarzon_addresses.json')
    with open(filepath, 'r') as f:
        data = json.load(f)
    return jsonify(data)


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5000)