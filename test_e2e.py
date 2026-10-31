import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ARTIFACT_DIR = r"C:\Users\Anonim\.gemini\antigravity\brain\7835f103-6a62-4fa6-9445-18e3a5fa8974"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

def run_tests():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1366,850")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 10)

    try:
        print("[1/8] Opening Login Page...")
        driver.get("http://127.0.0.1:5000/login")
        time.sleep(1.5)
        shot1 = os.path.join(ARTIFACT_DIR, "01_login_page.png")
        driver.save_screenshot(shot1)
        print(f"Saved: {shot1}")

        # Click Admin Quick Demo button
        print("[2/8] Logging in as Admin...")
        admin_btn = driver.find_element(By.XPATH, "//button[contains(., 'Admin Toko')]")
        admin_btn.click()
        time.sleep(0.5)

        submit_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        submit_btn.click()
        time.sleep(2)

        # Dashboard View
        print("[3/8] Capturing Dashboard with Charts & KPIs...")
        shot2 = os.path.join(ARTIFACT_DIR, "02_dashboard_kpi.png")
        driver.save_screenshot(shot2)
        print(f"Saved: {shot2}")

        # Inventory View
        print("[4/8] Navigating to Inventory...")
        driver.get("http://127.0.0.1:5000/inventory")
        time.sleep(1.5)
        shot3 = os.path.join(ARTIFACT_DIR, "03_inventory_catalog.png")
        driver.save_screenshot(shot3)
        print(f"Saved: {shot3}")

        # Open Restock Modal for an item
        print("[5/8] Opening Restock / Stock Adjustment modal...")
        restock_btn = driver.find_elements(By.XPATH, "//button[@title='Atur / Restock Stok Barang']")[0]
        restock_btn.click()
        time.sleep(1)

        qty_input = driver.find_element(By.ID, "adjust-qty")
        qty_input.clear()
        qty_input.send_keys("25")
        
        note_input = driver.find_element(By.ID, "adjust-note")
        note_input.clear()
        note_input.send_keys("Penerimaan barang dari Supplier PT Sukses")
        time.sleep(0.5)

        shot4 = os.path.join(ARTIFACT_DIR, "04_stock_restock_modal.png")
        driver.save_screenshot(shot4)
        print(f"Saved: {shot4}")

        # Submit restock
        submit_restock = driver.find_element(By.XPATH, "//form[@id='stock-form']//button[@type='submit']")
        submit_restock.click()
        time.sleep(1.5)

        # Navigate to POS Cashier
        print("[6/8] Navigating to POS Cashier Terminal...")
        driver.get("http://127.0.0.1:5000/pos")
        time.sleep(1.5)
        
        # Add products to cart by clicking product cards
        print("[7/8] Adding items to cart and testing cash calculator...")
        cards = driver.find_elements(By.CLASS_NAME, "product-card")
        # Click 1st available card
        cards[0].click()
        time.sleep(0.3)
        cards[0].click() # x2
        time.sleep(0.3)
        # Click 2nd available card
        cards[1].click()
        time.sleep(0.3)
        # Click 4th available card
        cards[4].click()
        time.sleep(0.5)

        # Set cash payment via shortcut preset button (e.g. 50rb or 100rb)
        preset_100k = driver.find_element(By.XPATH, "//button[contains(., '100rb')]")
        preset_100k.click()
        time.sleep(1)

        shot5 = os.path.join(ARTIFACT_DIR, "05_pos_cashier_checkout.png")
        driver.save_screenshot(shot5)
        print(f"Saved: {shot5}")

        # Execute checkout
        print("[8/8] Executing checkout & displaying thermal receipt...")
        checkout_btn = driver.find_element(By.ID, "checkout-btn")
        driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", checkout_btn)
        time.sleep(2)

        shot6 = os.path.join(ARTIFACT_DIR, "06_thermal_receipt.png")
        driver.save_screenshot(shot6)
        print(f"Saved: {shot6}")

        # Close receipt modal and open reports
        close_receipt = driver.find_element(By.XPATH, "//button[contains(., 'Transaksi Baru')]")
        driver.execute_script("arguments[0].click();", close_receipt)
        time.sleep(0.5)

        print("[9/8] Checking Sales Reports...")
        driver.get("http://127.0.0.1:5000/reports")
        time.sleep(2)
        shot7 = os.path.join(ARTIFACT_DIR, "07_sales_reports.png")
        driver.save_screenshot(shot7)
        print(f"Saved: {shot7}")

        print("ALL E2E BROWSER TESTS COMPLETED SUCCESSFULLY!")

    finally:
        driver.quit()

if __name__ == '__main__':
    run_tests()
