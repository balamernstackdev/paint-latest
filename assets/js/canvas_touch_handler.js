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
                    if (/Invalid color|theme\.sidebar|widgetBackground|Unrecognized feature|ambient-light|battery|wake-lock|sandbox|document-domain|oversized-images|vr|layout-animations|legacy-image-formats|allow-scripts|allow-same-origin|payment|microphone|camera|geolocation/i.test(msg)) return;
                    original.apply(this, args);
                };
                w.console[m].__isMuted = true;
            });
        } catch (e) { }
    };
    silence(window);

    // 🛑 BLOCK CONTEXT MENU (PREVENT "SAVE IMAGE" / "SHARE")
    window.addEventListener('contextmenu', e => {
        if (e.target.closest('[id$="-overlay"]') || e.target.tagName === 'IFRAME' || e.target.closest('canvas')) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        }
    }, { capture: true, passive: false });

    // 📱 ADVANCED GESTURE TRACKING
    window.isCanvasGesturing = false;
    window.lastPinchTime = 0;
    window.activePointers = new Map();
    window.userZoomLevel = 1.0;
    window.panX = 0;
    window.panY = 0;
    window.lastPinchDist = 0;

    // 🤏 PINCH STATE SNAPSHOT (set on touchstart, used through the gesture)
    window._pinch = {
        active: false,
        startDist: 0,
        startZoom: 1.0,
        startPanX: 0,
        startPanY: 0,
        // Midpoint in viewport px at gesture start
        startMidViewX: 0,
        startMidViewY: 0,
        // Midpoint in viewport px at gesture start relative to wrapper
        startMidRelX: 0,
        startMidRelY: 0,
    };
    window._rafScheduled = false;

    // ─────────────────────────────────────────────────────────────────────────
    // 🛡️  SUPER-STRICT GESTURE INTERCEPTOR (Parent Level)
    // ─────────────────────────────────────────────────────────────────────────
    if (!window.parent.__ANTIGRAVITY_TOUCH_HANDLERS_ATTACHED) {
        try {
            // Snapshot gesture state on first touch so we have stable references
            window.parent.document.addEventListener('touchstart', e => {
                if (e.touches.length === 2) {
                    window.isCanvasGesturing = true;
                    const t1 = e.touches[0], t2 = e.touches[1];
                    const dist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
                    const midX = (t1.clientX + t2.clientX) / 2;
                    const midY = (t1.clientY + t2.clientY) / 2;

                    // Snapshot for the anchor-zoom math used in touchmove
                    window._pinch.active = true;
                    window._pinch.startDist = dist;
                    window._pinch.startZoom = window.userZoomLevel || 1.0;
                    window._pinch.startPanX = window.panX || 0;
                    window._pinch.startPanY = window.panY || 0;
                    window._pinch.startMidViewX = midX;
                    window._pinch.startMidViewY = midY;

                    // Also store legacy fields used elsewhere
                    window.lastPinchDist = dist;
                    window.lastPinchCenter = { x: midX, y: midY };
                }
            }, { capture: true, passive: true });
        } catch (e) { }

        // Global pointer-id tracker (used to guard single-finger editors)
        window.parent.document.addEventListener('pointerdown', e => window.activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY }), true);
        window.parent.document.addEventListener('pointerup', e => window.activePointers.delete(e.pointerId), true);
        window.parent.document.addEventListener('pointercancel', e => window.activePointers.delete(e.pointerId), true);

        window.parent.__ANTIGRAVITY_TOUCH_HANDLERS_ATTACHED = true;
    }

    // Internal tracker for overlay elements (fallback)
    const trackPointer = (el) => {
        el.addEventListener('pointerdown', e => window.activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY }));
        el.addEventListener('pointerup', e => window.activePointers.delete(e.pointerId));
        el.addEventListener('pointercancel', e => window.activePointers.delete(e.pointerId));
    };

    // ─────────────────────────────────────────────────────────────────────────
    // 🤏  ANCHOR-CORRECT PINCH-ZOOM + PAN HANDLER
    //
    //  Math explanation:
    //  Let W = CANVAS_WIDTH (intrinsic), H = CANVAS_HEIGHT.
    //  The wrapper has visual size  wW = W * baseScale, wH = H * baseScale.
    //  The canvas is placed at top:50% left:50% and pulled back by -50%/-50%,
    //  then scaled by totalScale = baseScale * userZoom.
    //  Its visual size is W * totalScale.  Its top-left corner in wrapper coords:
    //    left =  wW/2 - (W*totalScale)/2  =  (wW - W*totalScale)/2
    //  A touch at viewport.x maps to wrapper.x = viewport.x - wrapperRect.left.
    //  For the zoom to be anchored at the midpoint pixel we need:
    //    (mid_rel - pan_visual_offset) / oldZoom == (mid_rel - pan_visual_offset') / newZoom
    //  Rearranging gives the new intrinsic pan:
    //    panX' = panX + (mid_rel_x / baseScale) * (1/oldZoom - 1/newZoom)
    // ─────────────────────────────────────────────────────────────────────────
    const _getWrapper = () => {
        const iframe = (() => {
            const all = parent.document.querySelectorAll('iframe[title="streamlit_drawable_canvas.st_canvas"], iframe[src*="streamlit_drawable_canvas"]');
            for (let i = all.length - 1; i >= 0; i--) {
                const f = all[i];
                if (!f.closest('[data-stale="true"]')) return f;
            }
            return all[all.length - 1];
        })();
        return iframe ? iframe.parentElement : null;
    };

    const _scheduleFrame = () => {
        if (window._rafScheduled) return;
        window._rafScheduled = true;
        requestAnimationFrame(() => {
            window._rafScheduled = false;
            applyResponsiveScale();
        });
    };

    const handlePinch = (e) => {
        if (e.touches.length !== 2) return;
        e.preventDefault();
        e.stopPropagation();

        window.isCanvasGesturing = true;

        const t1 = e.touches[0], t2 = e.touches[1];
        const dist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
        const midVX = (t1.clientX + t2.clientX) / 2;
        const midVY = (t1.clientY + t2.clientY) / 2;

        const p = window._pinch;
        if (!p.active || p.startDist < 4) return;

        // ── 1. New zoom level (clamped) ────────────────────────────────────
        const scaleFactor = dist / p.startDist;
        let newZoom = p.startZoom * scaleFactor;
        newZoom = Math.max(0.5, Math.min(8.0, newZoom));

        // ── 2. Compute wrapper-relative midpoint at gesture start ──────────
        //  Reuse the baseScale last computed by applyResponsiveScale so both
        //  the visual transform and the coordinate math use the SAME value.
        //  Fall back to computing it fresh if applyResponsiveScale hasn't run yet.
        const CWIDTH = (window.CANVAS_CONFIG || {}).CANVAS_WIDTH || CANVAS_WIDTH;
        const CHEIGHT = (window.CANVAS_CONFIG || {}).CANVAS_HEIGHT || CANVAS_HEIGHT;
        let baseScale = window._currentBaseScale;
        if (!baseScale) {
            // Fallback: measure container width same way applyResponsiveScale does
            const winW2 = (parent.window.visualViewport ? parent.window.visualViewport.width : parent.window.innerWidth) || parent.document.documentElement.clientWidth;
            let availW2 = winW2;
            try {
                const mb = parent.document.querySelector('.main .block-container');
                if (mb) { const r = mb.getBoundingClientRect(); if (r.width > 200) availW2 = Math.floor(r.width); }
            } catch (e) { }
            if (winW2 < 1024) {
                baseScale = (availW2 - 4) / CWIDTH;
            } else {
                const scaleW = Math.min(availW2 - 16, CWIDTH) / CWIDTH;
                const scaleH = ((parent.window.visualViewport ? parent.window.visualViewport.height : parent.window.innerHeight) - 120) / CHEIGHT;
                baseScale = Math.min(scaleW, scaleH, 1.0);
            }
            if (baseScale < 0.1) baseScale = 0.1;
        }

        const wrapper = _getWrapper();
        if (!wrapper) return;
        const wRect = wrapper.getBoundingClientRect();

        // Midpoint relative to wrapper centre (in intrinsic canvas units)
        //  wrapperCentreX = wRect.left + wRect.width/2  (visual)
        //  midInWrapper (visual)  = midVX - wRect.left
        //  midFromCentre (visual) = midInWrapper - wRect.width/2
        //  midFromCentre (intrinsic) = midFromCentre_visual / (baseScale * startZoom)
        // BUT we want the fixed anchor point in intrinsic coordinates:
        //  anchorIntrinsic = (startMidFromCentre_visual / (baseScale * startZoom)) - startPan
        //  That simplifies: for anchor zoom we just need the start midpoint relative to wrapper.

        const startMidRelX = p.startMidViewX - wRect.left;  // px from wrapper left
        const startMidRelY = p.startMidViewY - wRect.top;

        // ── 3. Anchor-correct pan ─────────────────────────────────────────
        //  In intrinsic coords, the midpoint = (midRel_visual / baseScale) - pan
        //  is a fixed scene point.  After zoom changes from Z0→Z1:
        //    panX1 = panX0 + midRelX_intrinsic * (1 - newZoom/oldZoom)
        //  where midRelX_intrinsic = (startMidRelX / baseScale) - (wW_intrinsic/2) + panX0
        //  but the wrapper width in intrinsic = CWIDTH (it is set = CWIDTH * baseScale visually).
        //  Let midC_intr = startMidRelX/baseScale - CWIDTH/2  (from canvas centre)
        //  Then anchoring gives:
        //    panX1 = midC_intr - (midC_intr - panX0) * (newZoom / oldZoom)

        const midC_X = startMidRelX / baseScale - CWIDTH / 2;  // from canvas centre, intrinsic
        const midC_Y = startMidRelY / baseScale - CHEIGHT / 2;

        let newPanX = midC_X - (midC_X - p.startPanX) * (newZoom / p.startZoom);
        let newPanY = midC_Y - (midC_Y - p.startPanY) * (newZoom / p.startZoom);

        // ── 4. Add finger-translation (two-finger pan) ────────────────────
        const moveDX = (midVX - p.startMidViewX) / (baseScale * newZoom);
        const moveDY = (midVY - p.startMidViewY) / (baseScale * newZoom);
        newPanX += moveDX;
        newPanY += moveDY;

        // ── 5. Clamp pan so image never exposes white space ───────────────
        const limitX = (CWIDTH * (newZoom - 1)) / (2 * newZoom);
        const limitY = (CHEIGHT * (newZoom - 1)) / (2 * newZoom);
        newPanX = Math.max(-limitX, Math.min(limitX, newPanX));
        newPanY = Math.max(-limitY, Math.min(limitY, newPanY));

        // ── 6. Commit to global state and schedule DOM update ─────────────
        window.userZoomLevel = newZoom;
        window.panX = newPanX;
        window.panY = newPanY;
        window.lastPinchDist = dist;
        window.lastPinchCenter = { x: midVX, y: midVY };
        window.lastPinchTime = Date.now();

        _scheduleFrame();
    };

    const handlePinchEnd = (e) => {
        if (e.touches.length < 2) {
            window.lastPinchDist = 0;
            window._pinch.active = false;
            // Keep isCanvasGesturing true briefly so editors don't misfire
            setTimeout(() => { window.isCanvasGesturing = false; }, 350);
        }
    };

    // ── Helper: snapshot pinch state (called from touchstart on any context) ──
    const _snapshotPinch = (t1, t2) => {
        const dist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
        const midX = (t1.clientX + t2.clientX) / 2;
        const midY = (t1.clientY + t2.clientY) / 2;
        window.isCanvasGesturing = true;
        window._pinch.active = true;
        window._pinch.startDist = dist;
        window._pinch.startZoom = window.userZoomLevel || 1.0;
        window._pinch.startPanX = window.panX || 0;
        window._pinch.startPanY = window.panY || 0;
        window._pinch.startMidViewX = midX;
        window._pinch.startMidViewY = midY;
        window.lastPinchDist = dist;
        window.lastPinchCenter = { x: midX, y: midY };
    };

    // Local window touchstart — fires even when parent guard is already set
    window.addEventListener('touchstart', e => {
        if (e.touches.length === 2) _snapshotPinch(e.touches[0], e.touches[1]);
    }, { capture: true, passive: true });

    // Attach to parent document to intercept events before iframes see them
    try {
        window.parent.document.addEventListener('touchmove', handlePinch, { capture: true, passive: false });
        window.parent.document.addEventListener('touchend', handlePinchEnd, { capture: true, passive: true });
        window.parent.document.addEventListener('touchcancel', handlePinchEnd, { capture: true, passive: true });

        // Local window fallback
        window.addEventListener('touchmove', handlePinch, { capture: true, passive: false });
        window.addEventListener('touchend', handlePinchEnd, { capture: true, passive: true });
        window.addEventListener('touchcancel', handlePinchEnd, { capture: true, passive: true });
    } catch (e) { }

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
        // REMOVED popstate dispatch to avoid double-rerun race conditions with manual trigger
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
        }, 200); // Reduced delay for faster first-click response
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
                touchAction: 'none', // 📱 Allow pinch-zoom but block pan (for drawing)
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
        }

        hide() {
            this.overlay.style.display = 'none';
            this.toolbar.style.display = 'none';
        }
    }

    class BoxEditor extends BaseEditor {
        constructor() {
            super('box-editor');
            this.boxes = [];
            this.selectedIndex = -1;
            this.isDrawing = false;
            this.isMoving = false;
            this.startX = 0; this.startY = 0;
            this.handles = [];
            this.startBox = null;
            this.activeHandle = null;

            this.boxContainer = parent.document.createElement('div');
            this.handleContainer = parent.document.createElement('div');
            this.overlay.appendChild(this.boxContainer);
            this.overlay.appendChild(this.handleContainer);

            this.createDOM();
            this.bindEvents();
        }

        createDOM() {
            // Handles
            const positions = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
            positions.forEach(pos => {
                const h = parent.document.createElement('div');
                h.dataset.handle = pos;
                Object.assign(h.style, {
                    position: 'absolute', width: '24px', height: '24px',
                    backgroundColor: '#FFFFFF', border: '2px solid #FF4B4B', borderRadius: '50%',
                    transform: 'translate(-50%, -50%)', zIndex: '1002', display: 'none',
                    pointerEvents: 'auto', cursor: 'pointer'
                });
                this.handleContainer.appendChild(h);
                this.handles.push(h);
            });

            // Toolbar Buttons
            const btnDelete = parent.document.createElement('button');
            btnDelete.innerHTML = "🗑️ Delete";
            btnDelete.style.cssText = btnBase + "color: #333;";
            btnDelete.onclick = (e) => { e.preventDefault(); this.deleteSelected(); };

            const btnApply = parent.document.createElement('button');
            btnApply.innerHTML = "✅ Apply";
            btnApply.style.cssText = btnBase + "border-color: #10B981; color: #10B981; background: #F0FDF4;";
            btnApply.onclick = (e) => { e.preventDefault(); this.commit(); };

            this.toolbar.appendChild(btnDelete);
            this.toolbar.appendChild(btnApply);
        }

        bindEvents() {
            trackPointer(this.overlay);
            this.overlay.onpointerdown = this.onPointerDown.bind(this);
            this.overlay.onpointermove = this.onPointerMove.bind(this);
            this.overlay.onpointerup = this.onPointerUp.bind(this);
            this.overlay.onpointercancel = this.onPointerUp.bind(this); // Reset on scroll
        }

        checkMode() {
            let mode = window.CANVAS_CONFIG?.DRAWING_MODE || 'point';
            if (mode === 'rect') {
                if (!this.mount()) return;
                this.show();
                this.updateDOM();
            } else {
                this.hide();
                this.boxes = [];
            }
        }

        deleteSelected() {
            if (this.selectedIndex !== -1) {
                this.boxes.splice(this.selectedIndex, 1);
                this.selectedIndex = -1;
                this.updateDOM();
            }
        }

        updateDOM() {
            this.boxContainer.innerHTML = '';
            this.boxes.forEach((b, idx) => {
                const el = parent.document.createElement('div');
                const isSelected = (idx === this.selectedIndex);
                Object.assign(el.style, {
                    position: 'absolute', left: b.x + 'px', top: b.y + 'px',
                    width: b.w + 'px', height: b.h + 'px',
                    border: isSelected ? '2px solid #FF4B4B' : '2px solid rgba(255, 75, 75, 0.4)',
                    backgroundColor: isSelected ? 'rgba(255, 75, 75, 0.1)' : 'rgba(255, 75, 75, 0.05)',
                });
                this.boxContainer.appendChild(el);
            });

            if (this.selectedIndex !== -1) {
                const b = this.boxes[this.selectedIndex];
                const map = {
                    nw: [b.x, b.y], n: [b.x + b.w / 2, b.y], ne: [b.x + b.w, b.y],
                    e: [b.x + b.w, b.y + b.h / 2], se: [b.x + b.w, b.y + b.h],
                    s: [b.x + b.w / 2, b.y + b.h], sw: [b.x, b.y + b.h],
                    w: [b.x, b.y + b.h / 2]
                };

                this.handles.forEach(h => {
                    const pos = h.dataset.handle;
                    const coords = map[pos];
                    if (coords) {
                        h.style.left = coords[0] + 'px';
                        h.style.top = coords[1] + 'px';
                        h.style.display = 'block';
                    }
                });
                this.handleContainer.style.display = 'block';
            } else {
                this.handleContainer.style.display = 'none';
            }

            this.toolbar.style.display = this.boxes.length > 0 ? 'flex' : 'none';
        }

        onPointerDown(e) {
            // 🛡️ STRICT GESTURE GUARD
            const touchCount = e.pointerType === 'touch' ? window.activePointers.size : 0;
            if (window.isCanvasGesturing || touchCount > 1 || (Date.now() - window.lastPinchTime < 600)) {
                this.cancelDrawing();
                return;
            }

            this.overlay.setPointerCapture(e.pointerId);

            const rect = this.overlay.getBoundingClientRect();
            // 🔍 COORDINATE MAPPING (Visual -> Intrinsic)
            // rect.width is the ZOOMED visual width. CANVAS_WIDTH is validation.
            const scale = rect.width / CANVAS_WIDTH;
            const x = (e.clientX - rect.left) / scale;
            const y = (e.clientY - rect.top) / scale;

            // 1. Check Active Handles
            if (e.target.dataset.handle) {
                this.isMoving = false;
                this.isDrawing = false;
                this.activeHandle = e.target.dataset.handle;
                this.startBox = { ...this.boxes[this.selectedIndex] };
                this.startX = x; // Store intrinsic start
                this.startY = y;
                return;
            }

            // 2. Check Box Click (Move)
            for (let i = this.boxes.length - 1; i >= 0; i--) {
                const b = this.boxes[i];
                if (x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h) {
                    this.selectedIndex = i;
                    this.isMoving = true;
                    this.isDrawing = false;
                    this.activeHandle = null;
                    this.startX = x;
                    this.startY = y;
                    this.startBox = { ...b };
                    this.updateDOM();
                    return;
                }
            }

            // 3. New Box
            this.isDrawing = true;
            this.isMoving = false;
            this.activeHandle = null;
            this.startX = x;
            this.startY = y;
            const newBox = { x, y, w: 0, h: 0 };
            this.boxes.push(newBox);
            this.selectedIndex = this.boxes.length - 1;
            this.startBox = { ...newBox };
            this.updateDOM();
        }

        onPointerMove(e) {
            const touchCount = e.pointerType === 'touch' ? window.activePointers.size : 0;
            if (window.isCanvasGesturing || touchCount > 1) {
                this.cancelDrawing();
                return;
            }
            if (!this.isDrawing && !this.isMoving && !this.activeHandle) return;
            e.preventDefault();

            const rect = this.overlay.getBoundingClientRect();
            // 🔍 COORDINATE MAPPING
            const scale = rect.width / CANVAS_WIDTH;
            const x = (e.clientX - rect.left) / scale;
            const y = (e.clientY - rect.top) / scale;

            if (this.isDrawing) {
                const b = this.boxes[this.selectedIndex];
                const minX = Math.min(this.startX, x);
                const minY = Math.min(this.startY, y);
                const w = Math.abs(x - this.startX);
                const h = Math.abs(y - this.startY);
                // Clamp
                b.x = Math.max(0, minX);
                b.y = Math.max(0, minY);
                b.w = Math.min(w, CANVAS_WIDTH - b.x); // Clamp to Intrinsic Size
                b.h = Math.min(h, CANVAS_HEIGHT - b.y);
            }
            else if (this.isMoving) {
                const dx = x - this.startX;
                const dy = y - this.startY;
                const b = this.boxes[this.selectedIndex];
                const sb = this.startBox;
                let nx = sb.x + dx;
                let ny = sb.y + dy;
                // Clamp
                nx = Math.max(0, Math.min(nx, CANVAS_WIDTH - sb.w));
                ny = Math.max(0, Math.min(ny, CANVAS_HEIGHT - sb.h));
                b.x = nx; b.y = ny;
            }
            else if (this.activeHandle) {
                const dx = x - this.startX;
                const dy = y - this.startY;
                const b = this.boxes[this.selectedIndex];
                const sb = this.startBox;
                let nx = sb.x, ny = sb.y, nw = sb.w, nh = sb.h;

                if (this.activeHandle.includes('e')) nw = sb.w + dx;
                if (this.activeHandle.includes('s')) nh = sb.h + dy;
                if (this.activeHandle.includes('w')) { nw = sb.w - dx; nx = sb.x + dx; }
                if (this.activeHandle.includes('n')) { nh = sb.h - dy; ny = sb.y + dy; }

                if (nw < 20) { if (this.activeHandle.includes('w')) nx = sb.x + sb.w - 20; nw = 20; }
                if (nh < 20) { if (this.activeHandle.includes('n')) ny = sb.y + sb.h - 20; nh = 20; }

                b.x = nx; b.y = ny; b.w = nw; b.h = nh;
            }
            requestAnimationFrame(() => this.updateDOM());
        }

        cancelDrawing() {
            if (this.isDrawing) {
                this.boxes.pop();
                this.isDrawing = false;
                this.selectedIndex = -1;
                this.updateDOM();
            }
            this.isMoving = false;
            this.activeHandle = null;
        }

        onPointerUp(e) {
            this.overlay.releasePointerCapture(e.pointerId);
            this.isDrawing = false;
            this.isMoving = false;
            this.activeHandle = null;

            if (this.selectedIndex !== -1) {
                const b = this.boxes[this.selectedIndex];
                // Remove if too small (accidental tap)
                if (b.w < 10 || b.h < 10) {
                    this.boxes.splice(this.selectedIndex, 1);
                    this.selectedIndex = -1;
                }
            }
            this.updateDOM();
        }

        commit() {
            if (this.boxes.length === 0) return;
            // Coords are already intrinsic. No scale needed (or scale=1).
            const parts = this.boxes.map(b => {
                const cx1 = Math.round(b.x);
                const cy1 = Math.round(b.y);
                const cx2 = Math.round(b.x + b.w);
                const cy2 = Math.round(b.y + b.h);
                return `${cx1},${cy1},${cx2},${cy2}`;
            });
            const val = parts.join('|') + ',' + Date.now();
            const url = new URL(parent.location.href);
            url.searchParams.set('box', val);
            url.searchParams.delete('tap'); url.searchParams.delete('poly_pts');
            throttledReplaceState(url);
            this.boxes = [];
            this.selectedIndex = -1;
            this.updateDOM();
            setTimeout(() => triggerRerun(), 500);
        }
    }

    function applyResponsiveScale() {
        // NOTE: We deliberately do NOT skip when isCanvasGesturing — the pinch
        // handler calls _scheduleFrame() which calls us, so we MUST run during
        // a gesture to see smooth zooming.  isCanvasGesturing is only used by
        // editors to block accidental single-tap draws.
        try {
            const iframes = parent.document.getElementsByTagName('iframe');
            if (!iframes.length) return;

            let winW = parent.window.innerWidth || parent.document.documentElement.clientWidth;
            let winH = parent.window.innerHeight || parent.document.documentElement.clientHeight;

            if (parent.window.visualViewport) {
                winW = parent.window.visualViewport.width;
                winH = parent.window.visualViewport.height;
            }

            // ── IMPROVED: Use actual Streamlit main container width ──────────
            // parent.window.innerWidth includes the sidebar, giving wrong results
            // on Streamlit Cloud where sidebar proportions differ from Local.
            // Measure the real available area from the block-container element.
            let availableW = winW;  // fallback
            try {
                const mainBlock = parent.document.querySelector('.main .block-container');
                if (mainBlock) {
                    const rect = mainBlock.getBoundingClientRect();
                    if (rect.width > 200) {
                        availableW = Math.floor(rect.width);
                    }
                }
            } catch (e) { }

            // BASE Scale Calculation
            // CANVAS_WIDTH comes from cfg injected by Python (accurate, dynamic)
            const CW = (window.CANVAS_CONFIG || {}).CANVAS_WIDTH || CANVAS_WIDTH;
            const CH = (window.CANVAS_CONFIG || {}).CANVAS_HEIGHT || CANVAS_HEIGHT;

            let baseScale;
            if (winW < 1024) {
                // Mobile: Fit to available width (minus small margin)
                const targetWidth = availableW - 4;
                baseScale = targetWidth / CW;
            } else {
                // Desktop: Fit the canvas within the actual container, not full window
                // Cap at CANVAS_WIDTH (never upscale beyond 1:1)
                const maxW = Math.min(availableW - 16, CW);  // 16px breathing room
                const maxH = winH - 120; // Reserve header/footer space

                const scaleW = maxW / CW;
                const scaleH = maxH / CH;

                // Never scale UP beyond 1.0 (no upscaling — preserves coordinate accuracy)
                baseScale = Math.min(scaleW, scaleH, 1.0);
            }

            if (baseScale < 0.1) baseScale = 0.1;

            // Expose so pinch handler can use the same value consistently
            window._currentBaseScale = baseScale;

            // Combined Scale
            let userZoom = window.userZoomLevel || 1.0;
            let totalScale = baseScale * userZoom;

            // Clamping Calculation
            // We want to restrict the translation so that the edges of the scaled image 
            // do not go "inside" the viewport edges (avoiding white space).
            // This is only possible if the image is larger than the viewport (userZoom > 1).
            // If userZoom <= 1, we force pan to 0 (center).

            let px = window.panX || 0;
            let py = window.panY || 0;

            if (userZoom <= 1.0) {
                px = 0;
                py = 0;
            } else {
                // Determine the visual size difference
                // visual_w = CANVAS_WIDTH * totalScale
                // wrapper_w = CANVAS_WIDTH * baseScale
                // limit = (visual_w - wrapper_w) / 2
                // But px is in "unscaled pixels" ?? No, px is applied in the transform *before* scale? 
                // Wait, transform logic below is: translate(${px}px) scale(${totalScale})
                // No, it's: translate(-50%, -50%) translate(${px}px, ${py}px) scale(${totalScale});
                // The order matters. translate(px) is applied *before* scale?
                // The standard is transform: translate(px) scale(...) -> px is in unscaled units if applied before?
                // Actually translate(...) happens in the local coordinate system of the element.
                // But the element has width=CANVAS_WIDTH.
                // So px is in intrinsic CANVAS coordinates.

                // Let's re-verify the math.
                // Center is (0,0) due to translate(-50%, -50%).
                // If we translate by dx, the visual center moves by dx * scale?
                // If I have translate(100px) scale(2), the visual shift is 200px?
                // CSS Spec: transform functions are multiplied.
                // matrix = translate(-50%, -50%) * translate(px, py) * scale(s)
                // NO, they are applied right-to-left mathematically, or left-to-right visually?
                // "The transformation functions are applied in the order they are written."

                // 1. translate(-50%, -50%): Moves the element so its top-left is at -50% width/height. 
                //    Effectively centering the element (since it's positioned at top:50%, left:50%).
                //    Coordinate system is now centered at the element center.

                // 2. translate(px, py): Moves the element by px, py in its current coordinate system.
                //    Coordinate system is intrinsic (CANVAS coordinates).

                // 3. scale(totalScale): Scales the result.

                // result_visual_pos = (pos + pan) * scale

                // So if we pan by 1 pixel in intrinsic coords, it moves by 'totalScale' pixels on screen.

                // The container size in visual pixels is: wrapper_w = CANVAS_WIDTH * baseScale.
                // The image size in visual pixels is: visual_w = CANVAS_WIDTH * totalScale.

                // Allowed visual overflow = (visual_w - wrapper_w) / 2.
                // Allowed intrinsic pan = (Allowed visual overflow) / totalScale.
                //                       = ( (CANVAS_WIDTH * totalScale) - (CANVAS_WIDTH * baseScale) ) / (2 * totalScale)
                //                       = ( CANVAS_WIDTH * (totalScale - baseScale) ) / (2 * totalScale)
                //                       = ( CANVAS_WIDTH * baseScale * (userZoom - 1) ) / (2 * baseScale * userZoom)
                //                       = ( CANVAS_WIDTH * (userZoom - 1) ) / (2 * userZoom)

                const limitX = (CANVAS_WIDTH * (userZoom - 1)) / (2 * userZoom);
                const limitY = (CANVAS_HEIGHT * (userZoom - 1)) / (2 * userZoom);

                px = Math.max(-limitX, Math.min(limitX, px));
                py = Math.max(-limitY, Math.min(limitY, py));
            }

            // Re-save clamped values to state so it doesn't drift
            window.panX = px;
            window.panY = py;

            for (let iframe of iframes) {
                if (iframe.title === "streamlit_drawable_canvas.st_canvas" || iframe.src.includes('streamlit_drawable_canvas')) {
                    const wrapper = iframe.parentElement;
                    if (!wrapper) continue;

                    // Wrapper Style (User Requirement: Fixed Container)
                    wrapper.className = "zoom-container"; // match user request class conceptually
                    wrapper.style.cssText = `
                        width: ${Math.floor(CANVAS_WIDTH * baseScale)}px;
                        height: ${Math.floor(CANVAS_HEIGHT * baseScale)}px;
                        position: relative;
                        margin: 0 auto !important;
                        display: block !important;
                        overflow: hidden; 
                        touch-action: none; /* 1️⃣ Requirement */
                        user-select: none;
                        -webkit-user-select: none;
                    `;

                    // Shared Transform Style for Iframe AND Overlay
                    const transformStyle = `
                        width: ${CANVAS_WIDTH}px;
                        height: ${CANVAS_HEIGHT}px;
                        position: absolute;
                        top: 50%; 
                        left: 50%;
                        transform-origin: center center; 
                        transform: translate(-50%, -50%) translate(${px}px, ${py}px) scale(${totalScale});
                        will-change: transform;
                        touch-action: none;
                        opacity: 1;
                        border: none;
                    `;

                    iframe.style.cssText = transformStyle;

                    // 🛠️ APPLY TO OVERLAY TOO
                    const overlay = wrapper.querySelector('[id$="-overlay"]');
                    if (overlay) {
                        // Keep base overlay styles but override transform/size
                        overlay.style.cssText = `
                             ${transformStyle}
                             display: block; 
                             z-index: 999;
                             cursor: crosshair;
                             overflow: visible;
                         `;
                        // Ensure overlay has correct ID style for touch
                        overlay.style.touchAction = 'none';
                    }
                }
            }
        } catch (e) { }
    }
    // 🌐 Expose so external scripts (zoom buttons, reset) can call it
    window.applyResponsiveScale = applyResponsiveScale;

    class PolygonEditor extends BaseEditor {
        constructor() {
            super('poly-editor');
            this.points = []; // Array of {x, y}
            this.isClosed = false;

            this.svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
            this.svg.style.cssText = "position:absolute; top:0; left:0; width:100%; height:100%; pointer-events:none;";
            this.overlay.appendChild(this.svg);

            this.createToolbar();
            this.bindEvents();
        }

        createToolbar() {
            const btnUndo = parent.document.createElement('button');
            btnUndo.innerHTML = "↩️ Undo";
            btnUndo.style.cssText = btnBase + "color: #333;";
            btnUndo.onclick = (e) => { e.preventDefault(); this.undo(); };

            const btnApply = parent.document.createElement('button');
            btnApply.innerHTML = "✅ Apply Paint";
            btnApply.style.cssText = btnBase + "border-color: #10B981; color: #10B981; background: #F0FDF4;";
            btnApply.onclick = (e) => { e.preventDefault(); this.commit(); };

            this.toolbar.appendChild(btnUndo);
            this.toolbar.appendChild(btnApply);
        }

        bindEvents() {
            trackPointer(this.overlay);
            // Use pointer events for unified mouse/touch
            this.overlay.onpointerdown = this.onPointerDown.bind(this);
            this.overlay.onpointermove = this.onPointerMove.bind(this);
            this.overlay.onpointerup = this.onPointerUp.bind(this);
            this.overlay.onpointercancel = (e) => this.onPointerUp(e); // Reset on scroll
            // Double click to close
            this.overlay.ondblclick = this.onDoubleClick.bind(this);
        }

        checkMode() {
            let mode = window.CANVAS_CONFIG?.DRAWING_MODE || 'point';
            this.mode = mode; // Store mode

            if (mode === 'polygon') {
                if (!this.mount()) return;
                this.show();
                this.render();
            } else {
                this.hide();
                this.points = [];
                this.isClosed = false;
            }
        }

        onPointerDown(e) {
            const touchCount = e.pointerType === 'touch' ? window.activePointers.size : 0;
            if (window.isCanvasGesturing || touchCount > 1 || (Date.now() - (window.lastPinchTime || 0) < 600)) return;
            e.stopPropagation();

            if (this.isClosed) return;

            const rect = this.overlay.getBoundingClientRect();
            // 🔍 COORDINATE MAPPING
            const scale = rect.width / CANVAS_WIDTH;
            const x = (e.clientX - rect.left) / scale;
            const y = (e.clientY - rect.top) / scale;

            if (this.mode === 'freedraw') {
                this.points = [{ x, y }];
                this.isDrawing = true;
                this.render();
            } else {
                if (this.points.length > 2) {
                    const start = this.points[0];
                    const dx = x - start.x;
                    const dy = y - start.y;
                    if (Math.sqrt(dx * dx + dy * dy) < 20) { // 20px intrinsic tolerance
                        this.closePolygon();
                        return;
                    }
                }
                this.points.push({ x, y });
                this.render();
            }
        }

        onPointerMove(e) {
            if (this.mode === 'freedraw' && this.isDrawing) {
                const rect = this.overlay.getBoundingClientRect();
                const scale = rect.width / CANVAS_WIDTH;
                const x = (e.clientX - rect.left) / scale;
                const y = (e.clientY - rect.top) / scale;

                const last = this.points[this.points.length - 1];
                const dx = x - last.x;
                const dy = y - last.y;
                if (dx * dx + dy * dy > 5) { // 5px tolerance implicit
                    this.points.push({ x, y });
                    this.render();
                }
            }
        }

        onPointerUp(e) {
            if (this.mode === 'freedraw' && this.isDrawing) {
                this.isDrawing = false;
                // Revert instant commit. User must double click or click "Apply"
                if (this.points.length > 2) {
                    this.closePolygon();
                } else {
                    this.points = [];
                    this.render();
                }
            }
        }

        onDoubleClick(e) {
            e.preventDefault();
            if (this.points.length > 2) {
                this.closePolygon();
            }
        }

        undo() {
            if (this.isClosed) {
                this.isClosed = false;
            } else {
                this.points.pop();
            }
            this.render();
        }

        closePolygon() {
            this.isClosed = true;
            this.render();
        }

        render() {
            while (this.svg.firstChild) this.svg.removeChild(this.svg.firstChild);

            if (this.points.length === 0) {
                this.toolbar.style.display = 'none';
                return;
            }

            // Draw Path
            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            let d = `M ${this.points[0].x} ${this.points[0].y}`;
            for (let i = 1; i < this.points.length; i++) {
                d += ` L ${this.points[i].x} ${this.points[i].y}`;
            }
            if (this.isClosed) d += " Z";

            path.setAttribute("d", d);
            path.setAttribute("stroke", "#00FFFF");
            path.setAttribute("stroke-width", "3");
            path.setAttribute("fill", this.isClosed ? "rgba(0, 255, 255, 0.3)" : "none");
            path.setAttribute("stroke-linejoin", "round");
            this.svg.appendChild(path);

            // Draw Vertices (ONLY for Polygon mode, HIDE for Freehand to avoid "dot" confusion)
            if (this.mode !== 'freedraw') {
                this.points.forEach((p, i) => {
                    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
                    c.setAttribute("cx", p.x);
                    c.setAttribute("cy", p.y);
                    c.setAttribute("r", "5");
                    c.setAttribute("fill", i === 0 ? "#FF4B4B" : "white");
                    c.setAttribute("stroke", "#333");
                    this.svg.appendChild(c);
                });
            }

            if (this.points.length > 0) {
                this.toolbar.style.display = 'flex';
                const applyBtn = this.toolbar.querySelector('button:last-child');
                applyBtn.style.opacity = this.isClosed ? '1' : '0.5';
                applyBtn.style.pointerEvents = this.isClosed ? 'auto' : 'none';
            }
        }

        commit() {
            if (!this.isClosed || this.points.length < 3) return;
            // Coords are already intrinsic.
            const ptsStr = this.points.map(p => {
                return `${Math.round(p.x)},${Math.round(p.y)}`;
            }).join(';');

            const val = ptsStr + ',' + Date.now();
            const url = new URL(parent.location.href);
            url.searchParams.set('poly_pts', val);
            url.searchParams.delete('tap'); url.searchParams.delete('box');
            throttledReplaceState(url);

            this.points = [];
            this.isClosed = false;
            this.render();
            setTimeout(() => triggerRerun(), 500);
        }
    }

    class PointEditor extends BaseEditor {
        constructor() {
            super('point-editor');
            this.lastTapTime = 0;
            this.bindEvents();
        }

        bindEvents() {
            trackPointer(this.overlay);
            this.overlay.onpointerdown = this.onPointerDown.bind(this);
            this.overlay.onpointerup = this.onPointerUp.bind(this);
            this.overlay.onpointercancel = (e) => { this.potentialX = null; };
        }

        checkMode() {
            let mode = window.CANVAS_CONFIG?.DRAWING_MODE || 'point';
            if (mode === 'point') {
                if (this.mount()) {
                    this.show();
                }
            } else {
                this.hide();
            }
        }

        onPointerDown(e) {
            // 🛡️ STRICT GESTURE GUARD
            const touchCount = e.pointerType === 'touch' ? window.activePointers.size : 0;
            if (window.isCanvasGesturing || touchCount > 1 || (Date.now() - window.lastPinchTime < 600)) {
                this.potentialX = null;
                return;
            }

            this.overlay.setPointerCapture(e.pointerId);
            this.potentialX = e.clientX;
            this.potentialY = e.clientY;
            this.potentialTime = Date.now();
        }

        onPointerUp(e) {
            if (!this.potentialX || window.isCanvasGesturing || window.activePointers.size > 0) {
                this.potentialX = null;
                return;
            }

            const now = Date.now();
            if (now - this.potentialTime > 500) return; // Not a tap

            const rect = this.overlay.getBoundingClientRect();
            const scale = (window.CANVAS_CONFIG?.CANVAS_WIDTH || 800) / rect.width;

            const x = Math.round((this.potentialX - rect.left) * scale);
            const y = Math.round((this.potentialY - rect.top) * scale);

            console.log(`JS: Point tap at (${x}, ${y})`);

            // Set URL parameter for Streamlit backend
            const url = new URL(parent.location.href);
            url.searchParams.set('tap', `${x},${y},${now}`);
            url.searchParams.delete('box');
            url.searchParams.delete('poly_pts');

            // Trigger rerun
            if (throttledReplaceState(url)) {
                triggerRerun();
            }
            this.potentialX = null;
        }
    }

    class MultiTouchHandler {
        constructor() {
            this.reset();
        }

        reset() {
            this.isGesturing = false;
            this.initialDist = 0;
            this.initialZoom = 1.0;
            this.initialPan = { x: 0.5, y: 0.5 };
            this.initialMid = { x: 0, y: 0 };
            this.currentTransform = { dx: 0, dy: 0, scale: 1 };
            window.isCanvasGesturing = false;
        }

        attach(el) {
            // Passive: false is crucial for preventDefault to stop browser zoom
            el.addEventListener('touchstart', (e) => {
                if (e.touches.length === 2) {
                    e.preventDefault();
                    this.isGesturing = true;
                    window.isCanvasGesturing = true;
                    window.lastPinchDist = Math.hypot(e.touches[1].clientX - e.touches[0].clientX, e.touches[1].clientY - e.touches[0].clientY);
                    window.lastPinchCenter = { x: (e.touches[0].clientX + e.touches[1].clientX) / 2, y: (e.touches[0].clientY + e.touches[1].clientY) / 2 };

                    const t1 = e.touches[0], t2 = e.touches[1];
                    // 📏 Use clientX/Y to match getBoundingClientRect (Viewport coords)
                    this.initialDist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
                    this.initialMid = { x: (t1.clientX + t2.clientX) / 2, y: (t1.clientY + t2.clientY) / 2 };

                    const config = window.CANVAS_CONFIG || {};
                    this.initialZoom = parseFloat(config.ZOOM_LEVEL) || 1.0;
                    this.initialPan = {
                        x: parseFloat(config.CUR_PAN_X) || 0.5,
                        y: parseFloat(config.CUR_PAN_Y) || 0.5
                    };

                    const iframe = getActiveIframe();
                    if (iframe) {
                        iframe.style.transition = 'none';
                        const rect = el.getBoundingClientRect();
                        // origin is relative to the element (0-100%)
                        const ox = ((this.initialMid.x - rect.left) / (rect.width || 1)) * 100;
                        const oy = ((this.initialMid.y - rect.top) / (rect.height || 1)) * 100;
                        iframe.style.transformOrigin = `${ox}% ${oy}%`;
                        iframe.style.opacity = '0.9';
                    }
                }
            }, { passive: false });

            el.addEventListener('touchmove', (e) => {
                if (this.isGesturing && e.touches.length === 2) {
                    e.preventDefault();
                    const t1 = e.touches[0], t2 = e.touches[1];
                    const dist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
                    const mid = { x: (t1.clientX + t2.clientX) / 2, y: (t1.clientY + t2.clientY) / 2 };

                    // 1. Calculate relative zoom with safety clamp
                    let gestureScale = this.initialDist > 10 ? dist / this.initialDist : 1.0;

                    const minPossibleScale = 1.0 / (this.initialZoom || 1.0);
                    if (gestureScale < minPossibleScale) gestureScale = minPossibleScale;

                    // 2. Calculate translation deltas in viewport space
                    const dx = mid.x - this.initialMid.x;
                    const dy = mid.y - this.initialMid.y;

                    this.currentTransform = { dx, dy, scale: gestureScale };

                    // 3. Visual Preview (Instant)
                    const iframe = getActiveIframe();
                    if (iframe) {
                        const winW = parent.window.innerWidth;
                        const baseScale = Math.min(1.0, (winW - 10) / CANVAS_WIDTH);

                        // Apply movement and scale relative to pinch center
                        // Clamped scale ensures we stay at least at 'baseScale' size
                        const visualScale = baseScale * gestureScale;
                        iframe.style.transform = `translate(${dx}px, ${dy}px) scale(${visualScale})`;
                    }
                }
            }, { passive: false });

            const finish = () => {
                if (this.isGesturing) {
                    const { dx, dy, scale } = this.currentTransform;
                    const iframe = getActiveIframe();
                    if (iframe) iframe.style.opacity = '1.0';

                    const rect = el.getBoundingClientRect();

                    // 1. Calculate the final zoom level
                    const finalZ = Math.max(1.0, Math.min(4.0, this.initialZoom * scale));

                    if (finalZ <= 1.001) {
                        this.sync(1.0, 0.5, 0.5);
                    } else {
                        // 2. Focal Point Math:
                        // Normalized focal point on screen (where we started pinching)
                        const fx = (this.initialMid.x - rect.left) / rect.width;
                        const fy = (this.initialMid.y - rect.top) / rect.height;

                        // Delta move in screen fractions
                        const dfx = dx / rect.width;
                        const dfy = dy / rect.height;

                        // Calculate where the initial focal point was on the image
                        // Img_Pos = Pan * (1 - 1/Z) + fx/Z
                        const imgFX = this.initialPan.x * (1 - 1 / this.initialZoom) + fx / this.initialZoom;
                        const imgFY = this.initialPan.y * (1 - 1 / this.initialZoom) + fy / this.initialZoom;

                        // Calculate the new Pan such that imgFX is at (fx + dfx) in the new view
                        // Pan2 = [ imgPOS - (fx + dfx)/Z2 ] / (1 - 1/Z2)
                        const span2 = 1.0 / finalZ;
                        const finalX = Math.max(0, Math.min(1, (imgFX - (fx + dfx) * span2) / (1 - span2)));
                        const finalY = Math.max(0, Math.min(1, (imgFY - (fy + dfy) * span2) / (1 - span2)));

                        this.sync(finalZ, finalX, finalY);
                    }

                    this.reset();
                    window.lastPinchTime = Date.now();
                }
            };

            el.addEventListener('touchend', finish);
            el.addEventListener('touchcancel', finish);
        }

        sync(z, px, py) {
            const url = new URL(parent.location.href);
            url.searchParams.set('zoom_update', z.toFixed(2));
            url.searchParams.set('pan_update', `${px.toFixed(3)},${py.toFixed(3)},${Date.now()}`);
            if (throttledReplaceState(url)) {
                triggerRerun();
            }
        }
    }

    let boxEditor = new BoxEditor();
    let polyEditor = new PolygonEditor();
    let pointEditor = new PointEditor();
    let multiTouch = new MultiTouchHandler();

    function mainLoop() {
        applyResponsiveScale();
        const editors = [boxEditor, polyEditor, pointEditor];
        editors.forEach(ed => {
            ed.checkMode();
            if (ed.overlay && !ed.overlay._gestureAttached) {
                // multiTouch.attach(ed.overlay); // 🛑 DISABLED: Using Global handlePinch for smooth Client-Side Zoom
                ed.overlay._gestureAttached = true;
            }
        });
    }

    // Start
    window.addEventListener("resize", mainLoop);
    setInterval(mainLoop, 500);
    mainLoop();
})();
