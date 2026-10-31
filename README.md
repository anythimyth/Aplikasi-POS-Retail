# Aplikasi POS (Point of Sale) & Manajemen Inventori Retail Terintegrasi

Aplikasi web modern, cepat, dan ringan yang dirancang khusus untuk operasional kasir retail, manajemen inventori stok barang, rekapitulasi laporan penjualan bulanan, dan ekspor laporan ke Excel. Dibangun menggunakan arsitektur **Python Flask**, **SQLite**, dan **Tailwind CSS** yang siap dijalankan secara lokal tanpa perlu instalasi basis data rumit ataupun node_modules build-step.

---

## 🌟 Fitur Utama & Modul Sistem

### 1. Modul Inventoris & Manajemen Stok
- **Master Data Produk**: Pencatatan Nama Produk, Kategori, Barcode/SKU unik, Harga Beli (Modal Pokok), Harga Jual, Stok Fisik, dan Batas Stok Minimum.
- **Peringatan Stok Minimum Visual**: Label warna dinamis (*Aman [Hijau]*, *Menipis [Kuning/Oranye]*, *Habis [Merah]*), disertai banner peringatan di dashboard dan tab filter khusus produk yang harus segera dipesan ke supplier.
- **Sistem Penyesuaian Stok (Audit Trail)**: 
  - Pencatatan otomatis barang masuk (*Restock / Supplier*).
  - Pencatatan barang keluar (*Rusak / Kadaluarsa*).
  - Penyesuaian stok opname (*Koreksi Stok Fisik Riil*).
  - Kartu stok (*Stock Movements*) untuk melacak mutasi stok lengkap per produk.

### 2. Modul Kasir (Point of Sale - POS)
- **Fast Cashier Terminal**:
  - Kolom pencarian otomatis dengan dukungan penuh **Hardware Barcode Scanner** (deteksi tombol Enter instan).
  - Audio feedback synthesizer (bunyi *beep* menyenangkan saat scan sukses dan suara peringatan saat stok habis / barcode tidak ditemukan).
  - Pintasan keyboard kasir (*Hotkeys*):
    - `F1`: Fokus ke kolom scan barcode/pencarian produk.
    - `F2`: Fokus ke kalkulator pembayaran tunai.
    - `F4`: Reset / kosongkan keranjang belanja.
    - `Enter`: Tambah produk / selesaikan pembayaran.
- **Kalkulator Kasir Cepat**: Tombol nominal uang pas dan pecahan cepat (Rp 10rb, 20rb, 50rb, 100rb), serta kalkulasi kembalian otomatis secara realtime.
- **Cetak Struk Thermal**: Desain struk belanja siap cetak printer thermal ukuran **58mm** dan **80mm** via format CSS `@media print`.

### 3. Modul Laporan Penjualan Bulanan & Analisis Bisnis (Fitur Baru)
- **Filter Fleksibel Bulan & Tahun**: Pilih bulan (Januari - Desember) dan tahun untuk menampilkan rekapitulasi spesifik.
- **Ringkasan KPI Bulanan**:
  - Total Omzet Penjualan Bulanan.
  - Total Modal Pokok / HPP (*Cost of Goods Sold*).
  - Keuntungan Kotor / Gross Profit (Omzet - Modal) & Margin Laba (%).
  - Total Frekuensi Transaksi & Rata-rata per Nota (*Average Order Value*).
- **Grafik Tren Penjualan Harian**: Visualisasi interaktif Chart.js bar chart per tanggal (1 sd 31) pada bulan terpilih.
- **Rekapitulasi Harian**: Tabel perincian omzet, modal, dan laba untuk setiap tanggal aktif dalam bulan tersebut.
- **Produk Terlaris Bulanan (*Top 10 Selling Items*)**: Peringkat 10 produk paling laku berdasarkan volume unit dan pendapatan kotor.

