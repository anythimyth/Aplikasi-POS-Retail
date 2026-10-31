import sqlite3
from datetime import datetime, timedelta
import random
from werkzeug.security import generate_password_hash
from database import get_db, init_db

def seed():
    init_db()
    conn = get_db()
    cursor = conn.cursor()

    # 1. Seed Users
    users_data = [
        ('admin', generate_password_hash('admin123'), 'Owner / Administrator', 'admin'),
        ('kasir', generate_password_hash('kasir123'), 'Siti Nurhaliza (Kasir)', 'cashier')
    ]
    for u in users_data:
        cursor.execute('''
        INSERT INTO users (username, password_hash, full_name, role)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            password_hash=excluded.password_hash,
            full_name=excluded.full_name,
            role=excluded.role
        ''', u)

    # 2. Seed Categories
    categories = [
        'Makanan & Snack',
        'Minuman Kemasan',
        'Sembako & Bumbu',
        'Perawatan Diri',
        'Kebutuhan Rumah Tangga'
    ]
    for cat in categories:
        cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))

    # Map category names to IDs
    cat_map = {row['name']: row['id'] for row in cursor.execute("SELECT id, name FROM categories").fetchall()}

    # 3. Seed Products (Realistic retail goods in Indonesia with standard barcodes)
    # Notice: some have normal stock, some low stock (below min_stock), some 0 stock
    products = [
        ('Indomie Goreng Spesial 85g', cat_map['Makanan & Snack'], '8998866200224', 2800, 3500, 48, 10),
        ('Indomie Kuah Ayam Bawang 75g', cat_map['Makanan & Snack'], '8998866200118', 2700, 3500, 36, 10),
        ('Chitato Sapi Panggang 68g', cat_map['Makanan & Snack'], '8992775211024', 9200, 11500, 15, 5),
        ('Silverqueen Almond 58g', cat_map['Makanan & Snack'], '8991001100341', 13500, 17000, 8, 10), # Low stock alert! (8 < 10)
        ('Oreo Vanilla 133g', cat_map['Makanan & Snack'], '8992741982019', 8500, 10500, 22, 5),
        
        ('Aqua Air Mineral 600ml', cat_map['Minuman Kemasan'], '8992753111018', 2800, 4000, 60, 15),
        ('Teh Pucuk Harum 350ml', cat_map['Minuman Kemasan'], '8991118120012', 3100, 4500, 40, 12),
        ('Ultra Milk Cokelat 250ml', cat_map['Minuman Kemasan'], '8992752011401', 5800, 7500, 4, 10), # Low stock alert! (4 < 10)
        ('Nescafe Classic 100g', cat_map['Minuman Kemasan'], '8992696401017', 22000, 26500, 12, 5),
        ('Pocari Sweat 500ml', cat_map['Minuman Kemasan'], '8992752101010', 6500, 8500, 0, 5), # Out of stock! (0)

        ('Minyak Goreng Sania 2L', cat_map['Sembako & Bumbu'], '8993005121021', 32000, 36500, 18, 5),
        ('Beras Ramos Premium 5kg', cat_map['Sembako & Bumbu'], '8994551010014', 68000, 76000, 14, 5),
        ('Gula Pasir Gulaku 1kg', cat_map['Sembako & Bumbu'], '8992761011029', 16000, 18500, 25, 8),
        ('Kecap Manis Bango 520ml', cat_map['Sembako & Bumbu'], '8999999042318', 21000, 25000, 6, 8), # Low stock alert! (6 < 8)

        ('Lifebuoy Sabun Cair Total 10 400ml', cat_map['Perawatan Diri'], '8999999512301', 19500, 24000, 16, 5),
        ('Pepsodent Pasta Gigi White 190g', cat_map['Perawatan Diri'], '8999999011123', 12500, 15500, 20, 5),
        ('Sunsilk Shampoo Black Shine 160ml', cat_map['Perawatan Diri'], '8999999120199', 18000, 22500, 11, 5),

        ('Sunlight Pencuci Piring Jeruk Nipis 700ml', cat_map['Kebutuhan Rumah Tangga'], '8999999023451', 13500, 16500, 30, 8),
        ('Rinso Anti Noda Deterjen Bubuk 770g', cat_map['Kebutuhan Rumah Tangga'], '8999999034562', 17000, 21000, 15, 6),
        ('Baygon Anti Nyamuk Spray 600ml', cat_map['Kebutuhan Rumah Tangga'], '8992751101028', 34000, 41000, 7, 5)
    ]

    for name, cat_id, sku, buy_p, sell_p, stock, min_s in products:
        cursor.execute('''
        INSERT INTO products (name, category_id, sku, buy_price, sell_price, stock, min_stock, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(sku) DO UPDATE SET
            name=excluded.name,
            category_id=excluded.category_id,
            buy_price=excluded.buy_price,
            sell_price=excluded.sell_price,
            stock=excluded.stock,
            min_stock=excluded.min_stock
        ''', (name, cat_id, sku, buy_p, sell_p, stock, min_s))

    # 4. Seed initial stock movement records for traceability
    admin_id = cursor.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()['id']
    prod_rows = cursor.execute("SELECT id, stock FROM products").fetchall()
    
    # Check if stock movements already exist
    sm_count = cursor.execute("SELECT count(*) as count FROM stock_movements").fetchone()['count']
    if sm_count == 0:
        for p in prod_rows:
            if p['stock'] > 0:
                cursor.execute('''
                INSERT INTO stock_movements (product_id, type, qty, previous_stock, current_stock, note, user_id)
                VALUES (?, 'IN', ?, 0, ?, 'Stok Awal Inventaris Toko', ?)
                ''', (p['id'], p['stock'], p['stock'], admin_id))

    # 5. Seed some sample historical transactions over the past 3 days so dashboard charts and sales reports look vivid
    trx_count = cursor.execute("SELECT count(*) as count FROM transactions").fetchone()['count']
    if trx_count == 0:
        kasir_id = cursor.execute("SELECT id FROM users WHERE username = 'kasir'").fetchone()['id']
        sample_customers = ['Budi Santoso', 'Ibu Ratna', 'Pak Joko', 'Dewi Lestari', 'Pelanggan Umum', 'Andi Pratama']
        
        all_prods = cursor.execute("SELECT id, name, sku, buy_price, sell_price FROM products WHERE stock > 0").fetchall()
        
        now = datetime.now()
        trx_counter = 100
        
        for days_ago in range(4, -1, -1):
            date_base = now - timedelta(days=days_ago)
            # Create 3-5 transactions per day
            num_trx = random.randint(3, 5) if days_ago > 0 else 2
            for t in range(num_trx):
                trx_counter += 1
                hour = random.randint(8, 20)
                minute = random.randint(10, 55)
                trx_time = date_base.replace(hour=hour, minute=minute, second=0).strftime('%Y-%m-%d %H:%M:%S')
                inv_no = f"INV-{date_base.strftime('%Y%m%d')}-{trx_counter:04d}"
                cust = random.choice(sample_customers)
                
                # Pick 2-4 random items
                chosen_prods = random.sample(all_prods, k=random.randint(2, min(4, len(all_prods))))
                tot_amount = 0
                tot_cost = 0
                items_to_insert = []
                
                for pr in chosen_prods:
                    qty = random.randint(1, 3)
                    subtotal = pr['sell_price'] * qty
                    cost = pr['buy_price'] * qty
                    profit = subtotal - cost
                    tot_amount += subtotal
                    tot_cost += cost
                    items_to_insert.append((pr['id'], pr['name'], pr['sku'], pr['buy_price'], pr['sell_price'], qty, subtotal, profit))
                
                # Cash payment with rounding
                payment = ((tot_amount + 9999) // 10000) * 10000
                if payment < tot_amount:
                    payment = tot_amount
                change = payment - tot_amount
                
                cursor.execute('''
                INSERT INTO transactions (invoice_number, date, cashier_id, customer_name, total_amount, total_cost, payment_amount, change_amount, payment_method, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CASH', 'Transaksi Retail Sukses', ?)
                ''', (inv_no, trx_time, kasir_id, cust, tot_amount, tot_cost, payment, change, trx_time))
                
                new_trx_id = cursor.lastrowid
                for item in items_to_insert:
                    cursor.execute('''
                    INSERT INTO transaction_items (transaction_id, product_id, product_name, sku, buy_price, sell_price, qty, subtotal, profit)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (new_trx_id, *item))

    # 6. Seed sample stock opname audits if none exists
    opn_count = cursor.execute("SELECT count(*) as count FROM stock_opnames").fetchone()['count']
    if opn_count == 0:
        opn_samples = [
            ('OPN-20261028-0001', 'Chitato Sapi Panggang 68g', '8992775211024', 9200, 11500, 17, 15, -2, 'KURANG', 'HILANG', 18400, 'Selisih barang saat audit rak display makanan ringan', admin_id),
            ('OPN-20261028-0002', 'Teh Pucuk Harum 350ml', '8991118120012', 3100, 4500, 42, 40, -2, 'KURANG', 'RUSAK', 6200, 'Kemasan bocor/rusak saat pemindahan ke chiller', admin_id),
            ('OPN-20261029-0001', 'Indomie Goreng Spesial 85g', '8998866200224', 2800, 3500, 48, 48, 0, 'SESUAI', 'SESUAI', 0, 'Pemeriksaan fisik stok akurat sesuai pembukuan', admin_id)
        ]
        for opn in opn_samples:
            p_row = cursor.execute("SELECT id FROM products WHERE sku = ?", (opn[2],)).fetchone()
            if p_row:
                p_id = p_row['id']
                cursor.execute('''
                INSERT INTO stock_opnames (
                    opname_code, product_id, product_name, sku, buy_price, sell_price,
                    system_stock, physical_stock, difference, status, reason, loss_amount,
                    notes, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (opn[0], p_id, opn[1], opn[2], opn[3], opn[4], opn[5], opn[6], opn[7], opn[8], opn[9], opn[10], opn[11], opn[12]))

    conn.commit()
    conn.close()
    print("Database and seed data successfully initialized!")

if __name__ == '__main__':
    seed()
