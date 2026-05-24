"""
Migration script to move files from local storage to Supabase Storage
Run this AFTER setting up Supabase and BEFORE deploying
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Import Flask app and models AFTER loading environment
from app import app, db, User, Product, ProductReview, Category, Shop

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
UPLOAD_FOLDER = 'static/uploads'

def init_supabase():
    """Initialize Supabase client"""
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✓ Supabase connected successfully!")
        return supabase
    except Exception as e:
        print(f"✗ Error connecting to Supabase: {e}")
        sys.exit(1)

def upload_file_to_supabase(supabase, file_path, bucket_path):
    """Upload a file to Supabase and return public URL"""
    try:
        # Read file as binary
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # Try to upload with file_options
        response = supabase.storage.from_('epicuremart-uploads').upload(
            path=bucket_path,
            file=file_data,
            file_options={"cacheControl": "3600", "upsert": "true"}
        )
        
        # Get public URL
        public_url = supabase.storage.from_('epicuremart-uploads').get_public_url(bucket_path)
        return True, public_url
    except Exception as e:
        print(f"  ✗ Error uploading {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def migrate_user_files(supabase):
    """Migrate user profile pictures and documents"""
    print("\n📁 Migrating User Files...")
    users = User.query.all()
    migrated = 0
    
    for user in users:
        # Migrate profile picture
        if user.profile_picture and not user.profile_picture.startswith('http'):
            old_path = os.path.join(UPLOAD_FOLDER, user.profile_picture)
            if os.path.exists(old_path):
                bucket_path = f"users/profile_pictures/{user.profile_picture}"
                success, url = upload_file_to_supabase(supabase, old_path, bucket_path)
                if success:
                    user.profile_picture = url
                    migrated += 1
                    print(f"  ✓ Migrated profile picture: {user.email}")
        
        # Migrate ID document
        if user.id_document and not user.id_document.startswith('http'):
            old_path = os.path.join(UPLOAD_FOLDER, user.id_document)
            if os.path.exists(old_path):
                bucket_path = f"users/id_documents/{user.id_document}"
                success, url = upload_file_to_supabase(supabase, old_path, bucket_path)
                if success:
                    user.id_document = url
                    migrated += 1
                    print(f"  ✓ Migrated ID document: {user.email}")
        
        # Migrate business permit
        if user.business_permit and not user.business_permit.startswith('http'):
            old_path = os.path.join(UPLOAD_FOLDER, user.business_permit)
            if os.path.exists(old_path):
                bucket_path = f"users/business_permits/{user.business_permit}"
                success, url = upload_file_to_supabase(supabase, old_path, bucket_path)
                if success:
                    user.business_permit = url
                    migrated += 1
                    print(f"  ✓ Migrated business permit: {user.email}")
        
        # Migrate driver's license
        if user.drivers_license and not user.drivers_license.startswith('http'):
            old_path = os.path.join(UPLOAD_FOLDER, user.drivers_license)
            if os.path.exists(old_path):
                bucket_path = f"users/drivers_licenses/{user.drivers_license}"
                success, url = upload_file_to_supabase(supabase, old_path, bucket_path)
                if success:
                    user.drivers_license = url
                    migrated += 1
                    print(f"  ✓ Migrated driver's license: {user.email}")
        
        # Migrate OR/CR
        if user.or_cr and not user.or_cr.startswith('http'):
            old_path = os.path.join(UPLOAD_FOLDER, user.or_cr)
            if os.path.exists(old_path):
                bucket_path = f"users/or_cr/{user.or_cr}"
                success, url = upload_file_to_supabase(supabase, old_path, bucket_path)
                if success:
                    user.or_cr = url
                    migrated += 1
                    print(f"  ✓ Migrated OR/CR: {user.email}")
        
        # Migrate company logo
        if user.company_logo and not user.company_logo.startswith('http'):
            old_path = os.path.join(UPLOAD_FOLDER, user.company_logo)
            if os.path.exists(old_path):
                bucket_path = f"couriers/company_logos/{user.company_logo}"
                success, url = upload_file_to_supabase(supabase, old_path, bucket_path)
                if success:
                    user.company_logo = url
                    migrated += 1
                    print(f"  ✓ Migrated company logo: {user.email}")
    
    db.session.commit()
    print(f"✓ User files migration complete! ({migrated} files)")

def migrate_product_files(supabase):
    """Migrate product images"""
    print("\n📁 Migrating Product Images...")
    products = Product.query.all()
    migrated = 0
    
    for product in products:
        if product.image and not product.image.startswith('http'):
            old_path = os.path.join(UPLOAD_FOLDER, product.image)
            if os.path.exists(old_path):
                bucket_path = f"products/images/{product.image}"
                success, url = upload_file_to_supabase(supabase, old_path, bucket_path)
                if success:
                    product.image = url
                    migrated += 1
                    print(f"  ✓ Migrated product image: {product.name}")
    
    db.session.commit()
    print(f"✓ Product images migration complete! ({migrated} files)")

def migrate_shop_logos(supabase):
    """Migrate shop logos"""
    print("\n📁 Migrating Shop Logos...")
    shops = Shop.query.all()
    migrated = 0
    
    for shop in shops:
        if shop.logo and not shop.logo.startswith('http'):
            old_path = os.path.join(UPLOAD_FOLDER, shop.logo)
            if os.path.exists(old_path):
                bucket_path = f"shops/logos/{shop.logo}"
                success, url = upload_file_to_supabase(supabase, old_path, bucket_path)
                if success:
                    shop.logo = url
                    migrated += 1
                    print(f"  ✓ Migrated shop logo: {shop.name}")
    
    db.session.commit()
    print(f"✓ Shop logos migration complete! ({migrated} files)")

def migrate_review_images(supabase):
    """Migrate product review images"""
    print("\n📁 Migrating Review Images...")
    reviews = ProductReview.query.all()
    migrated = 0
    
    for review in reviews:
        if review.review_images:
            # review_images is comma-separated filenames
            old_images = review.review_images.split(',')
            new_images = []
            
            for old_image in old_images:
                old_image = old_image.strip()
                if old_image and not old_image.startswith('http'):
                    old_path = os.path.join(UPLOAD_FOLDER, old_image)
                    if os.path.exists(old_path):
                        bucket_path = f"reviews/images/{old_image}"
                        success, url = upload_file_to_supabase(supabase, old_path, bucket_path)
                        if success:
                            new_images.append(url)
                            migrated += 1
                else:
                    # Already a URL or empty
                    if old_image:
                        new_images.append(old_image)
            
            if new_images:
                review.review_images = ','.join(new_images)
                print(f"  ✓ Migrated review images for product {review.product_id}")
    
    db.session.commit()
    print(f"✓ Review images migration complete! ({migrated} files)")

def migrate_category_backgrounds(supabase):
    """Migrate category background images"""
    print("\n📁 Migrating Category Backgrounds...")
    categories = Category.query.all()
    migrated = 0
    
    for category in categories:
        if category.background_image and not category.background_image.startswith('http'):
            old_path = os.path.join(UPLOAD_FOLDER, category.background_image)
            if os.path.exists(old_path):
                bucket_path = f"categories/backgrounds/{category.background_image}"
                success, url = upload_file_to_supabase(supabase, old_path, bucket_path)
                if success:
                    category.background_image = url
                    migrated += 1
                    print(f"  ✓ Migrated category background: {category.name}")
    
    db.session.commit()
    print(f"✓ Category backgrounds migration complete! ({migrated} files)")

def main():
    print("=" * 50)
    print("🚀 SUPABASE FILE MIGRATION")
    print("=" * 50)
    
    # Check if upload folder exists
    if not os.path.exists(UPLOAD_FOLDER):
        print(f"\n✗ Upload folder not found: {UPLOAD_FOLDER}")
        sys.exit(1)
    
    # Check environment variables
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("\n✗ Missing Supabase credentials in .env file!")
        print("  Add SUPABASE_URL and SUPABASE_KEY to .env")
        sys.exit(1)
    
    # Initialize Supabase
    supabase = init_supabase()
    
    # Perform migrations within Flask app context
    with app.app_context():
        try:
            migrate_user_files(supabase)
            migrate_product_files(supabase)
            migrate_shop_logos(supabase)
            migrate_review_images(supabase)
            migrate_category_backgrounds(supabase)
            
            print("\n" + "=" * 50)
            print("✅ MIGRATION COMPLETE!")
            print("=" * 50)
            print("\nYour files have been migrated to Supabase Storage.")
            print("You can now safely delete the 'static/uploads' folder.")
            
        except Exception as e:
            print(f"\n✗ Migration failed: {e}")
            db.session.rollback()
            sys.exit(1)

if __name__ == '__main__':
    main()
