@echo off
title Aplikasi POS Kasir Retail & Inventori Stok
echo ========================================================
echo    APLIKASI POINT OF SALE (POS) & INVENTORI RETAIl
echo ========================================================
echo.
echo Memeriksa ketersediaan database...
if not exist "pos_retail.db" (
    echo Menginisialisasi basis data dan data produk awal...
    python seed_data.py
)
echo.
echo Menjalankan server aplikasi di http://127.0.0.1:5000 ...
echo Tekan CTRL+C untuk menghentikan server.
echo.
start http://127.0.0.1:5000
python app.py
pause
