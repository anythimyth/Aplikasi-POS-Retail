// Common Application Utilities

// Format number to Indonesian Rupiah
function formatRupiah(number) {
    if (isNaN(number) || number === null || number === undefined) return 'Rp 0';
    return new Intl.NumberFormat('id-ID', {
        style: 'currency',
        currency: 'IDR',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(number);
}

// Web Audio API Synthesizer for Cashier Scan & Error beeps
const SoundFX = {
    audioCtx: null,

    init() {
        if (!this.audioCtx) {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
                this.audioCtx = new AudioContext();
            }
        }
    },

    playSuccess() {
        try {
            this.init();
            if (!this.audioCtx) return;
            if (this.audioCtx.state === 'suspended') {
                this.audioCtx.resume();
            }
            const osc = this.audioCtx.createOscillator();
            const gain = this.audioCtx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(1760, this.audioCtx.currentTime); // High pleasant beep
            gain.gain.setValueAtTime(0.15, this.audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, this.audioCtx.currentTime + 0.12);
            osc.connect(gain);
            gain.connect(this.audioCtx.destination);
            osc.start();
            osc.stop(this.audioCtx.currentTime + 0.12);
        } catch (e) {
            // Audio policy or no audio device
        }
    },

    playError() {
        try {
            this.init();
            if (!this.audioCtx) return;
            if (this.audioCtx.state === 'suspended') {
                this.audioCtx.resume();
            }
            const osc = this.audioCtx.createOscillator();
            const gain = this.audioCtx.createGain();
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(220, this.audioCtx.currentTime); // Low buzz
            gain.gain.setValueAtTime(0.2, this.audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, this.audioCtx.currentTime + 0.25);
            osc.connect(gain);
            gain.connect(this.audioCtx.destination);
            osc.start();
            osc.stop(this.audioCtx.currentTime + 0.25);
        } catch (e) {
            // Audio policy
        }
    }
};

// Simple Toast Notification
function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    const bgColors = {
        success: 'bg-emerald-600 text-white',
        danger: 'bg-rose-600 text-white',
        warning: 'bg-amber-500 text-white',
        info: 'bg-indigo-600 text-white'
    };
    const icons = {
        success: 'fa-check-circle',
        danger: 'fa-triangle-exclamation',
        warning: 'fa-circle-exclamation',
        info: 'fa-circle-info'
    };

    toast.className = `flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg font-medium text-sm transition-all transform duration-300 pointer-events-auto ${bgColors[type] || bgColors.info}`;
    toast.innerHTML = `
        <i class="fa-solid ${icons[type] || icons.info} text-lg"></i>
        <span>${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-2');
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}
