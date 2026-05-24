#!/usr/bin/env python3
"""
Quick diagnostic script to check rider data in the database
"""
import os
from dotenv import load_dotenv
from app import app, db, User

load_dotenv()

def check_riders():
    with app.app_context():
        print("=" * 80)
        print("RIDER STATUS CHECK")
        print("=" * 80)
        
        # Get all riders (approved and not)
        all_riders = User.query.filter_by(role='rider').all()
        print(f"\nTotal riders in database: {len(all_riders)}\n")
        
        if not all_riders:
            print("No riders found in the database!")
            return
        
        # Show details
        print(f"{'Email':<30} {'Name':<20} {'Approved':<10} {'Courier':<20}")
        print("-" * 80)
        
        for rider in all_riders:
            courier_name = "None"
            if rider.courier_id:
                courier = User.query.get(rider.courier_id)
                courier_name = courier.company_name if courier else "Invalid ID"
            
            print(f"{rider.email:<30} {(rider.full_name or 'N/A'):<20} {str(rider.is_approved):<10} {courier_name:<20}")
        
        # Summary
        approved_count = sum(1 for r in all_riders if r.is_approved)
        print("\n" + "=" * 80)
        print(f"Approved riders: {approved_count}/{len(all_riders)}")
        print("=" * 80)
        
        # Check for issues
        print("\nISSUES DETECTED:")
        unapproved = [r for r in all_riders if not r.is_approved]
        if unapproved:
            print(f"❌ {len(unapproved)} rider(s) not approved:")
            for r in unapproved:
                print(f"   - {r.email} ({r.full_name or 'No name'})")
        
        riders_without_courier = [r for r in all_riders if r.is_approved and not r.courier_id]
        if riders_without_courier:
            print(f"⚠️  {len(riders_without_courier)} approved rider(s) without assigned courier:")
            for r in riders_without_courier:
                print(f"   - {r.email} ({r.full_name or 'No name'})")
        
        riders_with_courier = [r for r in all_riders if r.is_approved and r.courier_id]
        if riders_with_courier:
            print(f"✓ {len(riders_with_courier)} approved rider(s) with assigned courier")

if __name__ == '__main__':
    check_riders()
