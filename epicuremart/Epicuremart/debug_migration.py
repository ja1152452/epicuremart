"""
Debug script to check what files need migration
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import Flask app and models AFTER loading environment
from app import app, db, User, Product, ProductReview, Category, Shop

UPLOAD_FOLDER = 'static/uploads'

def main():
    print("=" * 50)
    print("🔍 MIGRATION DEBUG CHECK")
    print("=" * 50)
    
    # Check if upload folder exists
    if not os.path.exists(UPLOAD_FOLDER):
        print(f"\n✗ Upload folder not found: {UPLOAD_FOLDER}")
        return
    
    print(f"\n✓ Upload folder found: {UPLOAD_FOLDER}")
    
    # List all files in upload folder
    all_files = []
    for filename in os.listdir(UPLOAD_FOLDER):
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.isfile(filepath):
            all_files.append(filename)
    
    print(f"\n📁 Total files in {UPLOAD_FOLDER}: {len(all_files)}")
    if all_files:
        print("   Files:")
        for f in all_files[:10]:  # Show first 10
            print(f"   - {f}")
        if len(all_files) > 10:
            print(f"   ... and {len(all_files) - 10} more")
    
    # Check database records
    with app.app_context():
        print("\n📊 DATABASE RECORDS CHECK:")
        
        users = User.query.all()
        print(f"\n  Users with files:")
        
        users_with_profile = [u for u in users if u.profile_picture and not u.profile_picture.startswith('http')]
        print(f"    - profile_picture: {len(users_with_profile)}")
        
        users_with_id = [u for u in users if u.id_document and not u.id_document.startswith('http')]
        print(f"    - id_document: {len(users_with_id)}")
        
        users_with_permit = [u for u in users if u.business_permit and not u.business_permit.startswith('http')]
        print(f"    - business_permit: {len(users_with_permit)}")
        
        users_with_license = [u for u in users if u.drivers_license and not u.drivers_license.startswith('http')]
        print(f"    - drivers_license: {len(users_with_license)}")
        
        users_with_orcr = [u for u in users if u.or_cr and not u.or_cr.startswith('http')]
        print(f"    - or_cr: {len(users_with_orcr)}")
        
        users_with_logo = [u for u in users if u.company_logo and not u.company_logo.startswith('http')]
        print(f"    - company_logo: {len(users_with_logo)}")
        
        # Sample data
        if users_with_id:
            print(f"\n  Sample user with id_document:")
            user = users_with_id[0]
            print(f"    Email: {user.email}")
            print(f"    id_document: {user.id_document}")
        
        # Check products
        products = Product.query.all()
        products_with_image = [p for p in products if p.image and not p.image.startswith('http')]
        print(f"\n  Products with image: {len(products_with_image)}")
        
        # Check shops
        shops = Shop.query.all()
        shops_with_logo = [s for s in shops if s.logo and not s.logo.startswith('http')]
        print(f"  Shops with logo: {len(shops_with_logo)}")
        
        # Check reviews
        reviews = ProductReview.query.all()
        reviews_with_images = [r for r in reviews if r.review_images and not r.review_images.startswith('http')]
        print(f"  Reviews with images: {len(reviews_with_images)}")
        
        # Check categories
        categories = Category.query.all()
        categories_with_bg = [c for c in categories if c.background_image and not c.background_image.startswith('http')]
        print(f"  Categories with background: {len(categories_with_bg)}")
        
        total_records = len(users_with_profile) + len(users_with_id) + len(users_with_permit) + \
                       len(users_with_license) + len(users_with_orcr) + len(users_with_logo) + \
                       len(products_with_image) + len(shops_with_logo) + len(reviews_with_images) + \
                       len(categories_with_bg)
        
        print(f"\n  📌 TOTAL RECORDS NEEDING MIGRATION: {total_records}")
        
        if total_records == 0:
            print("\n  [WARNING] No files found in database that need migration!")
            print("    - Either all files are already URLs")
            print("    - Or database is empty")
            print("    - Or files were already migrated")

if __name__ == '__main__':
    main()