### 4. Fitur Ekspor Data ke Excel (.xlsx) (Fitur Baru)
- **Unduh Laporan Otomatis**: Tombol *"Ekspor ke Excel (.xlsx)"* di header laporan bulanan dan riwayat transaksi.
- **Struktur Workbook Profesional**:
  - **Sheet 1 (`Rekap Transaksi`)**: Rincian setiap item transaksi (No, Tanggal & Jam, No. Faktur, Kasir, Pelanggan, Barcode, Nama Produk, Harga Satuan, Qty, Total Harga, Keuntungan Kotor, Metode Pembayaran) lengkap dengan baris total penjumlahan.
  - **Sheet 2 (`Produk Terlaris`)**: Peringkat produk paling laku pada periode tersebut.
- **Format Rapi & Standar**: Warna header hijau emerald elegan (`#16A34A`), format angka Rupiah (`#,##0`), zebra striping selang-seling, dan penyesuaian lebar kolom otomatis (*auto-fit width*).

### 5. Keamanan & Hak Akses Pengguna (RBAC)
- **Admin / Pemilik Toko**: Akses penuh ke seluruh menu (Dashboard Keuntungan, Inventori, Restock, Pengaturan Toko & Pengguna, Laporan Lengkap & Ekspor Excel dengan Laba).
- **Kasir**: Antarmuka kasir cepat (POS) dan riwayat transaksi kasir tanpa menampilkan informasi harga modal atau margin laba toko.

---

## 🔑 Akun Default (Login Demo)

| Peran (Role) | Username | Password | Deskripsi Akses |
| :--- | :--- | :--- | :--- |
| **Admin / Pemilik** | `admin` | `admin123` | Akses penuh (Dashboard Laba, Stok, Restock, Pengguna, Laporan) |
| **Kasir** | `kasir` | `kasir123` | Terminal Kasir POS & Nota Transaksi Kasir |

---

## 🚀 Panduan Menjalankan Aplikasi di Lokal

### Langkah 1: Buka Terminal / PowerShell
```bash
cd c:\Aplikasi-POS-Retail
```

### Langkah 2: Instalasi Kebutuhan Dependensi
```bash
pip install -r requirements.txt
```
*Paket yang digunakan: Flask, Werkzeug, openpyxl (untuk ekspor Excel).*

### Langkah 3: Jalankan Server Aplikasi
```bash
python app.py
```
Atau klik dua kali file **`run_app.bat`** di Windows Explorer.

Buka browser di alamat:
👉 **`http://127.0.0.1:5000`**

---

## 📂 Struktur Direktori Proyek

```
c:\Aplikasi-POS-Retail\
├── app.py                     # Server Flask utama, API, Rute Laporan Bulanan & Ekspor Excel
├── database.py                # Konfigurasi SQLite, Helper queries, & Setting toko
├── seed_data.py               # Data awal: User, Kategori, Produk, Barcode, Transaksi
├── requirements.txt           # Ketergantungan minimal (Flask, Werkzeug, openpyxl)
├── run_app.bat                # Script peluncur 1-klik di Windows
├── static/
│   ├── css/
│   │   └── custom.css         # Styling khusus cetak struk thermal 58mm/80mm
│   └── js/
│       ├── app.js             # Notifikasi toast, format rupiah, synthesizer audio
│       └── pos.js             # Logika kasir, scanning barcode, kalkulasi & keranjang
└── templates/
    ├── base.html              # Layout utama, sidebar responsive, topbar, alert
    ├── login.html             # Halaman login dengan 1-klik akun demo
    ├── dashboard.html         # Dashboard KPI, grafik tren omzet/laba, stok kritis
    ├── inventory.html         # Manajemen produk, modal restock, kartu stok audit
    ├── pos.html               # Terminal kasir, barcode scanner, ringkasan transaksi
    ├── reports.html           # Laporan Bulanan, Grafik Harian, Ekspor Excel & Riwayat Nota
    └── settings.html          # Pengaturan profil toko, struk, dan manajemen staf kasir
```
"# Aplikasi-POS-Retail" 
