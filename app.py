import os
import io
import json
import calendar
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for, 
    flash, session, jsonify, abort, send_file
)
from werkzeug.security import check_password_hash, generate_password_hash
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from database import (
    get_db, init_db, get_setting, set_setting, 
    generate_invoice_number, generate_opname_code
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pos-retail-secret-key-2026')

# Inisialisasi database otomatis saat aplikasi pertama kali dimuat
# (diperlukan agar Gunicorn/Render dapat menginisialisasi DB tanpa menjalankan __main__)
from database import init_db as _init_db
with app.app_context():
    _init_db()

# Custom Jinja filters
@app.template_filter('rupiah')
def rupiah_filter(value):
    try:
        val = int(value or 0)
        return f"Rp {val:,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return f"Rp {value}"

@app.template_filter('datetime_format')
def datetime_format_filter(value):
    if not value:
        return '-'
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', ''))
        return dt.strftime('%d/%m/%Y %H:%M')
    except Exception:
        return str(value)

# Context processor for store settings & current user
@app.context_processor
def inject_global_data():
    store_name = get_setting('store_name', 'Toko Berkah Retail')
    store_address = get_setting('store_address', 'Jl. Merdeka No. 45, Jakarta')
    store_phone = get_setting('store_phone', '0812-3456-7890')
    receipt_paper_size = get_setting('receipt_paper_size', '58mm')
    
    # Check low stock count for notification badge
    conn = get_db()
    low_stock_count = conn.execute(
        "SELECT count(*) as cnt FROM products WHERE stock <= min_stock AND is_active = 1"
    ).fetchone()['cnt']
    conn.close()

    return {
        'store_name': store_name,
        'store_address': store_address,
        'store_phone': store_phone,
        'receipt_paper_size': receipt_paper_size,
        'low_stock_count': low_stock_count,
        'current_user': {
            'id': session.get('user_id'),
            'username': session.get('username'),
            'full_name': session.get('full_name'),
            'role': session.get('role')
        } if 'user_id' in session else None
    }

# Decorators for auth
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu untuk mengakses sistem.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Akses ditolak! Menu ini hanya dapat diakses oleh Admin / Pemilik Toko.', 'danger')
            return redirect(url_for('pos'))
        return f(*args, **kwargs)
    return decorated_function

# ----------------- AUTH ROUTES -----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('dashboard'))
        return redirect(url_for('pos'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            flash(f"Selamat datang kembali, {user['full_name']}!", 'success')
            
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            if user['role'] == 'admin':
                return redirect(url_for('dashboard'))
            return redirect(url_for('pos'))
        else:
            flash('Username atau kata sandi tidak valid. Coba lagi.', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah keluar dari sistem.', 'info')
    return redirect(url_for('login'))

# ----------------- MAIN NAVIGATION -----------------
@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('dashboard'))
        return redirect(url_for('pos'))
    return redirect(url_for('login'))

# ----------------- DASHBOARD -----------------
@app.route('/dashboard')
@admin_required
def dashboard():
    conn = get_db()
    today_str = datetime.now().strftime('%Y-%m-%d')

    # Today's stats
    today_stats = conn.execute('''
        SELECT 
            COALESCE(SUM(total_amount), 0) as today_omzet,
            COALESCE(SUM(total_amount - total_cost), 0) as today_profit,
            COUNT(id) as today_trx_count
        FROM transactions 
        WHERE date(date) = ?
    ''', (today_str,)).fetchone()

    # Overall inventory stats
    inv_stats = conn.execute('''
        SELECT 
            COUNT(id) as total_products,
            COALESCE(SUM(stock), 0) as total_stock_items,
            COALESCE(SUM(stock * buy_price), 0) as total_asset_value,
            SUM(CASE WHEN stock <= min_stock AND stock > 0 THEN 1 ELSE 0 END) as low_stock_count,
            SUM(CASE WHEN stock = 0 THEN 1 ELSE 0 END) as out_of_stock_count
        FROM products 
        WHERE is_active = 1
    ''').fetchone()

    # Low stock items list (for critical action table)
    low_stock_items = conn.execute('''
        SELECT p.*, c.name as category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.stock <= p.min_stock AND p.is_active = 1
        ORDER BY p.stock ASC
        LIMIT 10
    ''').fetchall()

    # Top selling items (overall or last 30 days)
    top_selling = conn.execute('''
        SELECT 
            ti.product_name,
            ti.sku,
            SUM(ti.qty) as total_qty_sold,
            SUM(ti.subtotal) as total_revenue,
            SUM(ti.profit) as total_profit
        FROM transaction_items ti
        JOIN transactions t ON ti.transaction_id = t.id
        GROUP BY ti.product_id, ti.product_name, ti.sku
        ORDER BY total_qty_sold DESC
        LIMIT 5
    ''').fetchall()

    # Last 7 days trend for chart
    chart_dates = []
    chart_omzet = []
    chart_profit = []
    for i in range(6, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        chart_dates.append(datetime.strptime(d, '%Y-%m-%d').strftime('%d %b'))
        row = conn.execute('''
            SELECT 
                COALESCE(SUM(total_amount), 0) as omzet,
                COALESCE(SUM(total_amount - total_cost), 0) as profit
            FROM transactions 
            WHERE date(date) = ?
        ''', (d,)).fetchone()
        chart_omzet.append(row['omzet'])
        chart_profit.append(row['profit'])

    # Recent transactions
    recent_transactions = conn.execute('''
        SELECT t.*, u.full_name as cashier_name,
               (SELECT COUNT(*) FROM transaction_items WHERE transaction_id = t.id) as item_count
        FROM transactions t
        LEFT JOIN users u ON t.cashier_id = u.id
        ORDER BY t.date DESC
        LIMIT 6
    ''').fetchall()

    # Stock opname loss stats
    opname_stats = conn.execute('''
        SELECT 
            COUNT(id) as total_opnames,
            COALESCE(SUM(loss_amount), 0) as total_loss,
            COALESCE(SUM(CASE WHEN difference < 0 THEN abs(difference) ELSE 0 END), 0) as total_lost_units
        FROM stock_opnames
    ''').fetchone()

    conn.close()

    return render_template(
        'dashboard.html',
        today_stats=today_stats,
        inv_stats=inv_stats,
        low_stock_items=low_stock_items,
        top_selling=top_selling,
        chart_dates=json.dumps(chart_dates),
        chart_omzet=json.dumps(chart_omzet),
        chart_profit=json.dumps(chart_profit),
        recent_transactions=recent_transactions,
        opname_stats=opname_stats
    )

# ----------------- INVENTORY & STOCK -----------------
@app.route('/inventory')
@admin_required
def inventory():
    conn = get_db()
    categories = conn.execute("SELECT * FROM categories ORDER BY name ASC").fetchall()
    
    # Query parameters for search & filter
    q = request.args.get('q', '').strip()
    cat_filter = request.args.get('category', '').strip()
    status_filter = request.args.get('status', '').strip() # 'low', 'out', 'safe'

    query = '''
        SELECT p.*, c.name as category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_active = 1
    '''
    params = []

    if q:
        query += " AND (p.name LIKE ? OR p.sku LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])

    if cat_filter:
        query += " AND p.category_id = ?"
        params.append(cat_filter)

    if status_filter == 'low':
        query += " AND p.stock <= p.min_stock AND p.stock > 0"
    elif status_filter == 'out':
        query += " AND p.stock = 0"
    elif status_filter == 'warning':
        query += " AND p.stock <= p.min_stock"
    elif status_filter == 'safe':
        query += " AND p.stock > p.min_stock"

    query += " ORDER BY p.stock <= p.min_stock DESC, p.name ASC"

    products = conn.execute(query, params).fetchall()
    conn.close()

    return render_template(
        'inventory.html',
        products=products,
        categories=categories,
        q=q,
        cat_filter=cat_filter,
        status_filter=status_filter
    )

@app.route('/api/products', methods=['POST'])
@admin_required
def api_add_product():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    sku = data.get('sku', '').strip()
    category_id = data.get('category_id') or None
    buy_price = int(data.get('buy_price') or 0)
    sell_price = int(data.get('sell_price') or 0)
    stock = int(data.get('stock') or 0)
    min_stock = int(data.get('min_stock') or 5)

    if not name or not sku:
        return jsonify({'success': False, 'message': 'Nama produk dan SKU / Barcode wajib diisi.'}), 400

    conn = get_db()
    existing = conn.execute("SELECT id FROM products WHERE sku = ?", (sku,)).fetchone()
    if existing:
        conn.close()
        return jsonify({'success': False, 'message': f"SKU / Barcode '{sku}' sudah terdaftar pada produk lain!"}), 400

    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (name, category_id, sku, buy_price, sell_price, stock, min_stock)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (name, category_id, sku, buy_price, sell_price, stock, min_stock))
    prod_id = cursor.lastrowid

    # Record initial stock in stock_movements if stock > 0
    if stock > 0:
        cursor.execute('''
            INSERT INTO stock_movements (product_id, type, qty, previous_stock, current_stock, note, user_id)
            VALUES (?, 'IN', ?, 0, ?, 'Stok Awal Produk Baru', ?)
        ''', (prod_id, stock, stock, session.get('user_id')))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Produk berhasil ditambahkan!', 'product_id': prod_id})

@app.route('/api/products/<int:prod_id>', methods=['GET', 'PUT', 'DELETE'])
@admin_required
def api_product_detail(prod_id):
    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'GET':
        prod = cursor.execute("SELECT * FROM products WHERE id = ?", (prod_id,)).fetchone()
        conn.close()
        if not prod:
            return jsonify({'success': False, 'message': 'Produk tidak ditemukan'}), 404
        return jsonify({'success': True, 'product': dict(prod)})

    elif request.method == 'PUT':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        sku = data.get('sku', '').strip()
        category_id = data.get('category_id') or None
        buy_price = int(data.get('buy_price') or 0)
        sell_price = int(data.get('sell_price') or 0)
        min_stock = int(data.get('min_stock') or 5)

        if not name or not sku:
            conn.close()
            return jsonify({'success': False, 'message': 'Nama produk dan Barcode harus diisi'}), 400

        # Check unique sku on other products
        duplicate = cursor.execute("SELECT id FROM products WHERE sku = ? AND id != ?", (sku, prod_id)).fetchone()
        if duplicate:
            conn.close()
            return jsonify({'success': False, 'message': 'SKU / Barcode telah digunakan produk lain'}), 400

        cursor.execute('''
            UPDATE products 
            SET name = ?, sku = ?, category_id = ?, buy_price = ?, sell_price = ?, min_stock = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (name, sku, category_id, buy_price, sell_price, min_stock, prod_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Produk berhasil diperbarui!'})

    elif request.method == 'DELETE':
        # Soft delete or hard delete if no transactions
        has_trx = cursor.execute("SELECT id FROM transaction_items WHERE product_id = ? LIMIT 1", (prod_id,)).fetchone()
        if has_trx:
            # Soft delete
            cursor.execute("UPDATE products SET is_active = 0 WHERE id = ?", (prod_id,))
        else:
            cursor.execute("DELETE FROM products WHERE id = ?", (prod_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Produk berhasil dihapus.'})

@app.route('/api/stock/adjust', methods=['POST'])
@admin_required
def api_stock_adjust():
    """Handle stock adjustments: Restock (IN), Opname / Correction (ADJUSTMENT), Damage / Shrinkage (OUT)"""
    data = request.get_json() or {}
    product_id = data.get('product_id')
    adjust_type = data.get('type') # 'IN', 'OUT', 'ADJUSTMENT'
    qty = int(data.get('qty') or 0)
    note = data.get('note', '').strip()

    if not product_id or adjust_type not in ['IN', 'OUT', 'ADJUSTMENT']:
        return jsonify({'success': False, 'message': 'Parameter tidak valid'}), 400

    conn = get_db()
    cursor = conn.cursor()
    prod = cursor.execute("SELECT id, name, stock FROM products WHERE id = ?", (product_id,)).fetchone()
    if not prod:
        conn.close()
        return jsonify({'success': False, 'message': 'Produk tidak ditemukan'}), 404

    previous_stock = prod['stock']

    if adjust_type == 'IN':
        if qty <= 0:
            conn.close()
            return jsonify({'success': False, 'message': 'Jumlah barang masuk harus lebih dari 0'}), 400
        current_stock = previous_stock + qty
        default_note = f"Barang Masuk (Restock / Supplier): +{qty}"
    elif adjust_type == 'OUT':
        if qty <= 0 or qty > previous_stock:
            conn.close()
            return jsonify({'success': False, 'message': 'Jumlah barang keluar tidak valid atau melebihi stok yang ada'}), 400
        current_stock = previous_stock - qty
        default_note = f"Barang Keluar (Rusak / Kadaluarsa): -{qty}"
    elif adjust_type == 'ADJUSTMENT':
        current_stock = qty # In opname adjustment, qty is the final physical count
        qty_diff = current_stock - previous_stock
        default_note = f"Penyesuaian Stok Fisik (Opname): {'+' if qty_diff >= 0 else ''}{qty_diff}"

    cursor.execute("UPDATE products SET stock = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (current_stock, product_id))
    cursor.execute('''
        INSERT INTO stock_movements (product_id, type, qty, previous_stock, current_stock, note, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (product_id, adjust_type, qty, previous_stock, current_stock, note or default_note, session.get('user_id')))

    conn.commit()
    conn.close()
    return jsonify({
        'success': True, 
        'message': f"Stok untuk '{prod['name']}' berhasil diperbarui menjadi {current_stock} unit.",
        'new_stock': current_stock
    })

@app.route('/api/stock/history/<int:prod_id>')
@admin_required
def api_stock_history(prod_id):
    conn = get_db()
    movements = conn.execute('''
        SELECT sm.*, u.full_name as user_name
        FROM stock_movements sm
        LEFT JOIN users u ON sm.user_id = u.id
        WHERE sm.product_id = ?
        ORDER BY sm.created_at DESC
        LIMIT 30
    ''', (prod_id,)).fetchall()
    prod = conn.execute("SELECT id, name, sku, stock FROM products WHERE id = ?", (prod_id,)).fetchone()
    conn.close()

    if not prod:
        return jsonify({'success': False, 'message': 'Produk tidak ditemukan'}), 404

    return jsonify({
        'success': True,
        'product': dict(prod),
        'history': [dict(m) for m in movements]
    })

# ----------------- POINT OF SALE (POS) -----------------
@app.route('/pos')
@login_required
def pos():
    conn = get_db()
    categories = conn.execute("SELECT * FROM categories ORDER BY name ASC").fetchall()
    # Initial load of active products for catalog selector
    products_rows = conn.execute('''
        SELECT p.id, p.name, p.sku, p.sell_price, p.stock, p.min_stock, c.name as category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_active = 1
        ORDER BY p.name ASC
    ''').fetchall()
    products = [dict(r) for r in products_rows]
    conn.close()

    return render_template(
        'pos.html',
        categories=categories,
        products=products
    )

@app.route('/api/pos/search')
@login_required
def api_pos_search():
    query = request.args.get('q', '').strip()
    conn = get_db()
    
    # Exact SKU match (for immediate barcode scan detection)
    exact_match = conn.execute('''
        SELECT p.*, c.name as category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.sku = ? AND p.is_active = 1
    ''', (query,)).fetchone()

    if exact_match:
        conn.close()
        return jsonify({
            'success': True,
            'is_exact': True,
            'product': dict(exact_match)
        })

    # Substring search for dropdown / suggestions
    results = conn.execute('''
        SELECT p.*, c.name as category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE (p.name LIKE ? OR p.sku LIKE ?) AND p.is_active = 1
        ORDER BY p.name ASC
        LIMIT 20
    ''', (f"%{query}%", f"%{query}%")).fetchall()
    conn.close()

    return jsonify({
        'success': True,
        'is_exact': False,
        'products': [dict(r) for r in results]
    })

@app.route('/api/pos/checkout', methods=['POST'])
@login_required
def api_pos_checkout():
    data = request.get_json() or {}
    items = data.get('items', [])
    customer_name = data.get('customer_name', 'Pelanggan Umum').strip() or 'Pelanggan Umum'
    payment_method = data.get('payment_method', 'CASH').upper()
    payment_amount = int(data.get('payment_amount') or 0)
    note = data.get('note', '').strip()

    if not items:
        return jsonify({'success': False, 'message': 'Keranjang transaksi masih kosong!'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Atomic transaction
        cursor.execute("BEGIN TRANSACTION")

        total_amount = 0
        total_cost = 0
        validated_items = []

        for item in items:
            prod_id = item.get('id')
            qty = int(item.get('qty', 1))

            if qty <= 0:
                continue

            # Lock product and check stock
            prod = cursor.execute("SELECT * FROM products WHERE id = ? AND is_active = 1", (prod_id,)).fetchone()
            if not prod:
                cursor.execute("ROLLBACK")
                conn.close()
                return jsonify({'success': False, 'message': f"Produk dengan ID {prod_id} tidak ditemukan atau non-aktif!"}), 400

            if prod['stock'] < qty:
                cursor.execute("ROLLBACK")
                conn.close()
                return jsonify({
                    'success': False, 
                    'message': f"Stok tidak mencukupi untuk '{prod['name']}'! Stok tersedia: {prod['stock']}, diminta: {qty}"
                }), 400

            subtotal = prod['sell_price'] * qty
            cost = prod['buy_price'] * qty
            profit = subtotal - cost
            
            total_amount += subtotal
            total_cost += cost

            validated_items.append({
                'product_id': prod['id'],
                'product_name': prod['name'],
                'sku': prod['sku'],
                'buy_price': prod['buy_price'],
                'sell_price': prod['sell_price'],
                'qty': qty,
                'subtotal': subtotal,
                'profit': profit,
                'new_stock': prod['stock'] - qty,
                'previous_stock': prod['stock']
            })

        if total_amount <= 0:
            cursor.execute("ROLLBACK")
            conn.close()
            return jsonify({'success': False, 'message': 'Total transaksi tidak valid!'}), 400

        # Validate payment
        if payment_method == 'CASH' and payment_amount < total_amount:
            cursor.execute("ROLLBACK")
            conn.close()
            return jsonify({
                'success': False, 
                'message': f"Nominal pembayaran kurang! Total: {total_amount}, Diterima: {payment_amount}"
            }), 400

        if payment_method in ['QRIS', 'TRANSFER']:
            payment_amount = total_amount
            change_amount = 0
        else:
            change_amount = payment_amount - total_amount

        # Generate invoice number
        invoice_number = generate_invoice_number()
        cashier_id = session.get('user_id')

        # Insert transaction
        cursor.execute('''
            INSERT INTO transactions (
                invoice_number, date, cashier_id, customer_name,
                total_amount, total_cost, payment_amount, change_amount,
                payment_method, note
            ) VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (invoice_number, cashier_id, customer_name, total_amount, total_cost, payment_amount, change_amount, payment_method, note))
        
        transaction_id = cursor.lastrowid

        # Insert items and deduct stock
        for v_item in validated_items:
            cursor.execute('''
                INSERT INTO transaction_items (
                    transaction_id, product_id, product_name, sku,
                    buy_price, sell_price, qty, subtotal, profit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                transaction_id, v_item['product_id'], v_item['product_name'], v_item['sku'],
                v_item['buy_price'], v_item['sell_price'], v_item['qty'], v_item['subtotal'], v_item['profit']
            ))

            # Deduct stock
            cursor.execute('''
                UPDATE products 
                SET stock = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (v_item['new_stock'], v_item['product_id']))

            # Record stock movement
            cursor.execute('''
                INSERT INTO stock_movements (
                    product_id, type, qty, previous_stock, current_stock, note, user_id
                ) VALUES (?, 'OUT', ?, ?, ?, ?, ?)
            ''', (
                v_item['product_id'], v_item['qty'], v_item['previous_stock'],
                v_item['new_stock'], f"Penjualan Kasir #{invoice_number}", cashier_id
            ))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Transaksi berhasil disimpan!',
            'invoice_number': invoice_number,
            'total_amount': total_amount,
            'payment_amount': payment_amount,
            'change_amount': change_amount,
            'customer_name': customer_name,
            'payment_method': payment_method
        })

    except Exception as e:
        cursor.execute("ROLLBACK")
        conn.close()
        return jsonify({'success': False, 'message': f"Terjadi kesalahan saat transaksi: {str(e)}"}), 500

@app.route('/api/pos/receipt/<invoice_number>')
@login_required
def api_pos_receipt(invoice_number):
    conn = get_db()
    trx = conn.execute('''
        SELECT t.*, u.full_name as cashier_name
        FROM transactions t
        LEFT JOIN users u ON t.cashier_id = u.id
        WHERE t.invoice_number = ?
    ''', (invoice_number,)).fetchone()

    if not trx:
        conn.close()
        return jsonify({'success': False, 'message': 'Faktur transaksi tidak ditemukan'}), 404

    items = conn.execute('''
        SELECT * FROM transaction_items WHERE transaction_id = ?
    ''', (trx['id'],)).fetchall()
    conn.close()

    store_name = get_setting('store_name', 'Toko Berkah Retail')
    store_address = get_setting('store_address', 'Jl. Merdeka No. 45, Jakarta')
    store_phone = get_setting('store_phone', '0812-3456-7890')
    receipt_footer = get_setting('receipt_footer', 'Terima kasih atas kunjungan Anda!')

    return jsonify({
        'success': True,
        'store': {
            'name': store_name,
            'address': store_address,
            'phone': store_phone,
            'footer': receipt_footer
        },
        'transaction': dict(trx),
        'items': [dict(it) for it in items]
    })

# Indonesian month names mapping
INDONESIAN_MONTHS = [
    (1, 'Januari'), (2, 'Februari'), (3, 'Maret'), (4, 'April'),
    (5, 'Mei'), (6, 'Juni'), (7, 'Juli'), (8, 'Agustus'),
    (9, 'September'), (10, 'Oktober'), (11, 'November'), (12, 'Desember')
]

# ----------------- REPORTS & HISTORY -----------------
@app.route('/reports')
@login_required
def reports():
    is_admin = session.get('role') == 'admin'
    conn = get_db()
    today = datetime.now()

    # Determine active tab ('monthly' or 'history')
    active_tab = request.args.get('tab', 'monthly')

    # Get available years for dropdown from transaction history
    year_rows = conn.execute("SELECT DISTINCT strftime('%Y', date) as yr FROM transactions WHERE date IS NOT NULL ORDER BY yr DESC").fetchall()
    available_years = [int(r['yr']) for r in year_rows if r['yr']]
    if today.year not in available_years:
        available_years.insert(0, today.year)
    available_years = sorted(list(set(available_years)), reverse=True)

    # 1. MONTHLY REPORT FILTER & DATA
    try:
        selected_month = int(request.args.get('month', today.month))
    except (ValueError, TypeError):
        selected_month = today.month

    try:
        selected_year = int(request.args.get('year', today.year))
    except (ValueError, TypeError):
        selected_year = today.year

    days_in_month = calendar.monthrange(selected_year, selected_month)[1]
    month_start_date = f"{selected_year:04d}-{selected_month:02d}-01"
    month_end_date = f"{selected_year:04d}-{selected_month:02d}-{days_in_month:02d}"
    selected_month_name = dict(INDONESIAN_MONTHS).get(selected_month, f"Bulan {selected_month}")

    # Monthly Summary KPI
    m_summary_query = '''
        SELECT 
            COUNT(t.id) as trx_count,
            COALESCE(SUM(t.total_amount), 0) as total_omzet,
            COALESCE(SUM(t.total_cost), 0) as total_cost,
            COALESCE(SUM(t.total_amount - t.total_cost), 0) as total_profit
        FROM transactions t
        WHERE date(t.date) BETWEEN ? AND ?
    '''
    m_params = [month_start_date, month_end_date]
    if not is_admin:
        m_summary_query += " AND t.cashier_id = ?"
        m_params.append(session.get('user_id'))

    monthly_summary = conn.execute(m_summary_query, m_params).fetchone()

    # Monthly Top Selling Items
    m_top_selling_query = '''
        SELECT 
            ti.product_name,
            ti.sku,
            SUM(ti.qty) as total_qty,
            SUM(ti.subtotal) as total_sales,
            SUM(ti.profit) as total_profit
        FROM transaction_items ti
        JOIN transactions t ON ti.transaction_id = t.id
        WHERE date(t.date) BETWEEN ? AND ?
    '''
    m_top_params = [month_start_date, month_end_date]
    if not is_admin:
        m_top_selling_query += " AND t.cashier_id = ?"
        m_top_params.append(session.get('user_id'))
    m_top_selling_query += " GROUP BY ti.product_id, ti.product_name, ti.sku ORDER BY total_qty DESC LIMIT 10"
    monthly_top_selling = conn.execute(m_top_selling_query, m_top_params).fetchall()

    # Monthly Daily Trend Chart & Breakdown
    m_daily_query = '''
        SELECT 
            CAST(strftime('%d', t.date) AS INTEGER) as day_num,
            date(t.date) as full_date,
            COUNT(t.id) as trx_count,
            COALESCE(SUM(t.total_amount), 0) as daily_omzet,
            COALESCE(SUM(t.total_cost), 0) as daily_cost,
            COALESCE(SUM(t.total_amount - t.total_cost), 0) as daily_profit
        FROM transactions t
        WHERE date(t.date) BETWEEN ? AND ?
    '''
    m_daily_params = [month_start_date, month_end_date]
    if not is_admin:
        m_daily_query += " AND t.cashier_id = ?"
        m_daily_params.append(session.get('user_id'))
    m_daily_query += " GROUP BY full_date ORDER BY day_num ASC"
    daily_records = conn.execute(m_daily_query, m_daily_params).fetchall()

    daily_map = {r['day_num']: dict(r) for r in daily_records}
    chart_days = [f"{d}" for d in range(1, days_in_month + 1)]
    chart_monthly_omzet = [daily_map.get(d, {}).get('daily_omzet', 0) if d in daily_map else 0 for d in range(1, days_in_month + 1)]
    chart_monthly_profit = [daily_map.get(d, {}).get('daily_profit', 0) if d in daily_map else 0 for d in range(1, days_in_month + 1)]

    # 2. DATE RANGE & TRANSACTION HISTORY FILTER
    first_day_month = today.replace(day=1).strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')

    start_date = request.args.get('start_date', first_day_month)
    end_date = request.args.get('end_date', today_str)
    search_inv = request.args.get('q', '').strip()

    query_trx = '''
        SELECT t.*, u.full_name as cashier_name,
               (SELECT COUNT(*) FROM transaction_items WHERE transaction_id = t.id) as total_items
        FROM transactions t
        LEFT JOIN users u ON t.cashier_id = u.id
        WHERE date(t.date) BETWEEN ? AND ?
    '''
    params = [start_date, end_date]

    if not is_admin:
        query_trx += " AND t.cashier_id = ?"
        params.append(session.get('user_id'))

    if search_inv:
        query_trx += " AND (t.invoice_number LIKE ? OR t.customer_name LIKE ?)"
        params.extend([f"%{search_inv}%", f"%{search_inv}%"])

    query_trx += " ORDER BY t.date DESC"
    transactions = conn.execute(query_trx, params).fetchall()

    summary_query = '''
        SELECT 
            COUNT(t.id) as trx_count,
            COALESCE(SUM(t.total_amount), 0) as total_omzet,
            COALESCE(SUM(t.total_cost), 0) as total_cost,
            COALESCE(SUM(t.total_amount - t.total_cost), 0) as total_profit
        FROM transactions t
        WHERE date(t.date) BETWEEN ? AND ?
    '''
    summary_params = [start_date, end_date]
    if not is_admin:
        summary_query += " AND t.cashier_id = ?"
        summary_params.append(session.get('user_id'))

    summary = conn.execute(summary_query, summary_params).fetchone()

    top_selling = []
    if is_admin:
        top_selling = conn.execute('''
            SELECT 
                ti.product_name,
                ti.sku,
                SUM(ti.qty) as total_qty,
                SUM(ti.subtotal) as total_sales,
                SUM(ti.profit) as total_profit
            FROM transaction_items ti
            JOIN transactions t ON ti.transaction_id = t.id
            WHERE date(t.date) BETWEEN ? AND ?
            GROUP BY ti.product_name, ti.sku
            ORDER BY total_qty DESC
            LIMIT 10
        ''', (start_date, end_date)).fetchall()

    conn.close()

    return render_template(
        'reports.html',
        active_tab=active_tab,
        # Monthly Data
        selected_month=selected_month,
        selected_year=selected_year,
        selected_month_name=selected_month_name,
        available_months=INDONESIAN_MONTHS,
        available_years=available_years,
        monthly_summary=monthly_summary,
        monthly_top_selling=monthly_top_selling,
        daily_records=daily_records,
        chart_days=json.dumps(chart_days),
        chart_monthly_omzet=json.dumps(chart_monthly_omzet),
        chart_monthly_profit=json.dumps(chart_monthly_profit),
        # Range / History Data
        transactions=transactions,
        summary=summary,
        top_selling=top_selling,
        start_date=start_date,
        end_date=end_date,
        search_inv=search_inv,
        is_admin=is_admin
    )

# ----------------- EXCEL EXPORT ENDPOINT -----------------
@app.route('/reports/export-excel')
@login_required
def export_excel():
    is_admin = session.get('role') == 'admin'
    export_type = request.args.get('type', 'monthly')
    today = datetime.now()
    conn = get_db()

    if export_type == 'monthly':
        try:
            month = int(request.args.get('month', today.month))
        except (ValueError, TypeError):
            month = today.month

        try:
            year = int(request.args.get('year', today.year))
        except (ValueError, TypeError):
            year = today.year

        days_in_month = calendar.monthrange(year, month)[1]
        start_date = f"{year:04d}-{month:02d}-01"
        end_date = f"{year:04d}-{month:02d}-{days_in_month:02d}"
        month_name = dict(INDONESIAN_MONTHS).get(month, f"Bulan_{month}")
        period_title = f"{month_name} {year}"
        filename = f"Laporan_Penjualan_Bulanan_{month_name}_{year}.xlsx"
    else:
        first_day_month = today.replace(day=1).strftime('%Y-%m-%d')
        start_date = request.args.get('start_date', first_day_month)
        end_date = request.args.get('end_date', today.strftime('%Y-%m-%d'))
        period_title = f"{start_date} s/d {end_date}"
        filename = f"Laporan_Transaksi_{start_date}_sd_{end_date}.xlsx"

    search_q = request.args.get('q', '').strip()

    # Query transaction line items for complete detail
    query = '''
        SELECT 
            t.invoice_number,
            t.date,
            t.payment_method,
            t.customer_name,
            u.full_name as cashier_name,
            ti.product_name,
            ti.sku,
            ti.buy_price,
            ti.sell_price,
            ti.qty,
            ti.subtotal,
            ti.profit
        FROM transactions t
        LEFT JOIN users u ON t.cashier_id = u.id
        JOIN transaction_items ti ON ti.transaction_id = t.id
        WHERE date(t.date) BETWEEN ? AND ?
    '''
    params = [start_date, end_date]

    if not is_admin:
        query += " AND t.cashier_id = ?"
        params.append(session.get('user_id'))

    if search_q:
        query += " AND (t.invoice_number LIKE ? OR t.customer_name LIKE ?)"
        params.extend([f"%{search_q}%", f"%{search_q}%"])

    query += " ORDER BY t.date DESC, t.id DESC, ti.id ASC"
    items = conn.execute(query, params).fetchall()

    # Query Top Selling Items for Sheet 2
    top_query = '''
        SELECT 
            ti.product_name,
            ti.sku,
            SUM(ti.qty) as total_qty,
            SUM(ti.subtotal) as total_sales,
            SUM(ti.profit) as total_profit
        FROM transaction_items ti
        JOIN transactions t ON ti.transaction_id = t.id
        WHERE date(t.date) BETWEEN ? AND ?
    '''
    top_params = [start_date, end_date]
    if not is_admin:
        top_query += " AND t.cashier_id = ?"
        top_params.append(session.get('user_id'))
    top_query += " GROUP BY ti.product_id, ti.product_name, ti.sku ORDER BY total_qty DESC LIMIT 20"
    top_products = conn.execute(top_query, top_params).fetchall()

    store_name = get_setting('store_name', 'Toko Berkah Retail')
    store_address = get_setting('store_address', 'Jl. Merdeka No. 45')
    store_phone = get_setting('store_phone', '0812-3456-7890')
    conn.close()

    # Create Workbook
    wb = openpyxl.Workbook()
    
    # ---------------- SHEET 1: DETAIL TRANSAKSI ----------------
    ws1 = wb.active
    ws1.title = "Rekap Transaksi"

    # Define Styles
    header_fill = PatternFill(start_color="16A34A", end_color="16A34A", fill_type="solid") # Emerald Green
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid") # Light Slate
    total_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid") # Slate 200

    font_title = Font(name="Calibri", size=15, bold=True, color="166534")
    font_subtitle = Font(name="Calibri", size=11, bold=True, color="334155")
    font_meta = Font(name="Calibri", size=9, italic=True, color="64748B")
    font_header = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    font_bold = Font(name="Calibri", size=10, bold=True, color="0F172A")
    font_normal = Font(name="Calibri", size=10, color="1E293B")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )
    total_border = Border(
        top=Side(style='thin', color='000000'),
        bottom=Side(style='double', color='000000'),
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1')
    )

    # Title Banner
    ws1["A1"] = store_name.upper()
    ws1["A1"].font = font_title
    ws1["A2"] = f"LAPORAN REKAPITULASI PENJUALAN RETAIL - PERIODE: {period_title.upper()}"
    ws1["A2"].font = font_subtitle
    ws1["A3"] = f"{store_address} | Telp: {store_phone} | Dicetak: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | Operator: {session.get('full_name')}"
    ws1["A3"].font = font_meta

    # Column Headers
    headers = [
        "No", "Tanggal & Waktu", "No. Faktur", "Kasir", "Pelanggan",
        "SKU / Barcode", "Nama Produk", "Harga Satuan (Rp)", "Qty",
        "Total Harga (Rp)"
    ]
    if is_admin:
        headers.append("Keuntungan (Rp)")
    headers.append("Metode Pembayaran")

    start_row = 5
    for col_idx, h_text in enumerate(headers, 1):
        cell = ws1.cell(row=start_row, column=col_idx, value=h_text)
        cell.font = font_header
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    ws1.row_dimensions[start_row].height = 28

    # Populate Data Rows
    curr_row = start_row + 1
    total_qty = 0
    total_omzet = 0
    total_profit = 0

    for idx, row in enumerate(items, 1):
        dt_val = str(row['date'])
        try:
            dt_obj = datetime.fromisoformat(dt_val.replace('Z', ''))
            dt_str = dt_obj.strftime('%d/%m/%Y %H:%M')
        except Exception:
            dt_str = dt_val

        ws1.cell(row=curr_row, column=1, value=idx).alignment = Alignment(horizontal="center")
        ws1.cell(row=curr_row, column=2, value=dt_str).alignment = Alignment(horizontal="center")
        ws1.cell(row=curr_row, column=3, value=row['invoice_number']).alignment = Alignment(horizontal="center")
        ws1.cell(row=curr_row, column=4, value=row['cashier_name'] or '-')
        ws1.cell(row=curr_row, column=5, value=row['customer_name'] or 'Pelanggan Umum')
        ws1.cell(row=curr_row, column=6, value=row['sku']).alignment = Alignment(horizontal="center")
        ws1.cell(row=curr_row, column=7, value=row['product_name'])
        
        c_price = ws1.cell(row=curr_row, column=8, value=row['sell_price'])
        c_price.number_format = '#,##0'
        c_price.alignment = Alignment(horizontal="right")
        
        c_qty = ws1.cell(row=curr_row, column=9, value=row['qty'])
        c_qty.number_format = '#,##0'
        c_qty.alignment = Alignment(horizontal="center")
        
        c_sub = ws1.cell(row=curr_row, column=10, value=row['subtotal'])
        c_sub.number_format = '#,##0'
        c_sub.alignment = Alignment(horizontal="right")

        next_col = 11
        if is_admin:
            c_prof = ws1.cell(row=curr_row, column=next_col, value=row['profit'])
            c_prof.number_format = '#,##0'
            c_prof.alignment = Alignment(horizontal="right")
            total_profit += row['profit']
            next_col += 1

        ws1.cell(row=curr_row, column=next_col, value=row['payment_method']).alignment = Alignment(horizontal="center")

        total_qty += row['qty']
        total_omzet += row['subtotal']

        for c in range(1, len(headers) + 1):
            cell = ws1.cell(row=curr_row, column=c)
            cell.font = font_normal
            cell.border = thin_border
            if idx % 2 == 0:
                cell.fill = zebra_fill

        curr_row += 1

    # Totals Row
    for c in range(1, len(headers) + 1):
        cell = ws1.cell(row=curr_row, column=c, value="")
        cell.border = total_border
        cell.fill = total_fill

    total_lbl = ws1.cell(row=curr_row, column=7, value="TOTAL KESELURUHAN")
    total_lbl.font = font_bold
    total_lbl.alignment = Alignment(horizontal="right")

    t_qty = ws1.cell(row=curr_row, column=9, value=total_qty)
    t_qty.font = font_bold
    t_qty.number_format = '#,##0'
    t_qty.alignment = Alignment(horizontal="center")

    t_omzet = ws1.cell(row=curr_row, column=10, value=total_omzet)
    t_omzet.font = font_bold
    t_omzet.number_format = '#,##0'
    t_omzet.alignment = Alignment(horizontal="right")

    next_col = 11
    if is_admin:
        t_prof = ws1.cell(row=curr_row, column=next_col, value=total_profit)
        t_prof.font = font_bold
        t_prof.number_format = '#,##0'
        t_prof.alignment = Alignment(horizontal="right")

    # Auto-adjust column widths for Sheet 1
    for col in ws1.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or '')
            if cell.row < 4:
                continue
            max_len = max(max_len, len(val_str))
        ws1.column_dimensions[col_letter].width = max(max_len + 3, 11)

    # ---------------- SHEET 2: TOP SELLING ITEMS ----------------
    ws2 = wb.create_sheet(title="Produk Terlaris")
    ws2["A1"] = store_name.upper()
    ws2["A1"].font = font_title
    ws2["A2"] = f"REKAP PRODUK TERLARIS - PERIODE: {period_title.upper()}"
    ws2["A2"].font = font_subtitle

    top_headers = ["Peringkat", "Nama Produk", "SKU / Barcode", "Total Terjual (Unit)", "Total Penjualan (Rp)"]
    if is_admin:
        top_headers.append("Total Keuntungan (Rp)")

    for c_idx, h in enumerate(top_headers, 1):
        cell = ws2.cell(row=4, column=c_idx, value=h)
        cell.font = font_header
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
    ws2.row_dimensions[4].height = 26

    r_top = 5
    for rank, p in enumerate(top_products, 1):
        ws2.cell(row=r_top, column=1, value=rank).alignment = Alignment(horizontal="center")
        ws2.cell(row=r_top, column=2, value=p['product_name'])
        ws2.cell(row=r_top, column=3, value=p['sku']).alignment = Alignment(horizontal="center")
        
        cq = ws2.cell(row=r_top, column=4, value=p['total_qty'])
        cq.number_format = '#,##0'
        cq.alignment = Alignment(horizontal="center")

        cs = ws2.cell(row=r_top, column=5, value=p['total_sales'])
        cs.number_format = '#,##0'
        cs.alignment = Alignment(horizontal="right")

        if is_admin:
            cp = ws2.cell(row=r_top, column=6, value=p['total_profit'])
            cp.number_format = '#,##0'
            cp.alignment = Alignment(horizontal="right")

        for c in range(1, len(top_headers) + 1):
            cell = ws2.cell(row=r_top, column=c)
            cell.font = font_normal
            cell.border = thin_border
            if rank % 2 == 0:
                cell.fill = zebra_fill
        r_top += 1

    for col in ws2.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or '')
            if cell.row < 3:
                continue
            max_len = max(max_len, len(val_str))
        ws2.column_dimensions[col_letter].width = max(max_len + 4, 12)

    # Stream out workbook as download
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ----------------- STOK OPNAME (STOCK TAKE & LOSS ANALYSIS) -----------------
@app.route('/stock-opname')
@admin_required
def stock_opname():
    conn = get_db()
    
    # 1. Active products for dropdown / scanner selector
    products_rows = conn.execute('''
        SELECT p.id, p.name, p.sku, p.buy_price, p.sell_price, p.stock, c.name as category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_active = 1
        ORDER BY p.name ASC
    ''').fetchall()
    products = [dict(r) for r in products_rows]

    # 2. Filter parameters for opname history
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip() # 'KURANG', 'LEBIH', 'SESUAI'
    reason_filter = request.args.get('reason', '').strip() # 'HILANG', 'RUSAK', 'KADALUWARSA', etc.

    history_query = '''
        SELECT so.*, u.full_name as user_name
        FROM stock_opnames so
        LEFT JOIN users u ON so.user_id = u.id
        WHERE 1=1
    '''
    params = []

    if q:
        history_query += " AND (so.product_name LIKE ? OR so.sku LIKE ? OR so.opname_code LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    if status_filter:
        history_query += " AND so.status = ?"
        params.append(status_filter)

    if reason_filter:
        history_query += " AND so.reason = ?"
        params.append(reason_filter)

    history_query += " ORDER BY so.date DESC, so.id DESC"
    opname_history = conn.execute(history_query, params).fetchall()

    # 3. Summary KPIs for Stok Opname
    kpi = conn.execute('''
        SELECT 
            COUNT(id) as total_count,
            COALESCE(SUM(loss_amount), 0) as total_loss,
            COALESCE(SUM(CASE WHEN difference < 0 THEN abs(difference) ELSE 0 END), 0) as total_lost_units,
            COALESCE(SUM(CASE WHEN difference = 0 THEN 1 ELSE 0 END), 0) as total_accurate_items,
            COALESCE(SUM(CASE WHEN difference > 0 THEN difference ELSE 0 END), 0) as total_surplus_units
        FROM stock_opnames
    ''').fetchone()

    conn.close()

    return render_template(
        'stock_opname.html',
        products=products,
        opname_history=opname_history,
        kpi=kpi,
        q=q,
        status_filter=status_filter,
        reason_filter=reason_filter
    )

@app.route('/api/stock-opname', methods=['POST'])
@admin_required
def api_save_stock_opname():
    data = request.get_json() or {}
    product_id = data.get('product_id')
    try:
        physical_stock = int(data.get('physical_stock'))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Stok fisik harus berupa angka bulat!'}), 400

    reason = data.get('reason', 'LAINNYA').strip().upper()
    notes = data.get('notes', '').strip()

    if not product_id or physical_stock < 0:
        return jsonify({'success': False, 'message': 'Produk dan stok fisik (≥ 0) wajib diisi!'}), 400

    conn = get_db()
    cursor = conn.cursor()

    prod = cursor.execute("SELECT * FROM products WHERE id = ? AND is_active = 1", (product_id,)).fetchone()
    if not prod:
        conn.close()
        return jsonify({'success': False, 'message': 'Produk tidak ditemukan atau non-aktif!'}), 404

    system_stock = prod['stock']
    difference = physical_stock - system_stock

    if difference < 0:
        status = 'KURANG'
        loss_amount = abs(difference) * prod['buy_price']
        if reason == 'SESUAI':
            reason = 'HILANG'
    elif difference > 0:
        status = 'LEBIH'
        loss_amount = 0
        if reason == 'SESUAI':
            reason = 'KOREKSI_HITUNG'
    else:
        status = 'SESUAI'
        loss_amount = 0
        reason = 'SESUAI'

    opname_code = generate_opname_code()
    user_id = session.get('user_id')

    try:
        cursor.execute("BEGIN TRANSACTION")

        # 1. Insert into stock_opnames
        cursor.execute('''
            INSERT INTO stock_opnames (
                opname_code, product_id, product_name, sku, buy_price, sell_price,
                system_stock, physical_stock, difference, status, reason, loss_amount,
                notes, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            opname_code, prod['id'], prod['name'], prod['sku'], prod['buy_price'], prod['sell_price'],
            system_stock, physical_stock, difference, status, reason, loss_amount,
            notes, user_id
        ))

        # 2. Update product's current stock to physical_stock
        cursor.execute('''
            UPDATE products 
            SET stock = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (physical_stock, prod['id']))

        # 3. Record in stock_movements audit trail
        diff_str = f"+{difference}" if difference > 0 else f"{difference}"
        movement_note = f"[STOK OPNAME] {opname_code} - Selisih: {diff_str} Unit ({reason}) - {notes}"
        cursor.execute('''
            INSERT INTO stock_movements (
                product_id, type, qty, previous_stock, current_stock, note, user_id
            ) VALUES (?, 'ADJUSTMENT', ?, ?, ?, ?, ?)
        ''', (
            prod['id'], abs(difference), system_stock, physical_stock, movement_note, user_id
        ))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f"Stok opname berhasil disimpan! Stok '{prod['name']}' disesuaikan dari {system_stock} menjadi {physical_stock} unit.",
            'opname_code': opname_code,
            'difference': difference,
            'status': status,
            'loss_amount': loss_amount,
            'new_stock': physical_stock
        })

    except Exception as e:
        cursor.execute("ROLLBACK")
        conn.close()
        return jsonify({'success': False, 'message': f"Terjadi kesalahan saat menyimpan opname: {str(e)}"}), 500

@app.route('/stock-opname/export-excel')
@admin_required
def export_stock_opname_excel():
    conn = get_db()
    
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    reason_filter = request.args.get('reason', '').strip()

    query = '''
        SELECT so.*, u.full_name as user_name
        FROM stock_opnames so
        LEFT JOIN users u ON so.user_id = u.id
        WHERE 1=1
    '''
    params = []

    if q:
        query += " AND (so.product_name LIKE ? OR so.sku LIKE ? OR so.opname_code LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    if status_filter:
        query += " AND so.status = ?"
        params.append(status_filter)

    if reason_filter:
        query += " AND so.reason = ?"
        params.append(reason_filter)

    query += " ORDER BY so.date DESC, so.id DESC"
    records = conn.execute(query, params).fetchall()

    store_name = get_setting('store_name', 'Toko Berkah Retail')
    store_address = get_setting('store_address', 'Jl. Merdeka No. 45, Jakarta Pusat')
    store_phone = get_setting('store_phone', '0812-3456-7890')
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rekap Stok Opname"

    header_fill = PatternFill(start_color="16A34A", end_color="16A34A", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    total_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")

    font_title = Font(name="Calibri", size=15, bold=True, color="166534")
    font_subtitle = Font(name="Calibri", size=11, bold=True, color="334155")
    font_meta = Font(name="Calibri", size=9, italic=True, color="64748B")
    font_header = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    font_bold = Font(name="Calibri", size=10, bold=True, color="0F172A")
    font_normal = Font(name="Calibri", size=10, color="1E293B")
    font_loss = Font(name="Calibri", size=10, bold=True, color="DC2626")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )
    total_border = Border(
        top=Side(style='thin', color='000000'),
        bottom=Side(style='double', color='000000'),
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1')
    )

    # Title Banner
    ws["A1"] = store_name.upper()
    ws["A1"].font = font_title
    ws["A2"] = "LAPORAN REKAPITULASI STOK OPNAME, SELISIH & NILAI KERUGIAN BARANG"
    ws["A2"].font = font_subtitle
    ws["A3"] = f"{store_address} | Telp: {store_phone} | Dicetak: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | Operator: {session.get('full_name')}"
    ws["A3"].font = font_meta

    headers = [
        "No", "No. Opname", "Tanggal & Waktu", "SKU / Barcode", "Nama Produk",
        "Harga Modal (Rp)", "Stok Sistem", "Stok Fisik", "Selisih Unit",
        "Status", "Alasan / Penyebab", "Nilai Kerugian (Rp)", "Keterangan / Catatan", "Petugas"
    ]

    start_row = 5
    for col_idx, h_text in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=col_idx, value=h_text)
        cell.font = font_header
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    ws.row_dimensions[start_row].height = 28

    curr_row = start_row + 1
    total_diff_units = 0
    total_loss_rp = 0

    for idx, r in enumerate(records, 1):
        dt_val = str(r['date'])
        try:
            dt_obj = datetime.fromisoformat(dt_val.replace('Z', ''))
            dt_str = dt_obj.strftime('%d/%m/%Y %H:%M')
        except Exception:
            dt_str = dt_val

        ws.cell(row=curr_row, column=1, value=idx).alignment = Alignment(horizontal="center")
        ws.cell(row=curr_row, column=2, value=r['opname_code']).alignment = Alignment(horizontal="center")
        ws.cell(row=curr_row, column=3, value=dt_str).alignment = Alignment(horizontal="center")
        ws.cell(row=curr_row, column=4, value=r['sku']).alignment = Alignment(horizontal="center")
        ws.cell(row=curr_row, column=5, value=r['product_name'])

        c_buy = ws.cell(row=curr_row, column=6, value=r['buy_price'])
        c_buy.number_format = '#,##0'
        c_buy.alignment = Alignment(horizontal="right")

        c_sys = ws.cell(row=curr_row, column=7, value=r['system_stock'])
        c_sys.number_format = '#,##0'
        c_sys.alignment = Alignment(horizontal="center")

        c_phy = ws.cell(row=curr_row, column=8, value=r['physical_stock'])
        c_phy.number_format = '#,##0'
        c_phy.alignment = Alignment(horizontal="center")

        diff = r['difference']
        c_diff = ws.cell(row=curr_row, column=9, value=diff)
        c_diff.number_format = '+#,##0;-#,##0;0'
        c_diff.alignment = Alignment(horizontal="center")

        ws.cell(row=curr_row, column=10, value=r['status']).alignment = Alignment(horizontal="center")
        ws.cell(row=curr_row, column=11, value=r['reason']).alignment = Alignment(horizontal="center")

        loss = r['loss_amount']
        c_loss = ws.cell(row=curr_row, column=12, value=loss)
        c_loss.number_format = '#,##0'
        c_loss.alignment = Alignment(horizontal="right")
        if loss > 0:
            c_loss.font = font_loss

        ws.cell(row=curr_row, column=13, value=r['notes'] or '-')
        ws.cell(row=curr_row, column=14, value=r['user_name'] or 'Admin')

        total_diff_units += diff
        total_loss_rp += loss

        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=curr_row, column=c)
            cell.border = thin_border
            if idx % 2 == 0:
                cell.fill = zebra_fill
            if c != 12 or loss == 0:
                cell.font = font_normal

        curr_row += 1

    # Totals Row
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=curr_row, column=c, value="")
        cell.border = total_border
        cell.fill = total_fill

    total_lbl = ws.cell(row=curr_row, column=5, value="TOTAL KESELURUHAN")
    total_lbl.font = font_bold
    total_lbl.alignment = Alignment(horizontal="right")

    t_diff = ws.cell(row=curr_row, column=9, value=total_diff_units)
    t_diff.font = font_bold
    t_diff.number_format = '+#,##0;-#,##0;0'
    t_diff.alignment = Alignment(horizontal="center")

    t_loss = ws.cell(row=curr_row, column=12, value=total_loss_rp)
    t_loss.font = font_bold
    t_loss.number_format = '#,##0'
    t_loss.alignment = Alignment(horizontal="right")

    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or '')
            if cell.row < 4:
                continue
            max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"Laporan_Stok_Opname_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ----------------- SETTINGS & USER MANAGEMENT -----------------
@app.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    conn = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'store_info':
            set_setting('store_name', request.form.get('store_name', '').strip())
            set_setting('store_address', request.form.get('store_address', '').strip())
            set_setting('store_phone', request.form.get('store_phone', '').strip())
            set_setting('receipt_footer', request.form.get('receipt_footer', '').strip())
            set_setting('receipt_paper_size', request.form.get('receipt_paper_size', '58mm'))
            flash('Pengaturan informasi toko & struk berhasil disimpan!', 'success')
            return redirect(url_for('settings'))

        elif action == 'add_user':
            username = request.form.get('username', '').strip()
            full_name = request.form.get('full_name', '').strip()
            role = request.form.get('role', 'cashier')
            password = request.form.get('password', '').strip()

            if not username or not password or not full_name:
                flash('Semua kolom pengguna wajib diisi!', 'danger')
            else:
                existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
                if existing:
                    flash(f"Username '{username}' sudah digunakan!", 'danger')
                else:
                    conn.execute('''
                        INSERT INTO users (username, password_hash, full_name, role)
                        VALUES (?, ?, ?, ?)
                    ''', (username, generate_password_hash(password), full_name, role))
                    conn.commit()
                    flash(f"Pengguna '{full_name}' ({role}) berhasil ditambahkan!", 'success')
            return redirect(url_for('settings'))

        elif action == 'delete_user':
            user_id = request.form.get('user_id')
            if str(user_id) == str(session.get('user_id')):
                flash('Anda tidak dapat menghapus akun Anda sendiri saat sedang login!', 'warning')
            else:
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
                conn.commit()
                flash('Pengguna berhasil dihapus!', 'info')
            return redirect(url_for('settings'))

    users = conn.execute("SELECT * FROM users ORDER BY role ASC, full_name ASC").fetchall()
    categories = conn.execute("SELECT * FROM categories ORDER BY name ASC").fetchall()
    conn.close()

    return render_template(
        'settings.html',
        users=users,
        categories=categories,
        store_name=get_setting('store_name'),
        store_address=get_setting('store_address'),
        store_phone=get_setting('store_phone'),
        receipt_footer=get_setting('receipt_footer'),
        receipt_paper_size=get_setting('receipt_paper_size')
    )

@app.route('/api/categories', methods=['POST'])
@admin_required
def api_add_category():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Nama kategori tidak boleh kosong'}), 400

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        cat_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'category': {'id': cat_id, 'name': name}})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'message': f"Kategori '{name}' sudah ada."}), 400

if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=5000, debug=True)
