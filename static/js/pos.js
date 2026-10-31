// Point of Sale (POS) Cashier Logic

class PosTerminal {
    constructor() {
        this.cart = [];
        this.selectedCategory = 'all';
        this.paymentMethod = 'CASH';
        this.cashAmount = 0;
        this.customerName = 'Pelanggan Umum';

        this.initElements();
        this.bindEvents();
        this.focusBarcodeInput();
    }

    initElements() {
        this.barcodeInput = document.getElementById('barcode-input');
        this.cartItemsContainer = document.getElementById('cart-items');
        this.cartEmptyState = document.getElementById('cart-empty');
        this.totalBadge = document.getElementById('total-badge');
        this.subtotalDisplay = document.getElementById('subtotal-display');
        this.totalDisplay = document.getElementById('total-display');
        this.cashInput = document.getElementById('cash-input');
        this.changeDisplay = document.getElementById('change-display');
        this.changeContainer = document.getElementById('change-container');
        this.checkoutBtn = document.getElementById('checkout-btn');
        this.productGrid = document.getElementById('product-grid');
        this.productCards = document.querySelectorAll('.product-card');
        this.receiptModal = document.getElementById('thermal-receipt-modal');
        this.customerNameInput = document.getElementById('customer-name-input');
    }

    bindEvents() {
        // Barcode / Search Enter key listener
        if (this.barcodeInput) {
            this.barcodeInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.handleBarcodeSubmit();
                }
            });
            // Instant filter while typing
            this.barcodeInput.addEventListener('input', () => {
                this.filterProductGrid();
            });
        }

        // Cash Input realtime calculation
        if (this.cashInput) {
            this.cashInput.addEventListener('input', () => {
                this.cashAmount = parseInt(this.cashInput.value) || 0;
                this.updatePaymentCalculations();
            });
            this.cashInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.processCheckout();
                }
            });
        }

        // Global hotkeys (F1, F2, F4)
        window.addEventListener('keydown', (e) => {
            if (e.key === 'F1') {
                e.preventDefault();
                this.focusBarcodeInput();
            } else if (e.key === 'F2') {
                e.preventDefault();
                if (this.cashInput) this.cashInput.focus();
            } else if (e.key === 'F4') {
                e.preventDefault();
                this.clearCart();
            }
        });
    }

    focusBarcodeInput() {
        if (this.barcodeInput) {
            this.barcodeInput.focus();
            this.barcodeInput.select();
        }
    }

    // Filter product grid visually by search and category
    filterProductGrid() {
        const query = (this.barcodeInput.value || '').toLowerCase().trim();
        this.productCards.forEach(card => {
            const name = card.dataset.name.toLowerCase();
            const sku = card.dataset.sku.toLowerCase();
            const cat = card.dataset.category;

            const matchesCategory = (this.selectedCategory === 'all' || cat === this.selectedCategory);
            const matchesQuery = (!query || name.includes(query) || sku.includes(query));

            if (matchesCategory && matchesQuery) {
                card.classList.remove('hidden');
            } else {
                card.classList.add('hidden');
            }
        });
    }

    filterCategory(catId, btnEl) {
        this.selectedCategory = catId;
        document.querySelectorAll('.cat-pill').forEach(btn => {
            btn.classList.remove('bg-brand-600', 'text-white', 'shadow-md');
            btn.classList.add('bg-white', 'text-slate-600', 'border-slate-200');
        });
        if (btnEl) {
            btnEl.classList.remove('bg-white', 'text-slate-600', 'border-slate-200');
            btnEl.classList.add('bg-brand-600', 'text-white', 'shadow-md');
        }
        this.filterProductGrid();
    }

    // Barcode scanner trigger
    async handleBarcodeSubmit() {
        const query = (this.barcodeInput.value || '').trim();
        if (!query) return;

        try {
            const res = await fetch(`/api/pos/search?q=${encodeURIComponent(query)}`);
            const data = await res.json();

            if (data.success && data.is_exact) {
                // Exact Barcode match! Add directly to cart
                this.addToCart(data.product);
                this.barcodeInput.value = '';
                this.filterProductGrid();
                SoundFX.playSuccess();
            } else if (data.success && data.products && data.products.length === 1) {
                // Single item matched query
                this.addToCart(data.products[0]);
                this.barcodeInput.value = '';
                this.filterProductGrid();
                SoundFX.playSuccess();
            } else {
                // Check if any product card on page matches exact sku
                const exactCard = Array.from(this.productCards).find(c => c.dataset.sku === query);
                if (exactCard) {
                    exactCard.click();
                    this.barcodeInput.value = '';
                    this.filterProductGrid();
                } else {
                    SoundFX.playError();
                    showToast(`Produk dengan Barcode / Kata Kunci "${query}" tidak ditemukan!`, 'danger');
                }
            }
        } catch (e) {
            SoundFX.playError();
            showToast('Gagal memproses pencarian barcode', 'danger');
        }
        this.focusBarcodeInput();
    }

    addToCartById(productId) {
        if (!window.POS_PRODUCTS) return;
        const prod = window.POS_PRODUCTS.find(p => p.id === productId);
        if (prod) {
            this.addToCart(prod);
        }
    }

    addToCart(product) {
        if (product.stock <= 0) {
            SoundFX.playError();
            showToast(`Stok untuk "${product.name}" sudah HABIS (0 unit)!`, 'danger');
            return;
        }

        const existing = this.cart.find(it => it.id === product.id);
        if (existing) {
            if (existing.qty + 1 > product.stock) {
                SoundFX.playError();
                showToast(`Stok tidak mencukupi! Hanya tersedia ${product.stock} unit.`, 'warning');
                return;
            }
            existing.qty += 1;
        } else {
            this.cart.push({
                id: product.id,
                name: product.name,
                sku: product.sku,
                sell_price: product.sell_price,
                stock: product.stock,
                qty: 1
            });
        }

        SoundFX.playSuccess();
        this.renderCart();
    }

    updateQty(productId, delta) {
        const item = this.cart.find(it => it.id === productId);
        if (!item) return;

        const newQty = item.qty + delta;
        if (newQty <= 0) {
            this.removeFromCart(productId);
            return;
        }
        if (newQty > item.stock) {
            SoundFX.playError();
            showToast(`Jumlah melebihi stok tersedia (${item.stock} unit)!`, 'warning');
            return;
        }

        item.qty = newQty;
        this.renderCart();
    }

    setQty(productId, val) {
        const item = this.cart.find(it => it.id === productId);
        if (!item) return;

        let qty = parseInt(val) || 1;
        if (qty <= 0) qty = 1;
        if (qty > item.stock) {
            SoundFX.playError();
            showToast(`Jumlah melebihi stok tersedia (${item.stock} unit)!`, 'warning');
            qty = item.stock;
        }

        item.qty = qty;
        this.renderCart();
    }

    removeFromCart(productId) {
        this.cart = this.cart.filter(it => it.id !== productId);
        this.renderCart();
    }

    clearCart() {
        if (this.cart.length === 0) return;
        this.cart = [];
        this.cashAmount = 0;
        if (this.cashInput) this.cashInput.value = '';
        this.renderCart();
        showToast('Keranjang telah dikosongkan.', 'info');
        this.focusBarcodeInput();
    }

    calculateTotal() {
        return this.cart.reduce((sum, it) => sum + (it.sell_price * it.qty), 0);
    }

    setPaymentMethod(method, btnEl) {
        this.paymentMethod = method;
        document.querySelectorAll('.pay-method-btn').forEach(b => {
            b.classList.remove('border-brand-600', 'bg-brand-50/70', 'text-brand-700');
            b.classList.add('border-slate-200', 'text-slate-600');
        });
        if (btnEl) {
            btnEl.classList.remove('border-slate-200', 'text-slate-600');
            btnEl.classList.add('border-brand-600', 'bg-brand-50/70', 'text-brand-700');
        }

        const cashDetails = document.getElementById('cash-details-section');
        if (method === 'CASH') {
            if (cashDetails) cashDetails.classList.remove('hidden');
        } else {
            if (cashDetails) cashDetails.classList.add('hidden');
        }

        this.updatePaymentCalculations();
    }

    setExactCash() {
        const total = this.calculateTotal();
        this.cashAmount = total;
        if (this.cashInput) {
            this.cashInput.value = total;
        }
        this.updatePaymentCalculations();
    }

    addCashPreset(amount) {
        const total = this.calculateTotal();
        this.cashAmount = amount;
        if (this.cashInput) {
            this.cashInput.value = amount;
        }
        this.updatePaymentCalculations();
    }

    updatePaymentCalculations() {
        const total = this.calculateTotal();
        const change = this.cashAmount - total;

        if (this.paymentMethod === 'CASH') {
            if (this.cashAmount >= total && total > 0) {
                this.changeContainer.className = 'flex items-center justify-between p-3 rounded-xl bg-emerald-50 border border-emerald-200';
                this.changeDisplay.className = 'text-base font-black text-emerald-700 font-mono';
                this.changeDisplay.innerText = formatRupiah(change);
                this.checkoutBtn.disabled = false;
                this.checkoutBtn.classList.remove('opacity-50', 'cursor-not-allowed');
            } else if (total > 0) {
                this.changeContainer.className = 'flex items-center justify-between p-3 rounded-xl bg-rose-50 border border-rose-200';
                this.changeDisplay.className = 'text-xs font-bold text-rose-600 font-mono';
                this.changeDisplay.innerText = `Kurang ${formatRupiah(Math.abs(change))}`;
                this.checkoutBtn.disabled = true;
                this.checkoutBtn.classList.add('opacity-50', 'cursor-not-allowed');
            } else {
                this.changeDisplay.innerText = 'Rp 0';
                this.checkoutBtn.disabled = true;
                this.checkoutBtn.classList.add('opacity-50', 'cursor-not-allowed');
            }
        } else {
            // Non-cash (QRIS / Transfer)
            this.checkoutBtn.disabled = (total <= 0);
            if (total > 0) {
                this.checkoutBtn.classList.remove('opacity-50', 'cursor-not-allowed');
            } else {
                this.checkoutBtn.classList.add('opacity-50', 'cursor-not-allowed');
            }
        }
    }

    renderCart() {
        const total = this.calculateTotal();
        const totalItemsCount = this.cart.reduce((cnt, it) => cnt + it.qty, 0);

        if (this.totalBadge) this.totalBadge.innerText = `${totalItemsCount} item`;
        if (this.subtotalDisplay) this.subtotalDisplay.innerText = formatRupiah(total);
        if (this.totalDisplay) this.totalDisplay.innerText = formatRupiah(total);

        if (this.cart.length === 0) {
            this.cartEmptyState.classList.remove('hidden');
            this.cartItemsContainer.classList.add('hidden');
            this.cartItemsContainer.innerHTML = '';
            this.checkoutBtn.disabled = true;
            this.checkoutBtn.classList.add('opacity-50', 'cursor-not-allowed');
            this.updatePaymentCalculations();
            return;
        }

        this.cartEmptyState.classList.add('hidden');
        this.cartItemsContainer.classList.remove('hidden');
        this.cartItemsContainer.innerHTML = '';

        this.cart.forEach(item => {
            const subtotal = item.sell_price * item.qty;
            const row = document.createElement('div');
            row.className = 'p-3 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-between gap-2 transition-all hover:bg-slate-100/70';
            row.innerHTML = `
                <div class="flex-1 min-w-0 pr-1">
                    <h5 class="text-xs font-bold text-slate-800 truncate leading-snug">${item.name}</h5>
                    <div class="flex items-center gap-2 mt-0.5 text-[11px] text-slate-500">
                        <span class="font-mono">${formatRupiah(item.sell_price)}</span>
                        <span class="text-slate-300">•</span>
                        <span class="text-slate-400">Stok: ${item.stock}</span>
                    </div>
                </div>
                
                <!-- Qty Controls -->
                <div class="flex items-center gap-1.5 flex-shrink-0">
                    <button type="button" onclick="posTerminal.updateQty(${item.id}, -1)" 
                            class="w-6 h-6 rounded-lg bg-white border border-slate-200 text-slate-600 hover:bg-slate-200 flex items-center justify-center text-xs font-bold transition-colors">
                        -
                    </button>
                    <input type="number" min="1" max="${item.stock}" value="${item.qty}"
                           onchange="posTerminal.setQty(${item.id}, this.value)"
                           class="w-10 text-center py-0.5 rounded-lg border border-slate-200 text-xs font-bold font-mono focus:ring-1 focus:ring-brand-500">
                    <button type="button" onclick="posTerminal.updateQty(${item.id}, 1)" 
                            class="w-6 h-6 rounded-lg bg-white border border-slate-200 text-slate-600 hover:bg-slate-200 flex items-center justify-center text-xs font-bold transition-colors">
                        +
                    </button>
                </div>

                <!-- Subtotal & Delete -->
                <div class="text-right min-w-[70px] flex-shrink-0">
                    <span class="text-xs font-black text-slate-800 font-mono block">${formatRupiah(subtotal)}</span>
                    <button type="button" onclick="posTerminal.removeFromCart(${item.id})" title="Hapus Item"
                            class="text-[10px] text-rose-500 hover:text-rose-700 mt-0.5">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            `;
            this.cartItemsContainer.appendChild(row);
        });

        this.updatePaymentCalculations();
    }

    async processCheckout() {
        const total = this.calculateTotal();
        if (this.cart.length === 0 || total <= 0) {
            SoundFX.playError();
            showToast('Keranjang belanja masih kosong!', 'warning');
            return;
        }

        if (this.paymentMethod === 'CASH' && this.cashAmount < total) {
            SoundFX.playError();
            showToast(`Uang yang diterima masih kurang ${formatRupiah(total - this.cashAmount)}!`, 'danger');
            if (this.cashInput) this.cashInput.focus();
            return;
        }

        const customer = (this.customerNameInput ? this.customerNameInput.value : 'Pelanggan Umum').trim() || 'Pelanggan Umum';

        this.checkoutBtn.disabled = true;
        this.checkoutBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Memproses...</span>`;

        try {
            const res = await fetch('/api/pos/checkout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    items: this.cart,
                    customer_name: customer,
                    payment_method: this.paymentMethod,
                    payment_amount: (this.paymentMethod === 'CASH') ? this.cashAmount : total
                })
            });

            const data = await res.json();

            if (data.success) {
                SoundFX.playSuccess();
                showToast(`Transaksi berhasil! No Faktur: ${data.invoice_number}`, 'success');
                // Open Thermal Receipt modal
                this.displayThermalReceipt(data.invoice_number);
                // Clear cart state
                this.cart = [];
                this.cashAmount = 0;
                if (this.cashInput) this.cashInput.value = '';
                this.renderCart();
            } else {
                SoundFX.playError();
                showToast(data.message, 'danger');
            }
        } catch (e) {
            SoundFX.playError();
            showToast('Terjadi gangguan saat memproses checkout.', 'danger');
        } finally {
            this.checkoutBtn.disabled = false;
            this.checkoutBtn.innerHTML = `
                <i class="fa-solid fa-check-circle text-lg"></i>
                <span>Selesaikan Pembayaran (Bayar)</span>
            `;
        }
    }

    async displayThermalReceipt(invoiceNumber) {
        try {
            const res = await fetch(`/api/pos/receipt/${invoiceNumber}`);
            const data = await res.json();

            if (data.success) {
                const trx = data.transaction;
                const items = data.items;
                const store = data.store;

                document.getElementById('receipt-store-name').innerText = store.name;
                document.getElementById('receipt-store-address').innerText = store.address;
                document.getElementById('receipt-store-phone').innerText = 'Telp: ' + store.phone;
                document.getElementById('receipt-invoice').innerText = trx.invoice_number;
                document.getElementById('receipt-date').innerText = trx.date;
                document.getElementById('receipt-cashier').innerText = trx.cashier_name || 'Kasir';
                document.getElementById('receipt-customer').innerText = trx.customer_name || 'Pelanggan Umum';

                // Render items in receipt
                const itemsList = document.getElementById('receipt-items-list');
                itemsList.innerHTML = '';
                items.forEach(it => {
                    const div = document.createElement('div');
                    div.className = 'mb-1.5';
                    div.innerHTML = `
                        <div class="font-bold text-left">${it.product_name}</div>
                        <div class="flex justify-between text-[11px] text-slate-600">
                            <span>${it.qty} x ${formatRupiah(it.sell_price)}</span>
                            <span class="font-bold">${formatRupiah(it.subtotal)}</span>
                        </div>
                    `;
                    itemsList.appendChild(div);
                });

                document.getElementById('receipt-total').innerText = formatRupiah(trx.total_amount);
                document.getElementById('receipt-payment-method').innerText = `BAYAR (${trx.payment_method})`;
                document.getElementById('receipt-payment-amount').innerText = formatRupiah(trx.payment_amount);
                document.getElementById('receipt-change').innerText = formatRupiah(trx.change_amount);
                document.getElementById('receipt-footer-text').innerText = store.footer;

                this.receiptModal.classList.remove('hidden');
            }
        } catch (e) {
            showToast('Gagal memuat format cetak struk', 'danger');
        }
    }

    closeReceiptModal() {
        if (this.receiptModal) {
            this.receiptModal.classList.add('hidden');
        }
        this.focusBarcodeInput();
    }

    printReceipt() {
        window.print();
    }
}

// Global initialization
let posTerminal = null;
document.addEventListener('DOMContentLoaded', () => {
    posTerminal = new PosTerminal();
});
