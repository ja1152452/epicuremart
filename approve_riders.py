#!/usr/bin/env python3
"""
Quick script to approve all pending riders and show their details
"""
import os
from dotenv import load_dotenv
from app import app, db, User

load_dotenv()

def approve_and_list_riders():
    with app.app_context():
        print("=" * 80)
        print("APPROVING PENDING RIDERS & LISTING ALL RIDERS")
        print("=" * 80)
        
        # First, approve all unapproved riders
        unapproved_riders = User.query.filter_by(role='rider', is_approved=False).all()
        
        if unapproved_riders:
            print(f"\nApproving {len(unapproved_riders)} pending rider(s)...")
            for rider in unapproved_riders:
                rider.is_approved = True
                print(f"  ✓ Approved: {rider.email} ({rider.full_name or 'No name'})")
            
            db.session.commit()
            print("Changes saved to database!")
        else:
            print("\nNo pending riders to approve.")
        
        # Now list all approved riders
        all_approved = User.query.filter_by(role='rider', is_approved=True).all()
        
        print(f"\n{'-' * 80}")
        print(f"TOTAL APPROVED RIDERS: {len(all_approved)}")
        print(f"{'-' * 80}\n")
        
        if not all_approved:
            print("No approved riders found!")
            return
        
        print(f"{'Email':<30} {'Name':<25} {'Courier':<25}")
        print("-" * 80)
        
        for rider in all_approved:
            courier_name = "Not assigned"
            if rider.courier_id:
                courier = User.query.get(rider.courier_id)
                if courier:
                    courier_name = courier.company_name or courier.full_name or "Unknown"
            
            print(f"{rider.email:<30} {(rider.full_name or 'N/A'):<25} {courier_name:<25}")
        
        print("\n" + "=" * 80)
        print("Riders are now ready to be assigned to orders!")
        print("=" * 80)

if __name__ == '__main__':
    approve_and_list_riders()
