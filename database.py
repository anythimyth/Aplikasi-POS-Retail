import os
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'pos_retail.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'cashier', -- 'admin' or 'cashier'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );

    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
        sku TEXT UNIQUE NOT NULL,
        buy_price INTEGER NOT NULL DEFAULT 0,
        sell_price INTEGER NOT NULL DEFAULT 0,
        stock INTEGER NOT NULL DEFAULT 0,
        min_stock INTEGER NOT NULL DEFAULT 5,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS stock_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        type TEXT NOT NULL, -- 'IN', 'OUT', 'ADJUSTMENT'
        qty INTEGER NOT NULL,
        previous_stock INTEGER NOT NULL,
        current_stock INTEGER NOT NULL,
        note TEXT,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_number TEXT UNIQUE NOT NULL,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        cashier_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        customer_name TEXT DEFAULT 'Pelanggan Umum',
        total_amount INTEGER NOT NULL,
        total_cost INTEGER NOT NULL,
        payment_amount INTEGER NOT NULL,
        change_amount INTEGER NOT NULL,
        payment_method TEXT DEFAULT 'CASH', -- 'CASH', 'QRIS', 'TRANSFER'
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS transaction_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
        product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
        product_name TEXT NOT NULL,
        sku TEXT NOT NULL,
        buy_price INTEGER NOT NULL,
        sell_price INTEGER NOT NULL,
        qty INTEGER NOT NULL,
        subtotal INTEGER NOT NULL,
        profit INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS stock_opnames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        opname_code TEXT UNIQUE NOT NULL,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        product_name TEXT NOT NULL,
        sku TEXT NOT NULL,
        buy_price INTEGER NOT NULL,
        sell_price INTEGER NOT NULL,
        system_stock INTEGER NOT NULL,
        physical_stock INTEGER NOT NULL,
        difference INTEGER NOT NULL, -- physical_stock - system_stock
        status TEXT NOT NULL, -- 'SESUAI', 'KURANG', 'LEBIH'
        reason TEXT NOT NULL, -- 'HILANG', 'RUSAK', 'KADALUWARSA', 'KOREKSI_HITUNG', 'LAINNYA', 'SESUAI'
        loss_amount INTEGER NOT NULL DEFAULT 0, -- if difference < 0, abs(difference) * buy_price
        notes TEXT,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS store_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    ''')

    # Default store settings
    default_settings = [
        ('store_name', 'Toko Berkah Retail'),
        ('store_address', 'Jl. Merdeka No. 45, Jakarta Pusat'),
        ('store_phone', '0812-3456-7890'),
        ('receipt_footer', 'Terima kasih atas kunjungan Anda!\nBarang yang sudah dibeli tidak dapat ditukar.'),
        ('receipt_paper_size', '58mm')
    ]

    for key, val in default_settings:
        cursor.execute("INSERT OR IGNORE INTO store_settings (key, value) VALUES (?, ?)", (key, val))

    conn.commit()
    conn.close()

def get_setting(key, default=''):
    conn = get_db()
    row = conn.execute("SELECT value FROM store_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT INTO store_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    conn.commit()
    conn.close()

def generate_invoice_number():
    today_str = datetime.now().strftime('%Y%m%d')
    prefix = f"INV-{today_str}-"
    conn = get_db()
    row = conn.execute(
        "SELECT invoice_number FROM transactions WHERE invoice_number LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{prefix}%",)
    ).fetchone()
    conn.close()

    if row:
        last_num = int(row['invoice_number'].split('-')[-1])
        next_num = last_num + 1
    else:
        next_num = 1
    return f"{prefix}{next_num:04d}"

def generate_opname_code():
    today_str = datetime.now().strftime('%Y%m%d')
    prefix = f"OPN-{today_str}-"
    conn = get_db()
    row = conn.execute(
        "SELECT opname_code FROM stock_opnames WHERE opname_code LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{prefix}%",)
    ).fetchone()
    conn.close()

    if row:
        last_num = int(row['opname_code'].split('-')[-1])
        next_num = last_num + 1
    else:
        next_num = 1
    return f"{prefix}{next_num:04d}"
