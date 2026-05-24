"""
Direct file upload to Supabase with admin access
Uses service_role key for unrestricted upload
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv()

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')  # Should be service_role key
UPLOAD_FOLDER = 'static/uploads'

# Files to migrate
FILES_TO_MIGRATE = [
    {
        'local_path': 'id_customer_dymolina21_ChatGPT_Image_Feb_20_2026_08_05_47_AM.png',
        'bucket_path': 'users/id_documents/id_customer_dymolina21_ChatGPT_Image_Feb_20_2026_08_05_47_AM.png'
    },
    {
        'local_path': 'id_customer_roelpacia54_ChatGPT_Image_Feb_20_2026_08_05_47_AM.png',
        'bucket_path': 'users/id_documents/id_customer_roelpacia54_ChatGPT_Image_Feb_20_2026_08_05_47_AM.png'
    },
    {
        'local_path': 'id_seller_jxelbarcelona_ChatGPT_Image_Feb_20_2026_08_12_22_AM.png',
        'bucket_path': 'users/id_documents/id_seller_jxelbarcelona_ChatGPT_Image_Feb_20_2026_08_12_22_AM.png'
    },
    {
        'local_path': 'business_permit_jxelbarcelona_760f2e71-80bf-4436-8175-656456c3aa83.jpg',
        'bucket_path': 'users/business_permits/business_permit_jxelbarcelona_760f2e71-80bf-4436-8175-656456c3aa83.jpg'
    },
]

def upload_via_rest_api(file_path, bucket_path):
    """Upload file using Supabase REST API"""
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/epicuremart-uploads/{bucket_path}"
        
        headers = {
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/octet-stream'
        }
        
        with open(file_path, 'rb') as f:
            response = requests.post(url, headers=headers, data=f, params={'upsert': 'true'})
        
        if response.status_code in [200, 201]:
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/epicuremart-uploads/{bucket_path}"
            return True, public_url
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
    
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 60)
    print("🚀 DIRECT SUPABASE UPLOAD (REST API)")
    print("=" * 60)
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("\n✗ Missing SUPABASE_URL or SUPABASE_KEY in .env")
        return
    
    print(f"\nSubabase URL: {SUPABASE_URL}")
    print(f"Using Key: {SUPABASE_KEY[:20]}...")
    
    uploaded = 0
    failed = 0
    
    for item in FILES_TO_MIGRATE:
        local_path = os.path.join(UPLOAD_FOLDER, item['local_path'])
        
        if not os.path.exists(local_path):
            print(f"\n✗ File not found: {local_path}")
            failed += 1
            continue
        
        print(f"\n📤 Uploading: {item['local_path']}")
        success, result = upload_via_rest_api(local_path, item['bucket_path'])
        
        if success:
            print(f"  ✓ Success!")
            print(f"  URL: {result}")
            uploaded += 1
        else:
            print(f"  ✗ Failed: {result}")
            failed += 1
    
    print(f"\n{'=' * 60}")
    print(f"📊 Results: {uploaded} uploaded, {failed} failed")
    print(f"{'=' * 60}")
    
    if uploaded == len(FILES_TO_MIGRATE):
        print("\n[SUCCESS] All files uploaded! Now run:")
        print("   python update_db_urls.py")

if __name__ == '__main__':
    main()
