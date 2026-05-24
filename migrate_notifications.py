from app import app, db
from sqlalchemy import text

with app.app_context():
    stmts = [
        "ALTER TABLE notifications ALTER COLUMN user_id TYPE UUID USING user_id::uuid",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS notif_type VARCHAR(50) DEFAULT 'info'",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS order_id UUID REFERENCES orders(id) ON DELETE SET NULL",
    ]
    for s in stmts:
        try:
            db.session.execute(text(s))
            db.session.commit()
            print(f"OK: {s[:70]}")
        except Exception as e:
            db.session.rollback()
            print(f"SKIP ({e.__class__.__name__}): {s[:70]}")

    cols = db.session.execute(text(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='notifications' ORDER BY ordinal_position"
    )).fetchall()
    print("Columns:", cols)
