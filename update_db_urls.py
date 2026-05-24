"""
Update database with Supabase file URLs after manual upload
Run this AFTER uploading files to Supabase manually
"""

import os
from dotenv import load_dotenv
from app import app, db, User

load_dotenv()

SUPABASE_URL = os.environ.get('SUPABASE_URL')

def main():
    print("=" * 60)
    print("🔄 UPDATING DATABASE WITH SUPABASE URLS")
    print("=" * 60)
    
    if not SUPABASE_URL:
        print("\n✗ SUPABASE_URL not found in .env file!")
        return
    
    # Mapping of database field to (email, field_name, file_type)
    migrations = [
        {
            'email': 'dymolina21@gmail.com',
            'field': 'id_document',
            'old_filename': 'id_customer_dymolina21_ChatGPT_Image_Feb_20_2026_08_05_47_AM.png',
            'bucket_folder': 'users/id_documents'
        },
        {
            'email': 'roelpacia54@gmail.com',
            'field': 'id_document',
            'old_filename': 'id_customer_roelpacia54_ChatGPT_Image_Feb_20_2026_08_05_47_AM.png',
            'bucket_folder': 'users/id_documents'
        },
        {
            'email': 'jxelbarcelona@gmail.com',
            'field': 'id_document',
            'old_filename': 'id_seller_jxelbarcelona_ChatGPT_Image_Feb_20_2026_08_12_22_AM.png',
            'bucket_folder': 'users/id_documents'
        },
        {
            'email': 'jxelbarcelona@gmail.com',
            'field': 'business_permit',
            'old_filename': 'business_permit_jxelbarcelona_760f2e71-80bf-4436-8175-656456c3aa83.jpg',
            'bucket_folder': 'users/business_permits'
        },
    ]
    
    with app.app_context():
        updated = 0
        
        for item in migrations:
            user = User.query.filter_by(email=item['email']).first()
            
            if not user:
                print(f"\n✗ User not found: {item['email']}")
                continue
            
            # Build Supabase URL
            filename = item['old_filename']
            bucket_folder = item['bucket_folder']
            supabase_url = f"{SUPABASE_URL}/storage/v1/object/public/epicuremart-uploads/{bucket_folder}/{filename}"
            
            # Update database
            setattr(user, item['field'], supabase_url)
            updated += 1
            
            print(f"\n✓ Updated {user.email}")
            print(f"  Field: {item['field']}")
            print(f"  URL: {supabase_url}")
        
        # Commit changes
        try:
            db.session.commit()
            print(f"\n{'=' * 60}")
            print(f"[SUCCESS] SUCCESS! {updated} records updated in database")
            print(f"{'=' * 60}")
        except Exception as e:
            print(f"\n✗ Error saving to database: {e}")
            db.session.rollback()

if __name__ == '__main__':
    main()
