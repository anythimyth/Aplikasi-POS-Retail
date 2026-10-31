import os
import requests
import openpyxl
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ARTIFACT_DIR = r"C:\Users\Anonim\.gemini\antigravity\brain\7835f103-6a62-4fa6-9445-18e3a5fa8974"

def test_excel_direct():
    print("[TEST 1] Testing Excel Export via Session...")
    s = requests.Session()
    # Login
    login_res = s.post("http://127.0.0.1:5000/login", data={"username": "admin", "password": "admin123"})
    assert login_res.status_code == 200 or login_res.history, "Login failed"

    # Export Monthly Excel
    excel_url = "http://127.0.0.1:5000/reports/export-excel?type=monthly&month=10&year=2026"
    res = s.get(excel_url)
    assert res.status_code == 200, f"Export failed with status {res.status_code}"
    assert "spreadsheetml.sheet" in res.headers.get("Content-Type", ""), "Not an Excel file"
    
    excel_path = os.path.join(ARTIFACT_DIR, "Laporan_Penjualan_Bulanan_Oktober_2026.xlsx")
    with open(excel_path, "wb") as f:
        f.write(res.content)
    print(f"Saved Excel file: {excel_path} (Size: {len(res.content)} bytes)")

    # Inspect Excel content with openpyxl
    wb = openpyxl.load_workbook(excel_path)
    sheet_names = wb.sheetnames
    print("Workbook Sheets:", sheet_names)
    assert "Rekap Transaksi" in sheet_names, "Sheet 1 missing"
    assert "Produk Terlaris" in sheet_names, "Sheet 2 missing"

    ws1 = wb["Rekap Transaksi"]
    print("Sheet 1 Title:", ws1["A1"].value)
    print("Sheet 1 Period:", ws1["A2"].value)
    print("Sheet 1 Total Rows:", ws1.max_row)

    ws2 = wb["Produk Terlaris"]
    print("Sheet 2 Title:", ws2["A2"].value)
    print("Sheet 2 Max Rows:", ws2.max_row)

    print("Excel direct test PASSED successfully!\n")

def test_browser_ui():
    print("[TEST 2] Testing Browser UI with Headless Chrome...")
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1366,850")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=chrome_options)
    try:
        # Login as Admin
        driver.get("http://127.0.0.1:5000/login")
        driver.find_element(By.XPATH, "//button[contains(., 'Admin Toko')]").click()
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        driver.implicitly_wait(5)

        # Open Reports
        driver.get("http://127.0.0.1:5000/reports?tab=monthly&month=10&year=2026")
        import time
        time.sleep(2)

        # Screenshot of Monthly Report
        shot_monthly = os.path.join(ARTIFACT_DIR, "08_laporan_bulanan.png")
        driver.save_screenshot(shot_monthly)
        print(f"Saved: {shot_monthly}")

        # Switch to Transaction History Tab
        tab_history_btn = driver.find_element(By.XPATH, "//button[contains(., 'Riwayat Nota Transaksi')]")
        tab_history_btn.click()
        time.sleep(1.5)

        # Screenshot of History with Excel button
        shot_history = os.path.join(ARTIFACT_DIR, "09_riwayat_transaksi_excel.png")
        driver.save_screenshot(shot_history)
        print(f"Saved: {shot_history}")

        print("Browser UI test PASSED successfully!")
    finally:
        driver.quit()

if __name__ == '__main__':
    test_excel_direct()
    test_browser_ui()
