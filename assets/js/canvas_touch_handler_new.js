/**
 * Canvas Responsive Scaling and Touch Handler
 * Multi-Box & Polygon Professional Mobile Editor with Streamlit-Like UI
 */

(function () {
    const silence = (w) => {
        try {
            if (!w || !w.console) return;
            ['warn', 'error', 'log'].forEach(m => {
                const original = w.console[m];
                if (!original || original.__isMuted) return;
                w.console[m] = function (...args) {
                    const msg = String(args[0] || "");
                    if (/Invalid color|theme\.sidebar|widgetBackground|Unrecognized feature|ambient-light|battery|wake-lock|sandbox|document-domain|oversized-images|vr|layout-animations|legacy-image-formats|allow-scripts|allow-same-origin|payment|microphone|camera|geolocation|passive event listener|wheel/i.test(msg)) return;
                    original.apply(this, args);
                };
                w.console[m].__isMuted = true;
            });
        } catch (e) { }
    };
    silence(window);

    // Config Check
    let config = window.CANVAS_CONFIG || (window.parent ? window.parent.CANVAS_CONFIG : null);
    if (!config && window.CANVAS_CONFIG_JSON) {
        try { config = JSON.parse(window.CANVAS_CONFIG_JSON); } catch (e) { }
    }
    if (!config) return;

    const { CANVAS_WIDTH, CANVAS_HEIGHT } = config;

    const getActiveIframe = () => {
        const all = parent.document.querySelectorAll('iframe[title="streamlit_drawable_canvas.st_canvas"], iframe[src*="streamlit_drawable_canvas"]');
        for (let i = all.length - 1; i >= 0; i--) {
            const f = all[i];
            if (!f.closest('[data-stale="true"]')) return f;
        }
        return all[all.length - 1];
    };

    let lastHistoryCall = 0;
    const throttledReplaceState = (url) => {
        const now = Date.now();
        if (now - lastHistoryCall < 50) return false;
        parent.history.replaceState({}, '', url.toString());
        try { parent.dispatchEvent(new Event('popstate')); } catch (e) { }
        lastHistoryCall = now;
        return true;
    };

    const triggerRerun = () => {
        const now = Date.now();
        if (window.lastRerunTrigger && (now - window.lastRerunTrigger < 400)) return;
        window.lastRerunTrigger = now;
        setTimeout(() => {
            // Robust Text-Based Search for the Sync Button
            const buttons = Array.from(parent.document.querySelectorAll('button'));
            const syncBtn = buttons.find(b => b.textContent && b.textContent.includes("GLOBAL SYNC"));

            if (syncBtn) {
                console.log("JS: Found Sync Button, clicking...");
                syncBtn.click();
            } else {
                console.error("JS: Sync Button 'GLOBAL SYNC' NOT FOUND in parent document.");
                const globalMarker = parent.document.querySelector('[data-sync-id="global_sync"]');
                if (globalMarker) {
                    const block = globalMarker.closest('[data-testid="stVerticalBlock"]');
                    if (block) {
                        const blockBtns = block.querySelectorAll('button');
                        if (blockBtns.length > 0) blockBtns[blockBtns.length - 1].click();
                    }
                }
            }
        }, 500); // 500ms delay for stability
    };

    // Shared UI Button Style
    const btnBase = `
        display: flex; align-items: center; justify-content: center; gap: 8px;
        height: 44px; padding: 0 24px; min-width: 120px;
        border-radius: 8px; font-family: "Source Sans Pro", sans-serif; font-weight: 600; font-size: 16px;
        cursor: pointer; transition: all 0.2s;
        border: 1px solid rgba(49, 51, 63, 0.2);
        background: white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    `;

    class BaseEditor {
        constructor(id) {
            this.id = id;
            this.overlay = null;
            this.toolbar = null;
            this.currentWrapper = null;
            this.createBaseSelect();
        }

        createBaseSelect() {
            // Overlay
            this.overlay = parent.document.createElement('div');
            this.overlay.id = this.id + '-overlay';
            Object.assign(this.overlay.style, {
                position: 'absolute',
                top: '0', left: '0', width: '100%', height: '100%',
                zIndex: '999',
                touchAction: 'none',
                display: 'none',
                cursor: 'crosshair',
                overflow: 'visible'
            });

            // Toolbar
            this.toolbar = parent.document.createElement('div');
            this.toolbar.id = this.id + '-toolbar';
            Object.assign(this.toolbar.style, {
                display: 'none',
                gap: '12px',
                padding: '16px 0',
                background: 'transparent',
                alignItems: 'center',
                justifyContent: 'center',
                width: '100%',
                pointerEvents: 'auto',
                flexDirection: 'row',
                position: 'relative',
                zIndex: '2000'
            });
        }

        mount() {
            const iframe = getActiveIframe();
            if (!iframe) return false;
            const wrapper = iframe.parentElement;
            if (!wrapper) return false;

            if (this.currentWrapper !== wrapper || !this.overlay.isConnected) {
                const stale = wrapper.querySelector('#' + this.id + '-overlay');
                if (stale && stale !== this.overlay) stale.remove();
                wrapper.appendChild(this.overlay);
                this.currentWrapper = wrapper;
            }

            if (wrapper.nextElementSibling !== this.toolbar) {
                // Remove stale toolbars from other editors if they are sticking around
                const oldBars = parent.document.querySelectorAll('[id$="-toolbar"]');
                oldBars.forEach(b => { if (b !== this.toolbar) b.remove(); });
                wrapper.after(this.toolbar);
            }
            return true;
        }

        show() {
            this.overlay.style.display = 'block';
            this.toolbar.style.display = 'flex';
        }

        hide() {
            this.overlay.style.display = 'none';
            this.toolbar.style.display = 'none';
        }
    }

    // NEW: PointEditor for AI Click mode
    class PointEditor extends BaseEditor {
        constructor() {
            super('point-editor');
            this.lastTapTime = 0;
            this.bindEvents();
        }

        bindEvents() {
            this.overlay.addEventListener('pointerdown', this.onPointerDown.bind(this));
            this.overlay.addEventListener('touchstart', this.onPointerDown.bind(this), { passive: false });
        }

        checkMode() {
            let mode = window.CANVAS_CONFIG?.DRAWING_MODE || '';
            if (mode === 'point') {
                if (this.mount()) {
                    this.show();
                    console.log("JS: Point editor activated");
                }
            } else {
                this.hide();
            }
        }

        onPointerDown(e) {
            e.preventDefault();
            e.stopPropagation();

            const now = Date.now();
            if (now - this.lastTapTime < 300) return; // Debounce
            this.lastTapTime = now;

            const rect = this.overlay.getBoundingClientRect();
            const x = Math.round(e.clientX - rect.left);
            const y = Math.round(e.clientY - rect.top);

            console.log(`JS: Point tap at (${x}, ${y})`);

            // Set URL parameter
            const url = new URL(parent.location.href);
            url.searchParams.set('tap', `${x},${y},${now}`);
            throttledReplaceState(url);
        }
    }
