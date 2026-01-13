/* admin/js/appointment_edit.js */
/* Мастер не может менять поле master и редактировать чужие позиции.
   Чужие строки — read-only; новые строки мастера — автоподстановка своего master. */

;(() => {
    const CTX = window.APPOINTMENT_CTX || { is_master: false, current_master_id: null };
    const IS_MASTER = !!CTX.is_master;
    const MY_ID = CTX.current_master_id != null ? String(CTX.current_master_id) : null;

    // безопасный разбор JSON-скриптов
    const parseJSON = (id, fallback) => {
        const el = document.getElementById(id);
        if (!el) return fallback;
        try { return JSON.parse(el.textContent || ""); } catch { return fallback; }
    };
    const MASTERS = parseJSON("masters-data", []);
    const MS_MAP = parseJSON("ms-map-data", {}); // { master_id: [ {id,name,base_price,svc_disc}, ... ] }
    const PROMO_BY_SERVICE = parseJSON("promos-by-service-data", {}); // { service_id: [ {id,text,discount}, ... ] }
    const PROMO_GLOBAL = parseJSON("promos-global-data", []);        // [ {id,text,discount}, ... ]
    const AVAILABILITY_URL = parseJSON("availability-url", "");
    const GST_PERCENT = Number(parseJSON("gst-percent", "5.0")) || 5;
    const GST_ENABLED = Boolean(parseJSON("gst-enabled", true));
    const CURRENCY_CODE = String(parseJSON("currency-code", "CAD") || "CAD").toLowerCase();
    const CURRENCY_SYMBOL = ((code) => {
        switch (code) {
            case "cad":
                return "CA$";
            case "usd":
                return "$";
            default:
                return code ? code.toUpperCase() + " " : "CA$";
        }
    })(CURRENCY_CODE);

    const $ = (sel, root = document) => root.querySelector(sel);
    const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
    window.APPOINTMENT_TOASTS = window.APPOINTMENT_TOASTS || [];

    const TOAST_LEVEL_CLASS = {
        error: "ab-toast--error",
        warning: "ab-toast--warning",
        success: "ab-toast--success",
        info: "",
    };

    function initToastSystem() {
        if (initToastSystem._initialized) {
            return;
        }
        const stack = document.querySelector("[data-toast-stack]");
        if (!stack) {
            return;
        }
        initToastSystem._initialized = true;

        const normalizeLevel = (value) => {
            const raw = (value || "").toString().trim();
            if (!raw) return "info";
            return raw.split(/\s+/)[0].toLowerCase();
        };

        const showToast = (message, level = "info", options = {}) => {
            if (!message) return null;
            const toast = document.createElement("div");
            toast.className = "ab-toast";
            const normalized = normalizeLevel(level);
            const levelClass = TOAST_LEVEL_CLASS[normalized];
            if (levelClass) {
                toast.classList.add(levelClass);
            }

            const textEl = document.createElement("div");
            textEl.className = "ab-toast__text";
            textEl.textContent = message;
            toast.appendChild(textEl);

            const closeBtn = document.createElement("button");
            closeBtn.type = "button";
            closeBtn.className = "ab-toast__close";
            closeBtn.setAttribute("aria-label", "Dismiss notification");
            closeBtn.textContent = "×";
            toast.appendChild(closeBtn);

            let autoHideId = null;
            const dismiss = () => {
                if (!toast.parentNode) return;
                toast.parentNode.removeChild(toast);
            };

            closeBtn.addEventListener("click", () => {
                if (autoHideId) {
                    window.clearTimeout(autoHideId);
                }
                dismiss();
            });

            stack.appendChild(toast);

            const requestedDuration = Number(options.duration);
            const duration = Number.isFinite(requestedDuration) ? requestedDuration : 6500;
            if (duration > 0) {
                autoHideId = window.setTimeout(dismiss, duration);
            }

            return toast;
        };

        window.showToast = showToast;

        if (Array.isArray(window.APPOINTMENT_TOASTS)) {
            window.APPOINTMENT_TOASTS.forEach((item) => {
                if (!item || !item.text) return;
                showToast(item.text, item.level || "info", item.options || {});
            });
            window.APPOINTMENT_TOASTS = [];
        }
    }

    const itemsContainer = $("#items-container");
    const salesContainer = document.getElementById("product-sales-container");
    const SALES_PREFIX = "product_sales";
    const SALE_DEFAULTS = parseJSON("product-sale-defaults", {});
    const appointmentClientSelect = document.getElementById("id_client");
    if (!itemsContainer) return;
    const subtotalDisplay = document.getElementById("appt-subtotal");
    const taxDisplay = document.getElementById("appt-tax");
    const totalDisplay = document.getElementById("appt-total");
    const taxRowDisplay = document.getElementById("appt-tax-row");
    const gstLabelDisplay = document.getElementById("gst-label");
    const feeDisplay = document.getElementById("appt-fee");
    const feeRowDisplay = document.getElementById("appt-fee-row");
    const CARD_FEE_PERCENT = Number(parseJSON("card-fee-percent", "0"));
    const CARD_FEE_FIXED = Number(parseJSON("card-fee-fixed", "0"));
    let cardFeeApplied = false;
    function initialFeeAppliedState() {
        const payButton = document.getElementById("pay-btn");
        if (payButton && typeof payButton.dataset.feeApplied !== "undefined") {
            return payButton.dataset.feeApplied === "true";
        }
        const cfg = window.APPOINTMENT_PAY || {};
        if (typeof cfg.feeApplied !== "undefined") {
            return !!cfg.feeApplied;
        }
        return false;
    }
    if (taxRowDisplay && !GST_ENABLED) {
        taxRowDisplay.classList.add("ab-hidden");
    }

    function buildOption(value, text) {
        const o = document.createElement("option");
        o.value = String(value);
        o.textContent = String(text);
        return o;
    }
    function mirrorOptions(dstSelect, srcSelect) {
        if (!dstSelect || !srcSelect) return;
        dstSelect.innerHTML = "";
        Array.from(srcSelect.options).forEach(o => {
            const opt = document.createElement("option");
            opt.value = String(o.value);
            opt.textContent = o.textContent;
            dstSelect.appendChild(opt);
        });
    }
    function setSelectValueEnsuringOption(select, value, labelIfAdd) {
        if (!select) return;
        const val = String(value ?? "");
        if (!val) { select.value = ""; return; }
        let has = Array.from(select.options).some(o => o.value === val);
        if (!has) {
            const opt = document.createElement("option");
            opt.value = val;
            opt.textContent = String(labelIfAdd ?? val);
            opt.selected = true;
            select.appendChild(opt);
        } else {
            Array.from(select.options).forEach(o => {
                o.selected = (o.value === val);
            });
        }
        select.value = val;
    }
    function ensureUiOption(selectEl, value, label) {
        if (!selectEl) return;
        const val = String(value ?? "");
        if (!val) return;
        const exists = Array.from(selectEl.options).some(o => o.value === val);
        if (!exists) {
            const opt = document.createElement("option");
            opt.value = val;
            opt.textContent = label || val;
            selectEl.appendChild(opt);
        }
    }
    function roundCurrency(value) {
        return Math.round((Number(value) || 0) * 100) / 100;
    }
    function formatPercent(value) {
        const num = Number(value);
        if (!Number.isFinite(num)) {
            return "";
        }
        const fixed = num % 1 === 0 ? num.toFixed(0) : num.toFixed(2);
        return fixed.replace(/\.0+$/, "").replace(/0+$/, "").replace(/\.$/, "");
    }
    function money(value) {
        const amount = Number(value || 0);
        return `${CURRENCY_SYMBOL}${amount.toFixed(2)}`;
    }
    function moneySigned(value) {
        const numeric = Number(value || 0);
        if (Math.abs(numeric) < 0.005) {
            return money(0);
        }
        const sign = numeric < 0 ? "-" : "";
        return `${sign}${money(Math.abs(numeric))}`;
    }

    function formatSlotLabel(dateObj) {
        const h = String(dateObj.getHours()).padStart(2, "0");
        const m = String(dateObj.getMinutes()).padStart(2, "0");
        return `${h}:${m}`;
    }

    function parseIsoSlot(iso) {
        if (!iso) return null;
        const dt = new Date(iso);
        return Number.isNaN(dt.getTime()) ? null : dt;
    }

    function normalizeTimeLabel(value) {
        const raw = (value ?? "").trim();
        if (!raw) return "";
        return raw.length > 5 ? raw.slice(0, 5) : raw;
    }

    function isoFromDateAndTime(dateStr, timeStr) {
        const label = normalizeTimeLabel(timeStr);
        if (!dateStr || !label) return null;
        const candidate = new Date(`${dateStr}T${label}`);
        if (Number.isNaN(candidate.getTime())) return null;
        return candidate.toISOString();
    }

    function availabilityUrlFor(serviceId, masterId, dateStr) {
        if (!AVAILABILITY_URL) return null;
        const params = new URLSearchParams({ service: serviceId || "", date: dateStr || "" });
        if (masterId) params.append("master", masterId);
        const divider = AVAILABILITY_URL.includes("?") ? "&" : "?";
        return `${AVAILABILITY_URL}${divider}${params.toString()}`;
    }

    function fetchAvailability(serviceId, masterId, dateStr) {
        const url = availabilityUrlFor(serviceId, masterId, dateStr);
        if (!url) {
            return Promise.reject(new Error("Availability endpoint is not configured."));
        }
        return fetch(url, { credentials: "same-origin" }).then(resp => {
            if (!resp.ok) {
                throw new Error(`Availability request failed with status ${resp.status}`);
            }
            return resp.json();
        });
    }

    function initTimeslotPickerForRow({ row, masterEl, serviceEl, dateEl, timeEl, validationToggle }) {
        if (!row || !dateEl || !timeEl) return null;
        const wrap = row.querySelector(".js-timeslots-wrap");
        const statusEl = row.querySelector(".js-timeslots-status");
        const grid = row.querySelector(".js-timeslots-grid");
        if (!wrap || !statusEl || !grid) return null;

        const defaultMessage = "Select master, service and date to view availability.";
        let activeBtn = null;
        let requestSeq = 0;

        function setStatus(state, message) {
            wrap.dataset.state = state;
            statusEl.textContent = message || defaultMessage;
        }

        function activateButton(btn) {
            if (activeBtn && activeBtn !== btn) {
                activeBtn.classList.remove("is-selected");
                activeBtn.setAttribute("aria-selected", "false");
            }
            activeBtn = btn || null;
            if (activeBtn) {
                activeBtn.classList.add("is-selected");
                activeBtn.setAttribute("aria-selected", "true");
            }
        }

        function updateInput(value, iso, emit = true) {
            timeEl.value = value || "";
            if (iso) {
                timeEl.dataset.selectedIso = iso;
            } else {
                delete timeEl.dataset.selectedIso;
            }
            if (emit) {
                timeEl.dispatchEvent(new Event("input", { bubbles: true }));
                timeEl.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }

        function clearSelection({ emit = true } = {}) {
            activateButton(null);
            updateInput("", "", emit);
        }

        function highlightCurrent() {
            const val = normalizeTimeLabel(timeEl.value);
            if (!val) {
                activateButton(null);
                return null;
            }
            const btn = grid.querySelector(`[data-time="${val}"]`);
            if (!btn) {
                activateButton(null);
                return null;
            }
            activateButton(btn);
            return btn;
        }

        function missingInputsMessage() {
            const missing = [];
            if (serviceEl && !serviceEl.value) missing.push("service");
            if (masterEl && !masterEl.value) missing.push("master");
            if (!dateEl.value) missing.push("date");
            if (!missing.length) return null;
            if (missing.length === 1) {
                const target = missing[0];
                if (target === "service") return "Select a service to view availability.";
                if (target === "master") return "Select a master to view availability.";
                return "Select a date to view availability.";
            }
            return defaultMessage;
        }

        function buildSlotButton(slotIso, options = {}) {
            const dt = slotIso ? parseIsoSlot(slotIso) : null;
            const label = options.label || (dt ? formatSlotLabel(dt) : null);
            if (!label) return null;
            const isoValue = typeof slotIso === "string" && slotIso ? slotIso : (options.isoFallback || null);
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "ab-timeslots__btn";
            if (options.isCurrent) {
                btn.classList.add("ab-timeslots__btn--current");
                btn.dataset.current = "1";
            }
            if (isoValue) {
                btn.dataset.iso = isoValue;
            }
            btn.dataset.time = label;
            btn.setAttribute("role", "option");
            btn.setAttribute("aria-selected", "false");
            btn.textContent = options.text || label;
            if (options.tooltip) {
                btn.title = options.tooltip;
            }
            btn.addEventListener("click", () => {
                activateButton(btn);
                const nextIso = isoValue || (typeof options.buildIso === "function" ? options.buildIso(label) : null);
                updateInput(label, nextIso, true);
                setStatus("ready", options.selectMessage || `Selected ${label}`);
            });
            return btn;
        }

        function renderSlots(slots) {
            grid.innerHTML = "";
            const seenLabels = new Set();
            if (Array.isArray(slots)) {
                slots.forEach(iso => {
                    const btn = buildSlotButton(iso);
                    if (btn) {
                        seenLabels.add(btn.dataset.time);
                        grid.appendChild(btn);
                    }
                });
            }

            const currentLabel = normalizeTimeLabel(timeEl.value);
            const originalDate = row.dataset.originalDate || "";
            const originalTime = row.dataset.originalTime || "";
            const allowCurrentSlot = !!(
                row.dataset.itemId &&
                originalDate &&
                originalTime &&
                currentLabel &&
                dateEl.value === originalDate &&
                currentLabel === originalTime
            );
            if (allowCurrentSlot && !seenLabels.has(currentLabel)) {
                const fallbackIso = isoFromDateAndTime(dateEl.value, currentLabel);
                const currentBtn = buildSlotButton(fallbackIso, {
                    label: currentLabel,
                    isCurrent: true,
                    tooltip: "Current appointment time",
                    selectMessage: `Current slot ${currentLabel} is kept for this appointment.`,
                    buildIso: () => isoFromDateAndTime(dateEl.value, currentLabel),
                });
                if (currentBtn) {
                    grid.insertBefore(currentBtn, grid.firstChild);
                    seenLabels.add(currentLabel);
                }
            }

            const highlighted = highlightCurrent();
            const totalButtons = grid.querySelectorAll(".ab-timeslots__btn").length;

            if (highlighted) {
                if (highlighted.dataset.current === "1") {
                    const others = Math.max(0, totalButtons - 1);
                    if (others > 0) {
                        const plural = others === 1 ? "slot" : "slots";
                        setStatus("ready", `Current slot ${highlighted.dataset.time} is kept for this appointment. ${others} alternative ${plural} available.`);
                    } else {
                        setStatus("ready", `Current slot ${highlighted.dataset.time} is kept for this appointment.`);
                    }
                } else {
                    const label = highlighted.dataset.time || "";
                    const suffix = totalButtons > 1 ? ` · ${totalButtons - 1} more` : "";
                    setStatus("ready", `Selected ${label}${suffix}`);
                }
                return;
            }

            if (totalButtons > 0) {
                clearSelection({ emit: true });
                const info = totalButtons === 1 ? "1 available slot" : `${totalButtons} available slots`;
                setStatus("ready", info);
                return;
            }

            clearSelection({ emit: true });
            setStatus("empty", "No available slots for this date.");
        }

        function buildUnlockedSlots() {
            const dateStr = dateEl.value;
            if (!dateStr) return [];
            const base = new Date(`${dateStr}T00:00:00`);
            if (Number.isNaN(base.getTime())) return [];
            const slots = [];
            for (let minutes = 0; minutes < 24 * 60; minutes += 15) {
                const dt = new Date(base.getTime() + minutes * 60 * 1000);
                slots.push(dt.toISOString());
            }
            return slots;
        }

        function refresh(options = {}) {
            if (wrap.dataset.disabled === "1") return;
            const preserveSelection = !!options.preserveSelection;
            if (!preserveSelection) {
                clearSelection({ emit: true });
            }
            const bypassValidation = validationToggle && !validationToggle.checked;
            if (bypassValidation) {
                if (!dateEl.value) {
                    grid.innerHTML = "";
                    setStatus("idle", "Select a date to view all time slots.");
                    return;
                }
                const slots = buildUnlockedSlots();
                renderSlots(slots);
                setStatus("ready", "Validation disabled: all time slots available.");
                return;
            }
            const message = missingInputsMessage();
            if (message) {
                grid.innerHTML = "";
                setStatus("idle", message);
                return;
            }
            if (!AVAILABILITY_URL) {
                grid.innerHTML = "";
                setStatus("error", "Availability endpoint is not configured.");
                return;
            }

            const masterId = masterEl ? masterEl.value : "";
            const serviceId = serviceEl ? serviceEl.value : "";
            const dateStr = dateEl.value;
            const seq = ++requestSeq;
            setStatus("loading", "Loading available slots...");
            fetchAvailability(serviceId, masterId, dateStr)
                .then(payload => {
                    if (seq !== requestSeq) return;
                    const masters = payload && Array.isArray(payload.masters) ? payload.masters : [];
                    let slots = [];
                    if (masters.length) {
                        let entry = null;
                        if (masterId) {
                            entry = masters.find(m => String(m.id) === String(masterId)) || null;
                        }
                        if (!entry) {
                            entry = masters[0] || null;
                        }
                        if (entry && Array.isArray(entry.slots)) {
                            slots = entry.slots.slice();
                        }
                    }
                    if (!slots.length && payload && Array.isArray(payload.slots)) {
                        slots = payload.slots.slice();
                    }
                    renderSlots(slots);
                })
                .catch(err => {
                    if (seq !== requestSeq) return;
                    console.error("Unable to load availability", err);
                    setStatus("error", "Unable to load availability. Try again.");
                });
        }

        timeEl.addEventListener("change", highlightCurrent);
        timeEl.addEventListener("input", highlightCurrent);

        if (!AVAILABILITY_URL) {
            setStatus("error", "Availability endpoint is not configured.");
        } else {
            const initial = missingInputsMessage();
            setStatus("idle", initial || defaultMessage);
        }

        return {
            refresh,
            highlight: highlightCurrent,
            clear: clearSelection,
            setDisabled(isDisabled, message) {
                if (isDisabled) {
                    wrap.dataset.disabled = "1";
                    wrap.dataset.state = "disabled";
                    statusEl.textContent = message || "Time editing is disabled for this item.";
                    grid.innerHTML = "";
                } else {
                    delete wrap.dataset.disabled;
                    const initial = missingInputsMessage();
                    setStatus("idle", initial || defaultMessage);
                }
            },
        };
    }
    function parseAmount(value) {
        const num = Number.parseFloat(value);
        return Number.isFinite(num) ? num : 0;
    }
    const GST_LABEL = `GST ${formatPercent(GST_PERCENT)}%`;
    function populateMasters(uiSelect) {
           uiSelect.innerHTML = "";
           // всегда показываем всех — нужно корректно отрисовать чужие строки
            (MASTERS || []).forEach(m => uiSelect.appendChild(buildOption(m.id, m.name || m.label || String(m.id))));
        }

    function populateServices(uiSelect, masterId) {
        uiSelect.innerHTML = "";
        const list = MS_MAP[String(masterId)] || [];
        list.forEach(s => {
            const opt = buildOption(s.id, s.name);
            if (s.base_price != null) opt.dataset.price = s.base_price;
            if (s.duration_min != null) opt.dataset.duration = s.duration_min;
            if (s.total_duration_min != null) opt.dataset.totalDuration = s.total_duration_min;
            if (s.is_taxable != null) opt.dataset.isTaxable = s.is_taxable ? "1" : "0";
            uiSelect.appendChild(opt);
        });
        uiSelect.disabled = list.length === 0;
    }

    function populatePromos(uiSelect, serviceId) {
        uiSelect.innerHTML = "";
        uiSelect.appendChild(buildOption("", "— No promocode —"));
        const list = (PROMO_BY_SERVICE[String(serviceId)] || []).concat(PROMO_GLOBAL || []);
        // дедуп по id
        const seen = new Set();
        list.forEach(p => {
            if (seen.has(p.id)) return;
            seen.add(p.id);
            uiSelect.appendChild(buildOption(p.id, p.text));
        });
    }

    const ITEM_STATUS_CLASSES = {
        BOOKED: "status-booked",
        CONFIRMED: "status-confirmed",
        COMPLETED: "status-completed",
        NO_SHOW: "status-noshow",
        CANCELLED: "status-cancelled",
    };
    const ITEM_STATUS_LABELS = {
        BOOKED: "Booked",
        CONFIRMED: "Confirmed",
        COMPLETED: "Completed",
        NO_SHOW: "No show",
        CANCELLED: "Cancelled",
    };
    const ACTION_STATUS_MAP = {
        confirm: "CONFIRMED",
        complete: "COMPLETED",
        noshow: "NO_SHOW",
        cancel: "CANCELLED",
    };
    const STATUS_CLASS_VALUES = Object.values(ITEM_STATUS_CLASSES);

    function normaliseStatusCode(value) {
        if (!value) return "BOOKED";
        return String(value).trim().toUpperCase();
    }

    function resolveStatusLabel(code, fallback) {
        const norm = normaliseStatusCode(code);
        if (fallback && String(fallback).trim()) {
            return String(fallback);
        }
        return ITEM_STATUS_LABELS[norm] || norm.charAt(0) + norm.slice(1).toLowerCase();
    }

    function statusBaseMessage(itemEl) {
        return "";
    }

    function getStatusHiddenInput(itemEl) {
        if (!itemEl) return null;
        const prefix = itemEl.dataset.formPrefix || "";
        if (prefix) {
            const exact = itemEl.querySelector(`input[name="${prefix}-status_code"]`);
            if (exact) return exact;
        }
        return itemEl.querySelector('input[name$="-status_code"]');
    }

    function getStatusReasonHiddenInput(itemEl) {
        if (!itemEl) return null;
        const prefix = itemEl.dataset.formPrefix || "";
        if (prefix) {
            const exact = itemEl.querySelector(`input[name="${prefix}-status_reason"]`);
            if (exact) return exact;
        }
        return itemEl.querySelector('input[name$="-status_reason"]');
    }

    function updateStatusNote(itemEl, stagedCode, reason) {
        const noteEl = itemEl && itemEl.querySelector('[data-role="status-note"]');
        if (!noteEl) return;
        noteEl.textContent = "";
        noteEl.classList.remove("pending");
        noteEl.style.display = "none";
    }

    function stageItemStatus(itemEl, code, options = {}) {
        if (!itemEl) return;
        const norm = normaliseStatusCode(code);
        const reasonText = (options.reason || "").trim();
        itemEl.dataset.pendingStatus = norm;
        const hidden = getStatusHiddenInput(itemEl);
        if (hidden) hidden.value = norm;
        const reasonHidden = getStatusReasonHiddenInput(itemEl);
        if (reasonHidden) reasonHidden.value = reasonText;
        if (reasonText) {
            itemEl.dataset.pendingCancelReason = reasonText;
        } else {
            delete itemEl.dataset.pendingCancelReason;
        }
        updateItemStatusPill(itemEl, norm);
        syncStatusButtons(itemEl, norm);
        updateStatusNote(itemEl, norm, reasonText);
    }

    function updateItemStatusPill(itemEl, code, label) {
        if (!itemEl) return;
        const pill = itemEl.querySelector('[data-role="status-pill"]');
        if (!pill) return;
        const normCode = normaliseStatusCode(code);
        const resolvedLabel = resolveStatusLabel(normCode, label || itemEl.dataset.statusLabel);
        pill.textContent = resolvedLabel;
        STATUS_CLASS_VALUES.forEach(cls => pill.classList.remove(cls));
        const className = ITEM_STATUS_CLASSES[normCode] || ITEM_STATUS_CLASSES.BOOKED;
        pill.classList.add(className);
        pill.dataset.statusCode = normCode;
        itemEl.dataset.statusCode = normCode;
        itemEl.dataset.statusLabel = resolvedLabel;
    }

    function syncStatusButtons(itemEl, currentCode) {
        const norm = normaliseStatusCode(currentCode);
        const hasItemId = !!itemEl.dataset.itemId;
        itemEl.querySelectorAll(".ab-item-status-btn").forEach(btn => {
            const action = btn.dataset.action || "";
            const targetCode = ACTION_STATUS_MAP[action] || "";
            if (!hasItemId) {
                btn.disabled = true;
                btn.classList.add("disabled");
                return;
            }
            btn.disabled = targetCode === norm;
            if (btn.disabled) {
                btn.classList.add("disabled");
            } else {
                btn.classList.remove("disabled");
            }
        });
    }

    function notifyUser(message, level = "info") {
        if (!message) return;
        const toast = window.showToast || window.notify || null;
        if (typeof toast === "function") {
            toast(message, level);
            return;
        }
        if (window.console) {
            const fn = level === "error" ? console.error : console.info;
            fn.call(console, message);
        }
        if (level === "error" || level === "warning") {
            window.alert(message);
        }
    }

    function handleStatusButtonClick(event) {
        const btn = event.currentTarget;
        const itemEl = btn.closest(".ab-item");
        if (!itemEl) return;
        const action = btn.dataset.action || "";
        const targetStatus = ACTION_STATUS_MAP[action];
        if (!targetStatus) return;
        if (!itemEl.dataset.itemId) {
            notifyUser("Save this appointment before managing item status.", "warning");
            return;
        }
        let reasonValue = itemEl.dataset.pendingCancelReason || "";
        if (targetStatus === "CANCELLED") {
            const response = window.prompt("Cancellation reason (optional)", reasonValue);
            if (response === null) {
                return;
            }
            reasonValue = response.trim();
        } else {
            reasonValue = "";
        }
        stageItemStatus(itemEl, targetStatus, { reason: reasonValue, notify: false });
    }

    function initItemStatusControls(itemEl) {
        if (!itemEl) return;
        const currentCode = normaliseStatusCode(itemEl.dataset.statusCode);
        const currentLabel = itemEl.dataset.statusLabel;
        if (!itemEl.dataset.originalStatusCode) {
            itemEl.dataset.originalStatusCode = currentCode;
        }
        const hidden = getStatusHiddenInput(itemEl);
        const stagedCode = hidden && hidden.value ? normaliseStatusCode(hidden.value) : "";
        const reasonHidden = getStatusReasonHiddenInput(itemEl);
        const stagedReason = reasonHidden && reasonHidden.value ? reasonHidden.value : "";
        if (stagedCode && stagedCode !== currentCode) {
            stageItemStatus(itemEl, stagedCode, { reason: stagedReason, silent: true, notify: false });
        } else {
            updateItemStatusPill(itemEl, currentCode, currentLabel);
            syncStatusButtons(itemEl, currentCode);
            itemEl.dataset.pendingStatus = "";
            if (stagedReason) {
                itemEl.dataset.pendingCancelReason = stagedReason;
            } else {
                delete itemEl.dataset.pendingCancelReason;
            }
            updateStatusNote(itemEl, "", "");
        }
        itemEl.querySelectorAll(".ab-item-status-btn").forEach(btn => {
            btn.addEventListener("click", handleStatusButtonClick);
        });
    }
    function updateRowSummary(row) {
        const priceInput = row.querySelector('input[name$="-unit_price"]');
        const deleteInput = row.querySelector('input[name$="-DELETE"]');
        const discountInput = row.querySelector('input[name$="-manual_discount_percent"]');
        const isDeleted = !!(deleteInput && deleteInput.checked);
        const hasSnapshot = row.dataset.hasPricing === "1";
        const isDirty = row.dataset.pricingDirty === "1";

        let baseAmount = roundCurrency(parseAmount(row.dataset.basePrice));
        if (!baseAmount) {
            baseAmount = roundCurrency(parseAmount(row.dataset.finalPrice));
            row.dataset.basePrice = baseAmount.toFixed(2);
        }

        const storedFinal = roundCurrency(parseAmount(row.dataset.finalPrice));
        const storedTax = roundCurrency(parseAmount(row.dataset.taxAmount));

        let taxable = !isDeleted && GST_ENABLED && row.dataset.taxable === "1";
        if (hasSnapshot && !isDeleted && storedTax > 0) {
            taxable = true;
            row.dataset.taxable = "1";
        }

        let subtotal;
        let tax;

        if (hasSnapshot && !isDirty && !isDeleted) {
            subtotal = storedFinal;
            tax = taxable ? storedTax : 0;
        } else {
            const rawValue = priceInput && priceInput.value !== '' ? Number(priceInput.value) : NaN;
            subtotal = isDeleted ? 0 : roundCurrency(Number.isFinite(rawValue) ? rawValue : storedFinal);
            tax = taxable ? roundCurrency(subtotal * GST_PERCENT / 100) : 0;
            row.dataset.finalPrice = subtotal.toFixed(2);
            row.dataset.taxAmount = tax.toFixed(2);
        }

        let discountAmount = roundCurrency(Math.abs(parseAmount(row.dataset.discountAmount)));
        if (!(hasSnapshot && !isDirty && !isDeleted)) {
            let computedDiscount = baseAmount > subtotal ? roundCurrency(baseAmount - subtotal) : 0;
            if (!computedDiscount && discountInput) {
                const manualPercent = Number.parseFloat(discountInput.value || "0");
                if (Number.isFinite(manualPercent) && manualPercent > 0 && !isDeleted) {
                    computedDiscount = roundCurrency(baseAmount * (manualPercent / 100));
                    subtotal = roundCurrency(baseAmount - computedDiscount);
                    tax = taxable ? roundCurrency(subtotal * GST_PERCENT / 100) : 0;
                    row.dataset.finalPrice = subtotal.toFixed(2);
                    row.dataset.taxAmount = tax.toFixed(2);
                }
            }
            discountAmount = computedDiscount;
        }
        row.dataset.discountAmount = discountAmount.toFixed(2);

        const subtotalEl = row.querySelector('.js-item-subtotal');
        if (subtotalEl) subtotalEl.textContent = money(subtotal);
        const baseEl = row.querySelector('.js-item-base');
        if (baseEl) baseEl.textContent = money(baseAmount);
        const discountEl = row.querySelector('.js-item-discount');
        if (discountEl) discountEl.textContent = moneySigned(-discountAmount);
        const taxRowEl = row.querySelector('.js-item-tax-row');
        if (taxRowEl) taxRowEl.classList.toggle('ab-hidden', !(taxable && (subtotal > 0 || tax > 0)));
        const taxLabelEl = row.querySelector('.js-item-tax-label');
        if (taxLabelEl) taxLabelEl.textContent = GST_LABEL;
        const taxEl = row.querySelector('.js-item-tax');
        if (taxEl) taxEl.textContent = money(tax);
       const total = roundCurrency(subtotal + tax);
       const totalEl = row.querySelector('.js-item-total');
       if (totalEl) totalEl.textContent = money(total);
        const tagsEl = row.querySelector('.js-item-tags');
        if (tagsEl) tagsEl.style.display = row.dataset.pricingDirty === "1" ? "none" : "";

        return { subtotal, tax, total };
    }

    function updateSaleSummary(row) {
        const quantityInput = row.querySelector('input[name$="-quantity"]');
        const unitPriceInput = row.querySelector('input[name$="-unit_price"]');
        const deleteInput = row.querySelector('input[name$="-DELETE"]');
        const isDeleted = !!(deleteInput && deleteInput.checked);
        const datasetValue = row.dataset.saleSubtotal ? Number(row.dataset.saleSubtotal) : 0;
        const quantity = quantityInput && quantityInput.value !== '' ? Number(quantityInput.value) : NaN;
        const unitPrice = unitPriceInput && unitPriceInput.value !== '' ? Number(unitPriceInput.value) : NaN;
        const subtotal = isDeleted ? 0 : roundCurrency(Number.isFinite(quantity) && Number.isFinite(unitPrice) ? quantity * unitPrice : datasetValue);
        row.dataset.saleSubtotal = String(subtotal.toFixed(2));
        const taxable = !isDeleted && GST_ENABLED;
        const tax = taxable ? roundCurrency(subtotal * GST_PERCENT / 100) : 0;
        row.dataset.saleTax = String(tax.toFixed(2));
        const total = roundCurrency(subtotal + tax);
        const subtotalEl = row.querySelector('.js-sale-subtotal');
        if (subtotalEl) subtotalEl.textContent = money(subtotal);
        const taxRowEl = row.querySelector('.js-sale-tax-row');
        if (taxRowEl) taxRowEl.classList.toggle('ab-hidden', !taxable);
        const taxLabelEl = row.querySelector('.js-sale-tax-label');
        if (taxLabelEl) taxLabelEl.textContent = GST_LABEL;
        const taxEl = row.querySelector('.js-sale-tax');
        if (taxEl) taxEl.textContent = money(tax);
        const totalEl = row.querySelector('.js-sale-total');
        if (totalEl) totalEl.textContent = money(total);
        const totalBadge = row.querySelector('[data-product-sale-role="total"]');
        if (totalBadge) totalBadge.textContent = money(total);
        return { subtotal, tax, total };
    }

    function recomputeAllTotals() {
        let subtotalSum = 0;
        let taxSum = 0;
        let baseSum = 0;
        let discountSum = 0;
        let productSubtotal = 0;

        $$('.ab-item', itemsContainer).forEach(row => {
            const { subtotal, tax } = updateRowSummary(row);
            subtotalSum += subtotal;
            taxSum += tax;

            const hasSnapshot = row.dataset.hasPricing === "1" && row.dataset.pricingDirty !== "1";
            const baseAmount = roundCurrency(parseAmount(row.dataset.basePrice));
            const discountAmount = roundCurrency(parseAmount(row.dataset.discountAmount));

            if (hasSnapshot) {
                baseSum += baseAmount;
                discountSum += discountAmount;
            } else {
                const effectiveBase = baseAmount || subtotal;
                baseSum += effectiveBase;
                discountSum += discountAmount || (effectiveBase > subtotal ? roundCurrency(effectiveBase - subtotal) : 0);
            }
        });

        if (salesContainer) {
            $$('.ps-item', salesContainer).forEach(row => {
                const { subtotal, tax } = updateSaleSummary(row);
                subtotalSum += subtotal;
                taxSum += tax;
                productSubtotal += subtotal;
            });
        }

        subtotalSum = roundCurrency(subtotalSum);
        taxSum = roundCurrency(taxSum);
        const preFeeTotal = roundCurrency(subtotalSum + taxSum);
        let processingFee = 0;
        if (cardFeeApplied && preFeeTotal > 0 && (CARD_FEE_PERCENT > 0 || CARD_FEE_FIXED > 0)) {
            processingFee = roundCurrency((preFeeTotal * CARD_FEE_PERCENT) + CARD_FEE_FIXED);
        }
        const totalSum = roundCurrency(preFeeTotal + processingFee);

        if (subtotalDisplay) subtotalDisplay.textContent = money(subtotalSum);
        if (taxDisplay) taxDisplay.textContent = money(taxSum);
        if (totalDisplay) {
            totalDisplay.textContent = money(totalSum);
            totalDisplay.dataset.totalAmount = totalSum.toFixed(2);
        }
        if (taxRowDisplay) taxRowDisplay.classList.toggle('ab-hidden', taxSum === 0);
        if (gstLabelDisplay) gstLabelDisplay.textContent = GST_LABEL;
        if (feeDisplay) feeDisplay.textContent = money(processingFee);
        if (feeRowDisplay) feeRowDisplay.style.display = processingFee > 0 ? "" : "none";

        const baseDisplay = document.getElementById('appt-base-subtotal');
        if (baseDisplay) baseDisplay.textContent = money(baseSum);
        const discountDisplay = document.getElementById('appt-discount-total');
        if (discountDisplay) discountDisplay.textContent = moneySigned(-discountSum);
        const productDisplay = document.getElementById('appt-product-subtotal');
        if (productDisplay) {
            productDisplay.textContent = money(productSubtotal);
            const productLine = productDisplay.closest('.ab-summary-line');
            if (productLine) productLine.style.display = productSubtotal > 0.004 ? "" : "none";
        }
        if (discountDisplay) {
            const discountLine = discountDisplay.closest('.ab-summary-line');
            if (discountLine) discountLine.style.display = discountSum > 0.004 ? "" : "none";
        }
    }
    // disabled поля не уезжают в POST — подложим hidden-клон
    function readValueFor(el) {
        if (el.tagName === "SELECT") return el.value || "";
        if (el.type === "checkbox") return el.checked ? (el.value || "on") : "";
        return el.value || "";
    }
    // disabled поля не уезжают в POST — подложим hidden-клон
    function ensureHiddenClone(el) {
        if (!el || !el.name) return;
        // уже есть клон?
        const next = el.nextElementSibling;
        if (next && next.tagName === "INPUT" && next.type === "hidden" && next.name === el.name && next.dataset.generated === "1") {
            // обновим value на всякий
            next.value = readValueFor(el);
            return;
        }
        const hid = document.createElement("input");
        hid.type = "hidden";
        hid.name = el.name;
        hid.value = readValueFor(el);
        hid.dataset.generated = "1";
        el.insertAdjacentElement("afterend", hid);
    }

    function disableAndClone(el) {
        try { el.disabled = true; } catch {}
        ensureHiddenClone(el);
    }

    // синхронизация UI<->нативных полей
    function syncSelects(ui, native) {
        if (!ui || !native) return;
        // первичное выравнивание
        if (native.value) ui.value = String(native.value);
        ui.addEventListener("change", () => { native.value = ui.value; });
    }
    function syncRowToNative(row) {
        const nativeMaster = row.querySelector(".native-master select");
        const uiMaster     = row.querySelector(".js-master");
        if (nativeMaster && uiMaster && uiMaster.value) nativeMaster.value = uiMaster.value;

        const nativeSvc = row.querySelector(".native-service select");
        const uiSvc     = row.querySelector(".js-service");
        if (nativeSvc && uiSvc) {
            // передать опции и значение
            mirrorOptions(nativeSvc, uiSvc);
            const lbl = uiSvc.selectedOptions?.[0]?.textContent || "";
            setSelectValueEnsuringOption(nativeSvc, uiSvc.value, lbl);
        }

        const nativePromo = row.querySelector(".native-promocode select[name$='-promocode']");
        const uiPromo     = row.querySelector(".js-promocode");
        if (nativePromo && uiPromo) {
            // промокоды могут быть тоже пустыми в native — синхронизируем минимально выбранное
            setSelectValueEnsuringOption(nativePromo, uiPromo.value, uiPromo.selectedOptions?.[0]?.textContent || "");
        }

        const nativeForce  = row.querySelector(".native-promocode input[name$='-force_apply']");
        const promoForceUI = row.querySelector(".js-promo-force");
        if (nativeForce) nativeForce.checked = !!(promoForceUI && promoForceUI.checked);

        const nativeValidation = row.querySelector(".native-validation input[type='checkbox'][name$='-validation_enabled']");
        const hiddenValidation = row.querySelector(".native-validation input[type='hidden'][name$='-validation_enabled']");
        const uiValidation = row.querySelector(".js-validation-toggle");
        if (nativeValidation && uiValidation) {
            nativeValidation.checked = uiValidation.checked;
        }
        if (hiddenValidation && uiValidation) {
            hiddenValidation.value = uiValidation.checked ? "True" : "False";
        }
    }
    function initRow(row) {
        // элементы
        const nativeMaster = $(".native-master select", row);
        const uiMaster     = $(".js-master", row);
        const nativeSvc    = $(".native-service select", row);
        const uiSvc        = $(".js-service", row);
        const nativePromo  = $(".native-promocode select[name$='-promocode']", row);
        const uiPromo      = $(".js-promocode", row);
        const promoForceUI = $(".js-promo-force", row);
        const nativeValidation = $(".native-validation input[type='checkbox'][name$='-validation_enabled']", row);
        const hiddenValidation = $(".native-validation input[type='hidden'][name$='-validation_enabled']", row);
        const uiValidation = $(".js-validation-toggle", row);
        const nativeStartDate = $("[name$='-start_time_0']", row);
        const nativeStartTime = $("[name$='-start_time_1']", row);
        const nativePrice  = $("[name$='-unit_price']", row);   // реальное поле
        const durationInput = $("[name$='-duration_override_min']", row);
        const discountInput = $("[name$='-manual_discount_percent']", row);
        const deleteInputToggle = $("input[name$='-DELETE']", row);
        const delWrap      = $(".js-del-wrap", row);
        const roBadge      = $(".js-ro-badge", row);
        let timeslotPicker = null;
        row.dataset.taxable = "0";
        row.dataset.pricingDirty = row.dataset.hasPricing === "1" ? "0" : "1";
        row.dataset.finalPrice = roundCurrency(parseAmount(row.dataset.finalPrice)).toFixed(2);
        row.dataset.taxAmount = roundCurrency(parseAmount(row.dataset.taxAmount)).toFixed(2);
        row.dataset.basePrice = roundCurrency(parseAmount(row.dataset.basePrice)).toFixed(2);
        row.dataset.discountAmount = roundCurrency(parseAmount(row.dataset.discountAmount)).toFixed(2);

        if (row.dataset.itemId) {
            if (!row.dataset.originalDate && nativeStartDate && nativeStartDate.value) {
                row.dataset.originalDate = nativeStartDate.value;
            }
            if (!row.dataset.originalTime && nativeStartTime && nativeStartTime.value) {
                row.dataset.originalTime = normalizeTimeLabel(nativeStartTime.value);
            }
        }

        const markDirty = () => { row.dataset.pricingDirty = "1"; };

        const ensureTimeslotPicker = () => {
            if (timeslotPicker) return timeslotPicker;
            if (!nativeStartDate || !nativeStartTime) return null;
            const wrap = row.querySelector(".js-timeslots-wrap");
            if (!wrap) return null;
            timeslotPicker = initTimeslotPickerForRow({
                row,
                masterEl: uiMaster,
                serviceEl: uiSvc,
                dateEl: nativeStartDate,
                timeEl: nativeStartTime,
                validationToggle: uiValidation,
            });
            return timeslotPicker;
        };

        const refreshTimeslots = (options = {}) => {
            const picker = ensureTimeslotPicker();
            if (!picker) return;
            const isDisabled = (nativeStartDate && nativeStartDate.disabled) || (nativeStartTime && nativeStartTime.disabled);
            if (isDisabled) {
                picker.setDisabled(true, "Time editing is disabled for this item.");
                return;
            }
            picker.setDisabled(false);
            picker.refresh(options);
        };

        const highlightTimeslot = () => {
            const picker = ensureTimeslotPicker();
            if (!picker) return;
            picker.highlight();
        };

        if (uiValidation && nativeValidation) {
            uiValidation.checked = nativeValidation.checked;
            if (hiddenValidation) {
                hiddenValidation.value = uiValidation.checked ? "True" : "False";
            }
            uiValidation.addEventListener("change", () => {
                nativeValidation.checked = uiValidation.checked;
                if (hiddenValidation) {
                    hiddenValidation.value = uiValidation.checked ? "True" : "False";
                }
                markDirty();
                if (timeslotPicker) {
                    timeslotPicker.refresh({ preserveSelection: true });
                }
            });
        }

        const syncTaxableMeta = () => {
            const opt = uiSvc && uiSvc.selectedOptions ? uiSvc.selectedOptions[0] : null;
            const taxable = !!(opt && opt.dataset && opt.dataset.isTaxable === "1");
            row.dataset.taxable = taxable ? "1" : "0";
            return taxable;
        };

        // наполним мастеров и выставим значения
        populateMasters(uiMaster);
        if (durationInput && !durationInput.value) {
            durationInput.dataset.auto = '1';
        }
        if (durationInput) {
            durationInput.addEventListener('input', () => {
                durationInput.dataset.auto = '0';
                markDirty();
                recomputeAllTotals();
            });
        }
        if (discountInput) {
            discountInput.addEventListener('change', () => {
                const val = parseInt(discountInput.value, 10);
                if (Number.isNaN(val)) return;
                if (val < 0) discountInput.value = '0';
                if (val > 100) discountInput.value = '100';
                markDirty();
                recomputeAllTotals();
            });
        }
        if (deleteInputToggle) {
            deleteInputToggle.addEventListener('change', () => {
                markDirty();
                recomputeAllTotals();
            });
        }
        if (nativePrice) {
            nativePrice.addEventListener('input', () => { markDirty(); recomputeAllTotals(); });
            nativePrice.addEventListener('change', () => { markDirty(); recomputeAllTotals(); });
        }

        // не трогаем значение master у существующих строк; просто отражаем его в UI
        if (nativeMaster && uiMaster) uiMaster.value = String(nativeMaster.value || "");
        // мастер не может менять мастера
        if (IS_MASTER && uiMaster) uiMaster.disabled = true;

        // услуги исходя из мастер-id
        const nativeSvcLabel = nativeSvc?.selectedOptions?.[0]?.textContent || "";
        const effectiveMasterId = (nativeMaster ? nativeMaster.value : (uiMaster ? uiMaster.value : ""));
        populateServices(uiSvc, effectiveMasterId);
        if (nativeSvc && uiSvc && nativeSvc.value) {
            ensureUiOption(uiSvc, nativeSvc.value, nativeSvcLabel);
            uiSvc.value = String(nativeSvc.value);
        }
        const initialOpt = uiSvc?.selectedOptions?.[0];
        if (durationInput && (!durationInput.value || durationInput.dataset.auto === '1')) {
            const initialTotal = initialOpt && initialOpt.dataset ? (initialOpt.dataset.totalDuration || initialOpt.dataset.duration || '') : '';
            if (initialTotal) {
                durationInput.value = initialTotal;
                durationInput.dataset.auto = '1';
            }
        }
        mirrorOptions(nativeSvc, uiSvc);

        // после того как uiSvc.value задан — протолкнём в native
        const label = uiSvc?.selectedOptions?.[0]?.textContent || nativeSvcLabel;
        setSelectValueEnsuringOption(nativeSvc, uiSvc ? uiSvc.value : "", label);
        syncTaxableMeta();
        updateRowSummary(row);


        // при изменении сервиса пользователем: и в native опции/значение
        uiSvc.addEventListener("change", () => {
            mirrorOptions(nativeSvc, uiSvc);
            const label = uiSvc.selectedOptions?.[0]?.textContent || "";
            setSelectValueEnsuringOption(nativeSvc, uiSvc.value, label);
            const opt = uiSvc.selectedOptions?.[0];
            const totalDur = opt && opt.dataset ? (opt.dataset.totalDuration || opt.dataset.duration || "") : "";
            const newBase = opt && opt.dataset ? roundCurrency(parseAmount(opt.dataset.price)) : 0;
            row.dataset.basePrice = newBase.toFixed(2);
            row.dataset.finalPrice = newBase.toFixed(2);
            row.dataset.discountAmount = "0.00";
            row.dataset.taxAmount = "0.00";
            row.dataset.hasPricing = "0";
            row.dataset.pricingDirty = "1";
            const priceField = row.querySelector('input[name$="-unit_price"]');
            if (priceField) {
                priceField.value = newBase > 0 ? newBase.toFixed(2) : "";
            }
            if (durationInput) {
                if (!durationInput.value || durationInput.dataset.auto === '1') {
                    durationInput.value = totalDur || '';
                    if (totalDur) {
                        durationInput.dataset.auto = '1';
                    }
                }
            }
            if (typeof populatePromos === "function") {
                populatePromos(uiPromo, uiSvc.value);
            }
            syncTaxableMeta();
            markDirty();
            recomputeAllTotals();
            refreshTimeslots();
        });
        // промокоды (UI остаётся disabled по умолчанию, включим ниже для «моих»)
        if (nativeSvc && nativeSvc.value) {
            populatePromos(uiPromo, nativeSvc.value);
            if (nativePromo && nativePromo.value) uiPromo.value = String(nativePromo.value);
        }

        // решим, «моя» ли эта строка
        const isMine = IS_MASTER && MY_ID && nativeMaster ? (String(nativeMaster.value) === MY_ID) : false;


        // права редактирования:
        if (IS_MASTER) {
            if (isMine) {
                // МОЯ строка: master зафриженный; сервис и промокод — можно
                uiSvc.disabled = false;
                // включим UI промокода, но синхронизируем с нативой
                uiPromo.disabled = false;

                // изменения сервисов — в нативу
                uiSvc.addEventListener("change", () => {
                    if (nativeSvc) nativeSvc.value = uiSvc.value;
                    populatePromos(uiPromo, uiSvc.value);
                    if (nativePromo) nativePromo.value = uiPromo.value;
                    syncTaxableMeta();
                    markDirty();
                    recomputeAllTotals();
                    refreshTimeslots();
                });

                // промо в нативу
                if (nativePromo) {
                    uiPromo.addEventListener("change", () => {
                        nativePromo.value = uiPromo.value;
                        markDirty();
                        recomputeAllTotals();
                    });
                }
                if (promoForceUI) {
                    const nativeForce = $(".native-promocode input[name$='-force_apply']", row);
                    promoForceUI.addEventListener("change", () => {
                        if (nativeForce) nativeForce.checked = !!promoForceUI.checked;
                        markDirty();
                        recomputeAllTotals();
                    });
                }
            } else {
                // ЧУЖАЯ строка: всё делаем read-only
                // ЧУЖАЯ строка: всё делаем read-only
                row.classList.add("readonly");

                // UI селекты/контролы блокируем
                if (uiSvc) uiSvc.disabled = true;
                if (uiPromo) uiPromo.disabled = true;
                if (promoForceUI) {
                    promoForceUI.disabled = true;
                    const nativeForce = $(".native-promocode input[name$='-force_apply']", row);
                    promoForceUI.checked = !!(nativeForce && nativeForce.checked);
                }

                // реальные отправляемые инпуты — делаем disabled и подкладываем hidden-клоны
                const nativeStartDate = $("[name$='-start_time_0']", row);
                const nativeStartTime = $("[name$='-start_time_1']", row);
                const nativePrice     = $("[name$='-unit_price']",    row);

                if (nativeStartDate) disableAndClone(nativeStartDate);
                if (nativeStartTime) disableAndClone(nativeStartTime);
                if (nativePrice)     disableAndClone(nativePrice);
                if (durationInput)   disableAndClone(durationInput);
                if (discountInput)   disableAndClone(discountInput);
                if (nativeValidation) disableAndClone(nativeValidation);
                if (uiValidation) uiValidation.disabled = true;

                // если поверх time уже навешан четвертной селект — тоже задизейблим


                // удалить чужое нельзя: вырубаем чекбокс DELETE и прячем «кнопку»
                const delInput = $("input[name$='-DELETE']", row);
                if (delInput) {
                    delInput.disabled = true; // на всякий
                    const lbl = delInput.closest("label");
                    if (lbl && lbl.classList.contains("ab-btn")) {
                        lbl.classList.add("ab-hidden");         // полностью скрыть
                        lbl.style.pointerEvents = "none";       // и на всякий без кликов
                    }
                }

                // глушим любые взаимодействия внутри чужой строки (клики/клавиатура)
                const stopper = e => { e.preventDefault(); e.stopPropagation(); };
                row.addEventListener("click", stopper, true);
                row.addEventListener("mousedown", stopper, true);
                row.addEventListener("keydown", stopper, true);

            }
        } else {
            // админ: обычная синхронизация UI <> нативные поля
            syncSelects(uiMaster, nativeMaster);
            uiMaster.addEventListener("change", () => {
                populateServices(uiSvc, uiMaster.value);
                // сбросим сервис+промо при смене мастера
                if (nativeSvc) nativeSvc.value = "";
                if (uiSvc) uiSvc.value = "";
                if (nativePromo) nativePromo.value = "";
                if (uiPromo) { uiPromo.value = ""; uiPromo.disabled = true; }
                markDirty();
                recomputeAllTotals();
                refreshTimeslots();
            });
            uiSvc.disabled = false;
            uiSvc.addEventListener("change", () => {
                if (nativeSvc) nativeSvc.value = uiSvc.value;
                const opt = uiSvc.selectedOptions?.[0];
                const totalDur = opt && opt.dataset ? (opt.dataset.totalDuration || opt.dataset.duration || '') : '';
                if (durationInput) {
                    if (!durationInput.value || durationInput.dataset.auto === '1') {
                        durationInput.value = totalDur || '';
                        if (totalDur) {
                            durationInput.dataset.auto = '1';
                        }
                    }
                }
                populatePromos(uiPromo, uiSvc.value);
                markDirty();
                recomputeAllTotals();
                refreshTimeslots();
            });
            if (nativePromo) {
                uiPromo.disabled = false;
                uiPromo.addEventListener("change", () => {
                    nativePromo.value = uiPromo.value;
                    markDirty();
                    recomputeAllTotals();
                });
            }
        if (promoForceUI) {
            const nativeForce = $(".native-promocode input[name$='-force_apply']", row);
            promoForceUI.addEventListener("change", () => {
                if (nativeForce) nativeForce.checked = !!promoForceUI.checked;
                markDirty();
                recomputeAllTotals();
            });
        }
    }

        if (nativeStartDate) {
            nativeStartDate.addEventListener("change", () => {
                refreshTimeslots({ preserveSelection: true });
            });
        }
        if (nativeStartTime) {
            nativeStartTime.addEventListener("change", highlightTimeslot);
            nativeStartTime.addEventListener("input", highlightTimeslot);
        }

        const preserveInitialSlot = !!(nativeStartTime && nativeStartTime.value);
        refreshTimeslots({ preserveSelection: preserveInitialSlot });
    }

    function initExistingRows() {
        $$(".ab-item", itemsContainer).forEach(initRow);
    }

    // добавление новой строки (когда работает ваш существующий код на клонирование empty_form)
    // после вставки — проинициализируем и зафиксируем мастера
    const mo = new MutationObserver(muts => {
        muts.forEach(m => m.addedNodes.forEach(node => {
            if (node.nodeType === 1 && node.classList.contains("ab-item")) {
                // если мастер — сразу подставим себя в нативу и UI
                if (IS_MASTER && MY_ID) {
                    const nativeMaster = $(".native-master select", node);
                    const uiMaster = $(".js-master", node);
                    if (nativeMaster) nativeMaster.value = MY_ID;
                    if (uiMaster) { uiMaster.value = MY_ID; uiMaster.disabled = true; }

                }
                initRow(node);
            }
        }));
    });
    mo.observe(itemsContainer, { childList: true });

    // Добавление новой строки из empty_form
    function nextFormIndex() {
        const totalEl = document.querySelector('input[name="items-TOTAL_FORMS"]');
        return totalEl ? parseInt(totalEl.value || "0", 10) : 0;
    }
    function bumpTotalForms() {
        const totalEl = document.querySelector('input[name="items-TOTAL_FORMS"]');
        if (totalEl) totalEl.value = String((parseInt(totalEl.value || "0", 10) + 1));
    }

    function replacePrefixAttributes(rootEl, idx) {
        const walk = rootEl.querySelectorAll("[name], [id], label[for]");
        walk.forEach(el => {
            if (el.name && el.name.includes("__prefix__")) el.name = el.name.replace(/__prefix__/g, idx);
            if (el.id && el.id.includes("__prefix__")) el.id = el.id.replace(/__prefix__/g, idx);
            if (el.getAttribute && el.hasAttribute("for")) {
                const f = el.getAttribute("for");
                if (f && f.includes("__prefix__")) el.setAttribute("for", f.replace(/__prefix__/g, idx));
            }
        });
        // для удобства
        rootEl.dataset.formIndex = String(idx);
        if (rootEl.dataset.formPrefix && rootEl.dataset.formPrefix.includes("__prefix__")) {
            rootEl.dataset.formPrefix = rootEl.dataset.formPrefix.replace(/__prefix__/g, idx);
        }
    }

    function initDefaultsForNewRow(row) {
        // если мастер — сразу зафиксируем своего мастера
        if (IS_MASTER && MY_ID) {
            const nativeMaster = $(".native-master select", row);
            const uiMaster = $(".js-master", row);
            if (nativeMaster) nativeMaster.value = MY_ID;
            if (uiMaster) { uiMaster.value = MY_ID; uiMaster.disabled = true; }
        }
    }

    function applySaleDefaults(row) {
        if (!row || row.dataset.defaultsApplied === "1") return;
        const objIdInput = row.querySelector('input[name$="-id"]');
        if (objIdInput && objIdInput.value) {
            row.dataset.saleSubtotal = row.dataset.saleSubtotal || "0.00";
            row.dataset.saleTax = row.dataset.saleTax || "0.00";
            updateSaleSummary(row);
            row.dataset.defaultsApplied = "1";
            return;
        }
        const defaults = SALE_DEFAULTS || {};

        const quantityInput = row.querySelector('input[name$="-quantity"]');
        if (quantityInput && !quantityInput.value && defaults.quantity) {
            quantityInput.value = defaults.quantity;
        }

        const soldBySelect = row.querySelector('select[name$="-sold_by"]');
        const soldByDefault = defaults.sold_by;
        if (soldBySelect && soldByDefault && !soldBySelect.value) {
            const soldId = String(soldByDefault.id || soldByDefault);
            const soldLabel = soldByDefault.label || soldByDefault.name || soldId;
            setSelectValueEnsuringOption(soldBySelect, soldId, soldLabel);
            const changeEvent = new Event("change", { bubbles: true });
            soldBySelect.dispatchEvent(changeEvent);
            if (window.django && window.django.jQuery) {
                window.django.jQuery(soldBySelect).trigger("change");
            } else if (window.jQuery) {
                window.jQuery(soldBySelect).trigger("change");
            }
        }

        const clientSelect = row.querySelector('select[name$="-client"]');
        const clientDefault = defaults.client;
        if (clientSelect && clientDefault && !clientSelect.value) {
            const clientId = String(clientDefault.id || clientDefault);
            const clientLabel = clientDefault.label || clientDefault.name || clientId;
            setSelectValueEnsuringOption(clientSelect, clientId, clientLabel);
            const changeEvent = new Event("change", { bubbles: true });
            clientSelect.dispatchEvent(changeEvent);
            if (window.django && window.django.jQuery) {
                window.django.jQuery(clientSelect).trigger("change");
            } else if (window.jQuery) {
                window.jQuery(clientSelect).trigger("change");
            }
        }
        row.dataset.saleSubtotal = row.dataset.saleSubtotal || "0.00";
        row.dataset.saleTax = row.dataset.saleTax || "0.00";
        updateSaleSummary(row);
        row.dataset.defaultsApplied = "1";
    }

    function ensureSalePriceBinding(row) {
        if (!row) return;
        const productField =
            row.querySelector('input[type="hidden"][name$="-product"]') || // CHANGED
            row.querySelector('select[name$="-product"]') || // CHANGED
            row.querySelector('[data-product-sale-role="product"]') || // CHANGED
            row.querySelector('input[name$="-product"]'); // CHANGED
        const unitPriceInput =
            row.querySelector('[data-product-sale-role="unit-price"]') ||
            row.querySelector('input[name$="-unit_price"]');
        if (!productField || !unitPriceInput) return;

        if (!productField.dataset.productSaleRole) {
            productField.setAttribute("data-product-sale-role", "product");
        }
        if (!unitPriceInput.dataset.productSaleRole) {
            unitPriceInput.setAttribute("data-product-sale-role", "unit-price");
        }
        if (unitPriceInput.dataset.salePriceUserBinding !== "1") { // CHANGED
            const markUserEdited = (event) => { // CHANGED
                if (event && event.isTrusted) { // CHANGED
                    unitPriceInput.dataset.userEdited = "1"; // CHANGED
                } // CHANGED
            }; // CHANGED
            unitPriceInput.addEventListener("input", markUserEdited); // CHANGED
            unitPriceInput.addEventListener("change", markUserEdited); // CHANGED
            unitPriceInput.dataset.salePriceUserBinding = "1"; // CHANGED
        } // CHANGED
        if (!unitPriceInput.dataset.userEdited && unitPriceInput.value && unitPriceInput.value.trim()) { // CHANGED
            unitPriceInput.dataset.userEdited = "1"; // CHANGED
        } // CHANGED

        const endpointRaw = (productField.dataset.priceEndpoint || window.PRODUCT_SALE_PRICE_ENDPOINT || "").trim(); // CHANGED
        if (endpointRaw) { // CHANGED
            productField.dataset.priceEndpoint = endpointRaw; // CHANGED
        } // CHANGED

        const existingBinding = productField.__salePriceBinding; // CHANGED
        if (existingBinding && existingBinding.unitPriceInput === unitPriceInput) { // CHANGED
            existingBinding.sync(false); // CHANGED
            return; // CHANGED
        } else if (existingBinding) { // CHANGED
            productField.removeEventListener("change", existingBinding.handleSelection); // CHANGED
            productField.removeEventListener("input", existingBinding.handleSelection); // CHANGED
            if (typeof existingBinding.detachJq === "function") { // CHANGED
                existingBinding.detachJq(); // CHANGED
            } // CHANGED
        } // CHANGED

        if (!endpointRaw) return; // CHANGED

        const jq = (window.django && window.django.jQuery) || window.jQuery || null; // CHANGED
        let priceRequestSeq = 0; // CHANGED
        const previewRequestSeq = Object.create(null); // CHANGED
        const productMetaCache = Object.create(null); // CHANGED
        const pendingMeta = new Set(); // CHANGED

        function normalizePrice(value) {
            const raw = String(value ?? "").trim();
            if (!raw) return null;
            const sanitized = raw.replace(/\s+/g, "").replace(",", ".");
            const numeric = Number(sanitized);
            if (Number.isFinite(numeric)) {
                return numeric.toFixed(2);
            }
            return raw;
        }

        function dispatchRecalc() { // CHANGED
            updateSaleSummary(row); // CHANGED
            unitPriceInput.dispatchEvent(new Event("input", { bubbles: true })); // CHANGED
            unitPriceInput.dispatchEvent(new Event("change", { bubbles: true })); // CHANGED
            recomputeAllTotals(); // CHANGED
        }

        function applyPrice(rawPrice) {
            if (unitPriceInput.dataset.userEdited === "1") { // CHANGED
                return; // CHANGED
            } // CHANGED
            const normalized = normalizePrice(rawPrice);
            if (normalized == null) return;
            const current = (unitPriceInput.value || "").trim();
            if (current === normalized) {
                if (unitPriceInput.dataset.userEdited === "1") {
                    unitPriceInput.dataset.userEdited = "";
                }
                return;
            }
            unitPriceInput.value = normalized;
            unitPriceInput.dataset.userEdited = "";
            dispatchRecalc();
        }

        function clearPrice() { // CHANGED
            if (unitPriceInput.dataset.userEdited === "1") { // CHANGED
                dispatchRecalc(); // CHANGED
                return; // CHANGED
            } // CHANGED
            unitPriceInput.value = ""; // CHANGED
            unitPriceInput.dataset.userEdited = ""; // CHANGED
            dispatchRecalc(); // CHANGED
        }

        function normalizeProductId(rawId) { // CHANGED
            const value = String(rawId || "").trim(); // CHANGED
            if (!value) return ""; // CHANGED
            const match = value.match(/([0-9a-fA-F-]+)$/); // CHANGED
            return match ? match[1] : value; // CHANGED
        } // CHANGED

        function rememberMeta(productId, payload) { // CHANGED
            const normalizedId = normalizeProductId(productId); // CHANGED
            if (!normalizedId) return; // CHANGED
            const meta = productMetaCache[normalizedId] || {}; // CHANGED
            const url = payload?.image_url || payload?.imageUrl; // CHANGED
            const alt = payload?.image_alt || payload?.imageAlt || payload?.name; // CHANGED
            const stockRaw = payload?.quantity_in_stock ?? payload?.stock ?? payload?.quantity; // CHANGED
            if (Number.isFinite(stockRaw)) { // CHANGED
                meta.stock = Number(stockRaw); // CHANGED
            } else if (typeof stockRaw === "string" && stockRaw.trim().length) { // CHANGED
                const parsed = Number(stockRaw); // CHANGED
                if (Number.isFinite(parsed)) meta.stock = parsed; // CHANGED
            } // CHANGED
            if (url) meta.imageUrl = url; // CHANGED
            if (alt) meta.imageAlt = alt; // CHANGED
            productMetaCache[normalizedId] = meta; // CHANGED
        } // CHANGED

        function applyOptionImage(optionEl, meta) { // CHANGED
            if (!optionEl || !meta || !meta.imageUrl) return; // CHANGED
            if (optionEl.getAttribute("role") !== "option") return; // CHANGED
            if (optionEl.getAttribute("aria-disabled") === "true") return; // CHANGED
            let thumb = optionEl.querySelector("[data-option-thumb]"); // CHANGED
            if (!thumb) { // CHANGED
                thumb = document.createElement("span"); // CHANGED
                thumb.setAttribute("data-option-thumb", "1"); // CHANGED
                thumb.style.display = "inline-flex"; // CHANGED
                thumb.style.width = "28px"; // CHANGED
                thumb.style.height = "28px"; // CHANGED
                thumb.style.borderRadius = "6px"; // CHANGED
                thumb.style.overflow = "hidden"; // CHANGED
                thumb.style.marginRight = "8px"; // CHANGED
                thumb.style.verticalAlign = "middle"; // CHANGED
                thumb.style.boxShadow = "inset 0 0 0 1px rgba(0,0,0,0.06)"; // CHANGED
                thumb.style.background = "#f3f4f6"; // CHANGED
                optionEl.prepend(thumb); // CHANGED
            } // CHANGED
            let img = thumb.querySelector("img"); // CHANGED
            if (!img) { // CHANGED
                img = document.createElement("img"); // CHANGED
                img.style.width = "100%"; // CHANGED
                img.style.height = "100%"; // CHANGED
                img.style.objectFit = "cover"; // CHANGED
                img.loading = "lazy"; // CHANGED
                thumb.appendChild(img); // CHANGED
            } // CHANGED
            img.src = meta.imageUrl; // CHANGED
            img.alt = meta.imageAlt || "Product image"; // CHANGED
            optionEl.classList.add("has-thumb"); // CHANGED
            let stockBadge = optionEl.querySelector("[data-option-stock]"); // CHANGED
            if (!stockBadge) { // CHANGED
                stockBadge = document.createElement("span"); // CHANGED
                stockBadge.setAttribute("data-option-stock", "1"); // CHANGED
                stockBadge.style.marginLeft = "6px"; // CHANGED
                stockBadge.style.padding = "3px 8px"; // CHANGED
                stockBadge.style.borderRadius = "999px"; // CHANGED
                stockBadge.style.fontSize = "12px"; // CHANGED
                stockBadge.style.fontWeight = "600"; // CHANGED
                stockBadge.style.background = "#eef2ff"; // CHANGED
                stockBadge.style.color = "#4338ca"; // CHANGED
                stockBadge.style.verticalAlign = "middle"; // CHANGED
                optionEl.appendChild(stockBadge); // CHANGED
            } // CHANGED
            if (meta.stock !== undefined) { // CHANGED
                const out = Number(meta.stock) <= 0; // CHANGED
                stockBadge.textContent = out ? "Out of stock" : `${meta.stock} in stock`; // CHANGED
                stockBadge.style.background = out ? "#fef2f2" : "#eef2ff"; // CHANGED
                stockBadge.style.color = out ? "#b91c1c" : "#4338ca"; // CHANGED
                if (out) { // CHANGED
                    optionEl.style.backgroundColor = "#fff7f7"; // CHANGED
                } else { // CHANGED
                    optionEl.style.backgroundColor = ""; // CHANGED
                } // CHANGED
            } // CHANGED
        } // CHANGED

        function applyPreview(payload) {
            const preview = row.querySelector("[data-product-preview]");
            if (!preview) return;
            const thumb = preview.querySelector("[data-preview-thumb]");
            const img = preview.querySelector("[data-preview-image]");
            const placeholder = preview.querySelector("[data-preview-placeholder]");
            const stockNode = preview.querySelector("[data-preview-stock]");
            const payloadObj = (payload && typeof payload === "object") ? payload : {};
            const url = payloadObj.image_url || payloadObj.imageUrl || "";
            const alt =
                payloadObj.image_alt ||
                payloadObj.imageAlt ||
                (productField && productField.options && productField.selectedIndex >= 0
                    ? (productField.options[productField.selectedIndex].textContent || "").trim()
                    : "") ||
                "Product image";

            if (url) {
                if (img) {
                    img.src = url;
                    img.alt = alt || "Product image";
                    img.loading = img.loading || "lazy";
                }
                if (thumb) thumb.hidden = false;
                if (placeholder) placeholder.hidden = true;
                preview.classList.add("has-image");
            } else {
                if (img) {
                    img.removeAttribute("src");
                    img.alt = "";
                }
                if (thumb) thumb.hidden = true;
                if (placeholder) placeholder.hidden = false;
                preview.classList.remove("has-image");
            }
            if (stockNode) { // CHANGED
                const stockRaw = payloadObj.quantity_in_stock ?? payloadObj.stock ?? payloadObj.quantity; // CHANGED
                const stock = Number(stockRaw); // CHANGED
                if (Number.isFinite(stock)) { // CHANGED
                    const out = stock <= 0; // CHANGED
                    stockNode.textContent = out ? "Out of stock" : `${stock} in stock`; // CHANGED
                    if (out) { // CHANGED
                        stockNode.classList.add("is-out"); // CHANGED
                    } else { // CHANGED
                        stockNode.classList.remove("is-out"); // CHANGED
                    } // CHANGED
                } else { // CHANGED
                    stockNode.textContent = "—"; // CHANGED
                    stockNode.classList.remove("is-out"); // CHANGED
                } // CHANGED
            } // CHANGED
        }

        function buildUrl(productId) {
            try {
                const url = new URL(endpointRaw, window.location.origin);
                url.searchParams.set("product", productId);
                return url.toString();
            } catch (error) {
                console.warn("Invalid product price endpoint", error);
                return "";
            }
        }

        function nextPreviewSeq(productId) { // CHANGED
            const key = normalizeProductId(productId) || "_"; // CHANGED
            const current = previewRequestSeq[key] || 0; // CHANGED
            const next = current + 1; // CHANGED
            previewRequestSeq[key] = next; // CHANGED
            return next; // CHANGED
        } // CHANGED

        function isLatestPreview(productId, seq) { // CHANGED
            const key = normalizeProductId(productId) || "_"; // CHANGED
            return seq === previewRequestSeq[key]; // CHANGED
        } // CHANGED

        async function fetchAndApplyPrice(productId, seq, options = {}) {
            const normalizedId = normalizeProductId(productId); // CHANGED
            const url = buildUrl(productId);
            if (!url) return;
            const shouldApplyPrice = options.applyPrice !== false;
            const kind = options.kind || "price"; // CHANGED
            const onMeta = typeof options.onMeta === "function" ? options.onMeta : null; // CHANGED
            try {
                const response = await fetch(url, {
                    credentials: "same-origin",
                    headers: { "X-Requested-With": "XMLHttpRequest" },
                });
                if (!response.ok) {
                    throw new Error(`Request failed with status ${response.status}`);
                }
                let payload; // CHANGED
                const contentType = response.headers.get("content-type") || ""; // CHANGED
                if (contentType.includes("application/json")) { // CHANGED
                    payload = await response.json(); // CHANGED
                } else { // CHANGED
                    const textPayload = await response.text(); // CHANGED
                    try { // CHANGED
                        payload = JSON.parse(textPayload); // CHANGED
                    } catch { // CHANGED
                        payload = textPayload; // CHANGED
                    } // CHANGED
                } // CHANGED
                const isLatest =
                    kind === "preview" ? isLatestPreview(productId, seq) : seq === priceRequestSeq; // CHANGED
                if (kind === "preview" && normalizedId) { // CHANGED
                    pendingMeta.delete(normalizedId); // CHANGED
                } // CHANGED
                if (!isLatest) return; // CHANGED
                let value = null; // CHANGED
                if (typeof payload === "number" || typeof payload === "string") { // CHANGED
                    value = payload; // CHANGED
                } else if (payload && typeof payload === "object") { // CHANGED
                    value = payload.unit_price ?? payload.price ?? payload.value ?? null; // CHANGED
                } // CHANGED
                rememberMeta(productId, payload); // CHANGED
                if (kind === "preview" && normalizedId) { // CHANGED
                    pendingMeta.delete(normalizedId); // CHANGED
                } // CHANGED
                if (onMeta) onMeta(payload, productId); // CHANGED
                if (shouldApplyPrice && value !== null && value !== undefined && value !== "") {
                    applyPrice(value);
                }
                applyPreview(payload || {});
                productField.dataset.salePreviewInitialized = "1";
            } catch (error) {
                const isLatest =
                    kind === "preview" ? isLatestPreview(productId, seq) : seq === priceRequestSeq; // CHANGED
                if (kind === "preview" && normalizedId) { // CHANGED
                    pendingMeta.delete(normalizedId); // CHANGED
                } // CHANGED
                if (isLatest) { // CHANGED
                    console.warn("Unable to auto-fill product price", error);
                    applyPreview({});
                    productField.dataset.salePreviewInitialized = productField.dataset.salePreviewInitialized || "1";
                }
            }
        }

        function shouldSkipAutoFill(force, productChanged) { // CHANGED
            if (force || productChanged) return false; // CHANGED
            const hasValue = !!(unitPriceInput.value && unitPriceInput.value.trim().length);
            if (hasValue) return true;
            return unitPriceInput.dataset.userEdited === "1";
        }

        function syncPrice(force) {
            const productId = (productField.value || "").trim();
            const previousProductId = productField.dataset.salePriceLastProduct || ""; // CHANGED
            const wasInitialized = productField.dataset.salePriceInitialized === "1"; // CHANGED
            const previewInitialized = productField.dataset.salePreviewInitialized === "1";
            const productChanged = productId !== previousProductId; // CHANGED
            const hasUserValue = !!(unitPriceInput.value && unitPriceInput.value.trim()); // CHANGED

            if (productChanged && (wasInitialized || force)) { // CHANGED
                unitPriceInput.dataset.userEdited = ""; // CHANGED
            } // CHANGED

            productField.dataset.salePriceLastProduct = productId; // CHANGED
            productField.dataset.salePriceInitialized = "1"; // CHANGED

            if (!productId) {
                if (force || productChanged || !previewInitialized) { // CHANGED
                    clearPrice();
                    applyPreview(null);
                    productField.dataset.salePreviewInitialized = "";
                }
                return;
            }
            let allowPriceUpdate = !shouldSkipAutoFill(force, productChanged);
            if (!wasInitialized && !force && hasUserValue) {
                allowPriceUpdate = false;
            }
            const shouldFetchPreview = productChanged || force || !previewInitialized;
            const shouldFetchPrice = allowPriceUpdate || productChanged || !wasInitialized;

            if (!wasInitialized && !force && hasUserValue && !shouldFetchPreview) { // CHANGED
                return; // CHANGED
            } // CHANGED
            if (!shouldFetchPreview && !shouldFetchPrice) { // CHANGED
                return; // CHANGED
            } // CHANGED
            priceRequestSeq += 1; // CHANGED
            const seq = priceRequestSeq; // CHANGED
            fetchAndApplyPrice(productId, seq, { applyPrice: allowPriceUpdate, kind: "price" }); // CHANGED
            if (shouldFetchPreview) { // CHANGED
                const previewSeq = nextPreviewSeq(productId); // CHANGED
                fetchAndApplyPrice(productId, previewSeq, { applyPrice: false, kind: "preview" }); // CHANGED
            } // CHANGED
        }

        const handleSelection = () => syncPrice(true); // CHANGED
        productField.addEventListener("change", handleSelection);
        productField.addEventListener("input", handleSelection);

        let detachJq = null; // CHANGED
        let detachHover = null; // CHANGED
        let detachResultObserver = null; // CHANGED

        function hydrateOptionImages(optionsList) { // CHANGED
            if (!optionsList) return; // CHANGED
            const optionEls = optionsList.querySelectorAll('.select2-results__option[role="option"]'); // CHANGED
            optionEls.forEach((opt) => { // CHANGED
                const rawId = opt.getAttribute("data-select2-id") || opt.getAttribute("id"); // CHANGED
                const normalizedId = normalizeProductId(rawId); // CHANGED
                if (!normalizedId) return; // CHANGED
                const meta = productMetaCache[normalizedId]; // CHANGED
                if (meta && meta.imageUrl) { // CHANGED
                    applyOptionImage(opt, meta); // CHANGED
                    return; // CHANGED
                } // CHANGED
                if (pendingMeta.has(normalizedId)) return; // CHANGED
                pendingMeta.add(normalizedId); // CHANGED
                const seq = nextPreviewSeq(normalizedId); // CHANGED
                fetchAndApplyPrice(normalizedId, seq, { // CHANGED
                    applyPrice: false, // CHANGED
                    kind: "preview", // CHANGED
                    onMeta: () => { // CHANGED
                        pendingMeta.delete(normalizedId); // CHANGED
                        const cached = productMetaCache[normalizedId]; // CHANGED
                        if (cached) applyOptionImage(opt, cached); // CHANGED
                    }, // CHANGED
                }); // CHANGED
            }); // CHANGED
        } // CHANGED

        function bindDropdownImages(dropdownEl) { // CHANGED
            if (!dropdownEl) return; // CHANGED
            const resultsList = dropdownEl.querySelector(".select2-results__options"); // CHANGED
            hydrateOptionImages(resultsList); // CHANGED
            if (detachResultObserver) detachResultObserver(); // CHANGED
            const observer = new MutationObserver(() => hydrateOptionImages(resultsList)); // CHANGED
            if (resultsList) { // CHANGED
                observer.observe(resultsList, { childList: true, subtree: true }); // CHANGED
                detachResultObserver = () => observer.disconnect(); // CHANGED
            } else { // CHANGED
                detachResultObserver = null; // CHANGED
            } // CHANGED
        } // CHANGED

        function bindHoverPreview($field) { // CHANGED
            const ns = ".salePreviewHover"; // CHANGED
            const cleanup = () => { // CHANGED
                if (detachHover) { // CHANGED
                    detachHover(); // CHANGED
                    detachHover = null; // CHANGED
                } // CHANGED
            }; // CHANGED
            $field.off(`select2:open${ns} select2:close${ns}`); // CHANGED
            $field.on(`select2:close${ns}`, () => { // CHANGED
                cleanup(); // CHANGED
                productField.dataset.salePreviewHoverId = ""; // CHANGED
                if (detachResultObserver) { // CHANGED
                    detachResultObserver(); // CHANGED
                    detachResultObserver = null; // CHANGED
                } // CHANGED
                const selectedId = (productField.value || "").trim(); // CHANGED
                if (selectedId) { // CHANGED
                    const seq = nextPreviewSeq(selectedId); // CHANGED
                    fetchAndApplyPrice(selectedId, seq, { applyPrice: false, kind: "preview" }); // CHANGED
                } else { // CHANGED
                    applyPreview(null); // CHANGED
                } // CHANGED
            }); // CHANGED
            $field.on(`select2:open${ns}`, () => { // CHANGED
                cleanup(); // CHANGED
                const dropdown = document.querySelector(".select2-container--open"); // CHANGED
                bindDropdownImages(dropdown); // CHANGED
                // Delay to allow dropdown to render // CHANGED
                setTimeout(() => { // CHANGED
                    const dropdown = document.querySelector(".select2-container--open"); // CHANGED
                    const results = dropdown ? dropdown.querySelector(".select2-results__options") : null; // CHANGED
                    if (!results) return; // CHANGED
                    const handleHover = (event) => { // CHANGED
                        const option = event.target ? event.target.closest(".select2-results__option") : null; // CHANGED
                        if (!option) return; // CHANGED
                        const data = (jq && typeof jq === "function") ? jq(option).data("data") || {} : {}; // CHANGED
                        const productId = (data && (data.id || data.pk)) || option.getAttribute("data-select2-id") || ""; // CHANGED
                        const normalizedId = normalizeProductId(productId); // CHANGED
                        if (!normalizedId || normalizedId === productField.value) return; // CHANGED
                        if (normalizedId === productField.dataset.salePreviewHoverId) return; // CHANGED
                        productField.dataset.salePreviewHoverId = normalizedId; // CHANGED
                        const seq = nextPreviewSeq(normalizedId); // CHANGED
                        fetchAndApplyPrice(normalizedId, seq, { // CHANGED
                            applyPrice: false, // CHANGED
                            kind: "preview", // CHANGED
                            onMeta: () => { // CHANGED
                                const cached = productMetaCache[normalizedId]; // CHANGED
                                if (cached) applyOptionImage(option, cached); // CHANGED
                            }, // CHANGED
                        }); // CHANGED
                    }; // CHANGED
                    const handleLeave = () => { // CHANGED
                        productField.dataset.salePreviewHoverId = ""; // CHANGED
                    }; // CHANGED
                    results.addEventListener("mousemove", handleHover); // CHANGED
                    results.addEventListener("mouseenter", handleHover); // CHANGED
                    results.addEventListener("mouseleave", handleLeave); // CHANGED
                    detachHover = () => { // CHANGED
                        results.removeEventListener("mousemove", handleHover); // CHANGED
                        results.removeEventListener("mouseenter", handleHover); // CHANGED
                        results.removeEventListener("mouseleave", handleLeave); // CHANGED
                    }; // CHANGED
                }, 0); // CHANGED
            }); // CHANGED
        } // CHANGED

        if (jq && typeof jq === "function") { // CHANGED
            const $field = jq(productField); // CHANGED
            const events = ["select2:select", "autocompleteLightSelect", "autocompleteLightChange"]; // CHANGED
            if ($field.data("salePriceBindingAttached") !== true) { // CHANGED
                events.forEach(eventName => $field.on(eventName, handleSelection)); // CHANGED
                $field.data("salePriceBindingAttached", true); // CHANGED
            } // CHANGED
            bindHoverPreview($field); // CHANGED
            detachJq = () => { // CHANGED
                events.forEach(eventName => $field.off(eventName, handleSelection)); // CHANGED
                $field.removeData("salePriceBindingAttached"); // CHANGED
                $field.off(".salePreviewHover"); // CHANGED
                if (detachHover) { // CHANGED
                    detachHover(); // CHANGED
                    detachHover = null; // CHANGED
                } // CHANGED
                if (detachResultObserver) { // CHANGED
                    detachResultObserver(); // CHANGED
                    detachResultObserver = null; // CHANGED
                } // CHANGED
            }; // CHANGED
        }

        productField.dataset.salePriceFallbackBound = "1"; // CHANGED
        productField.__salePriceBinding = { // CHANGED
            unitPriceInput, // CHANGED
            handleSelection, // CHANGED
            detachJq, // CHANGED
            sync: syncPrice, // CHANGED
        }; // CHANGED

        syncPrice(false); // CHANGED
    }

    function refreshSaleClientDefaultFromAppointment() {
        if (!appointmentClientSelect || !SALE_DEFAULTS) return;
        const val = appointmentClientSelect.value;
        if (val) {
            const options = Array.from(appointmentClientSelect.options || []);
            const match = options.find(opt => opt.value === val);
            const label = match ? match.textContent.trim() : val;
            SALE_DEFAULTS.client = { id: val, label };
        } else {
            delete SALE_DEFAULTS.client;
        }
    }

    function addItem() {
        const tpl = $("#empty-form-tpl");
        if (!tpl) return;

        const idx = nextFormIndex();
        const fragment = tpl.content.cloneNode(true);
        const node = fragment.firstElementChild; // .ab-item

        replacePrefixAttributes(node, idx);
        initDefaultsForNewRow(node);

        // Вставка в DOM
        itemsContainer.appendChild(node);

        // Увеличиваем TOTAL_FORMS
        bumpTotalForms();

        // Инициализация строки (селекты, таймпикер и т.д.)
        initRow(node);
        recomputeAllTotals();
    }

    // Product sales helpers
    function salesTotalFormsEl() {
        return document.querySelector(`input[name="${SALES_PREFIX}-TOTAL_FORMS"]`);
    }
    function bumpSalesForms() {
        const totalEl = salesTotalFormsEl();
        if (totalEl) {
            totalEl.value = String(parseInt(totalEl.value || "0", 10) + 1);
        }
    }
    function nextSaleIndex() {
        const totalEl = salesTotalFormsEl();
        return totalEl ? parseInt(totalEl.value || "0", 10) : 0;
    }
    function initSaleRow(row) {
        if (!row) return;
        if (window.ProductSaleForm && typeof window.ProductSaleForm.enhanceScope === "function") {
            window.ProductSaleForm.enhanceScope(row);
        }
        const quantityInput = row.querySelector('input[name$="-quantity"]');
        const unitPriceInput = row.querySelector('input[name$="-unit_price"]');
        if (unitPriceInput && !unitPriceInput.dataset.productSaleRole) { // CHANGED
            unitPriceInput.setAttribute("data-product-sale-role", "unit-price"); // CHANGED
        } // CHANGED
        const deleteCheckbox = row.querySelector(`input[type="checkbox"][name$='-DELETE']`);
        const removeBtn = $(".js-sale-remove", row);
        ensureSalePriceBinding(row);
        const handleRecompute = () => {
            updateSaleSummary(row);
            recomputeAllTotals();
        };
        if (quantityInput) {
            quantityInput.addEventListener('input', handleRecompute);
            quantityInput.addEventListener('change', handleRecompute);
        }
        if (unitPriceInput) {
            unitPriceInput.addEventListener('input', handleRecompute);
            unitPriceInput.addEventListener('change', handleRecompute);
        }
        if (deleteCheckbox) {
            deleteCheckbox.addEventListener('change', () => {
                if (deleteCheckbox.checked) {
                    row.classList.add('ab-hidden');
                } else {
                    row.classList.remove('ab-hidden');
                }
                handleRecompute();
            });
        }
        if (removeBtn) {
            removeBtn.addEventListener('click', () => {
                if (deleteCheckbox) deleteCheckbox.checked = true;
                row.classList.add('ab-hidden');
                handleRecompute();
            });
        }
        handleRecompute();
    }
    function initExistingSales() {
        if (!salesContainer) return;
        $$(".ps-item", salesContainer).forEach(row => {
            applySaleDefaults(row);
            initSaleRow(row);
        });
    }
    function addProductSale() {
        if (!salesContainer) return;
        const tpl = document.getElementById("product-sale-empty-form");
        if (!tpl) return;
        const placeholder = salesContainer.querySelector(".ps-placeholder");
        if (placeholder) placeholder.remove();
        const idx = nextSaleIndex();
        const fragment = tpl.content.cloneNode(true);
        const node = fragment.firstElementChild;
        replacePrefixAttributes(node, idx);
        applySaleDefaults(node);
        salesContainer.appendChild(node);
        bumpSalesForms();
        if (window.django && window.django.jQuery) {
            window.django.jQuery(document).trigger("formset:added", [node, SALES_PREFIX]);
        } else if (window.jQuery) {
            window.jQuery(document).trigger("formset:added", [node, SALES_PREFIX]);
        }
        document.dispatchEvent(new CustomEvent("formset:added", { detail: { form: node, name: SALES_PREFIX } }));
        initSaleRow(node);
    }

    function initRefundMenu() {
        const refundBtn = document.getElementById("refund-btn");
        const refundMenu = document.getElementById("refund-menu");
        if (!refundBtn || !refundMenu) return;

        const hasRefunds = (refundBtn.dataset.hasRefunds || "").toLowerCase() === "true";
        if (!hasRefunds || refundBtn.disabled) {
            refundMenu.hidden = true;
            return;
        }

        const toggleMenu = (visible) => {
            refundMenu.hidden = !visible;
        };

        refundBtn.addEventListener("click", (event) => {
            event.preventDefault();
            toggleMenu(refundMenu.hidden);
        });

        document.addEventListener("click", (event) => {
            if (!refundMenu.contains(event.target) && !refundBtn.contains(event.target)) {
                toggleMenu(false);
            }
        });
    }

    function initPayMenu() {
        const cfg = window.APPOINTMENT_PAY || {};
        const payBtn = document.getElementById("pay-btn");
        const menu = document.getElementById("pay-menu");
        if (!payBtn || !menu) return;

        const csrfToken = (document.querySelector('input[name="csrfmiddlewaretoken"]') || {}).value || "";
        const getAppointmentId = () => {
            const raw = (payBtn.dataset.appointmentId || cfg.appointmentId || "").trim();
            if (!raw || raw.toLowerCase() === "none") return "";
            return raw;
        };
        const getAddPaymentUrl = () => payBtn.dataset.paymentAddUrl || cfg.addPaymentUrl || "";
        const getTerminalStartUrl = () => payBtn.dataset.terminalStartUrl || cfg.terminalStartUrl || "";
        const getTerminalConnUrl = () => payBtn.dataset.terminalConnUrl || cfg.terminalConnUrl || "";
        const getVerifyUrl = () => payBtn.dataset.paymentVerifyUrl || cfg.verifyUrl || "";
        const currentTotalAmount = () => {
            if (totalDisplay && totalDisplay.dataset.totalAmount) {
                return totalDisplay.dataset.totalAmount;
            }
            if (cfg.totalAmount && cfg.totalAmount !== "None") {
                return cfg.totalAmount;
            }
            if (!totalDisplay) return "";
            const raw = (totalDisplay.textContent || "").replace(/[^\d.,-]/g, "");
            return raw.replace(",", ".");
        };
        const getOutstandingAmount = () => {
            const raw =
                payBtn.dataset.amountDue ||
                cfg.outstandingAmount ||
                "";
            if (raw && String(raw).toLowerCase() !== "none") {
                return raw;
            }
            return currentTotalAmount();
        };

        const requireSavedAppointment = () => {
            const apptId = getAppointmentId();
            if (!apptId) {
                alert("Please save the appointment first.");
                return null;
            }
            return apptId;
        };

        const showMenu = (visible) => {
            menu.hidden = !visible;
        };

        payBtn.addEventListener("click", (event) => {
            event.preventDefault();
            showMenu(menu.hidden);
        });

        document.addEventListener("click", (event) => {
            if (!menu.contains(event.target) && !payBtn.contains(event.target)) {
                showMenu(false);
            }
        });

        function navigateToPaymentAdd(params) {
            const apptId = requireSavedAppointment();
            if (!apptId) return;
            const base = getAddPaymentUrl();
            if (!base) {
                alert("Payment form is unavailable.");
                return;
            }
            try {
                const url = new URL(base, window.location.origin);
                const query = {
                    appointment: apptId,
                    amount: getOutstandingAmount(),
                    ...params,
                };
                Object.entries(query).forEach(([key, value]) => {
                    if (value !== undefined && value !== null && String(value).length > 0) {
                        url.searchParams.set(key, value);
                    }
                });
                window.location.href = url.toString();
            } catch (err) {
                console.error(err);
            }
        }

        async function startTerminalPayment() {
            const apptId = requireSavedAppointment();
            if (!apptId) throw new Error("Please save the appointment first.");
            const url = getTerminalStartUrl();
            if (!url) {
                throw new Error("Terminal payment endpoint is unavailable.");
            }
            const response = await fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "X-CSRFToken": csrfToken,
                },
            });
            let payload = {};
            try {
                payload = await response.json();
            } catch (err) {
                console.error("Failed to parse terminal start payload", err);
            }
            if (!response.ok || payload.ok === false) {
                throw new Error(payload.error || "Failed to start terminal payment.");
            }
            if (!payload.client_secret || !payload.payment_intent_id) {
                throw new Error("Incomplete terminal payment response.");
            }
            if (payload.outstanding) {
                payBtn.dataset.amountDue = String(payload.outstanding);
            } else if (payload.amount) {
                payBtn.dataset.amountDue = String(payload.amount);
            }
            return payload;
        }

        async function getConnectionToken() {
            const url = getTerminalConnUrl();
            if (!url) {
                throw new Error("Terminal connection endpoint is unavailable.");
            }
            const response = await fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: { "Accept": "application/json" },
            });
            let payload = {};
            try {
                payload = await response.json();
            } catch (err) {
                console.error("Failed to parse connection token payload", err);
            }
            if (!response.ok || !payload.secret) {
                throw new Error(payload.error || "Unable to fetch connection token.");
            }
            return payload.secret;
        }

        let terminalInstance = null;
        let readerConnected = false;
        let paymentInFlight = false;

        async function discoverAndConnect(terminal) {
            const discover = async (options = {}) => {
                const discovery = await terminal.discoverReaders({
                    discoveryMethod: "internet",
                    ...options,
                });
                if (discovery.error) {
                    throw discovery.error;
                }
                return discovery.discoveredReaders || [];
            };

            let readers = await discover();
            if (!readers.length) {
                readers = await discover({ simulated: true });
            }
            if (!readers.length) {
                throw new Error("No Stripe Terminal readers found. Connect a reader or enable the simulator.");
            }
            const connectResult = await terminal.connectReader(readers[0]);
            if (connectResult.error) {
                throw connectResult.error;
            }
            return connectResult.reader;
        }

        async function ensureTerminalConnected() {
            if (!window.StripeTerminal) {
                throw new Error("StripeTerminal SDK is not loaded.");
            }
            if (!terminalInstance) {
                terminalInstance = window.StripeTerminal.create({
                    onFetchConnectionToken: () => getConnectionToken(),
                    onUnexpectedReaderDisconnect: () => {
                        readerConnected = false;
                        alert("Reader disconnected. Please reconnect before collecting payment.");
                    },
                });
            }
            if (!readerConnected) {
                await discoverAndConnect(terminalInstance);
                readerConnected = true;
            }
            return terminalInstance;
        }

        function applyFeePreview(serverAmount) {
            cardFeeApplied = true;
            payBtn.dataset.feeApplied = "true";
            if (typeof serverAmount !== "undefined" && serverAmount !== null) {
                payBtn.dataset.amountDue = String(serverAmount);
            }
            try {
                recomputeAllTotals();
            } catch (err) {
                console.warn("Failed to recompute totals", err);
            }
            if (!totalDisplay || typeof serverAmount === "undefined") {
                return;
            }
            const numeric = Number(serverAmount);
            if (!Number.isNaN(numeric)) {
                totalDisplay.textContent = money(numeric);
                totalDisplay.dataset.totalAmount = numeric.toFixed(2);
            }
        }

        async function processTerminalPayment(clientSecret) {
            const terminal = await ensureTerminalConnected();
            const collect = await terminal.collectPaymentMethod(clientSecret);
            if (collect.error) {
                throw collect.error;
            }
            const processed = await terminal.processPayment(collect.paymentIntent);
            if (processed.error) {
                throw processed.error;
            }
            return processed.paymentIntent;
        }

        async function verifyPayment(paymentIntentId) {
            const verifyUrl = getVerifyUrl();
            if (!verifyUrl || !paymentIntentId) {
                return;
            }
            try {
                const response = await fetch(verifyUrl, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "X-CSRFToken": csrfToken,
                    },
                    body: JSON.stringify({ payment_intent_id: paymentIntentId }),
                });
                if (!response.ok) {
                    const data = await response.json().catch(() => ({}));
                    throw new Error(data.error || `Verify failed (${response.status})`);
                }
            } catch (error) {
                console.warn("Verify failed (webhook will still update):", error);
            }
        }

        menu.addEventListener("click", async (event) => {
            const target = event.target.closest("[data-pay]");
            if (!target) return;
            event.preventDefault();
            showMenu(false);
            const mode = target.getAttribute("data-pay");
            if (mode === "cash" || mode === "etransfer") {
                navigateToPaymentAdd({ method_hint: mode, status_hint: "succeeded" });
                return;
            }
            if (mode === "card-credit" || mode === "card-debit") {
                const outstandingRaw = getOutstandingAmount();
                const outstandingValue = parseFloat(outstandingRaw || "0");
                if (!outstandingRaw || Number.isNaN(outstandingValue) || outstandingValue <= 0) {
                    alert("Appointment has no outstanding balance to charge.");
                    return;
                }
                if (paymentInFlight) {
                    alert("A terminal payment is already in progress.");
                    return;
                }
                paymentInFlight = true;
                const prevDisabled = payBtn.disabled;
                payBtn.disabled = true;
                try {
                    const session = await startTerminalPayment();
                    applyFeePreview(session.amount);
                    await processTerminalPayment(session.client_secret);
                    await verifyPayment(session.payment_intent_id);
                    window.location.reload();
                } catch (error) {
                    console.error(error);
                    alert(error && error.message ? error.message : "Terminal payment failed");
                } finally {
                    paymentInFlight = false;
                    payBtn.disabled = prevDisabled;
                }
            }
        });
    }

    // вкладки
    function initTabs() {
        const tabs = $$(".tab");
        const panels = $$(".tab-panel");

        const activateTab = (id) => {
            if (!id) return;
            tabs.forEach(tab => {
                const tabId = tab.getAttribute("data-tab");
                const isActive = tabId === id;
                tab.classList.toggle("active", isActive);
            });
            panels.forEach(panel => {
                const panelId = panel.getAttribute("data-tab-panel");
                const isActive = panelId === id;
                panel.classList.toggle("active", isActive);
            });
        };

        const syncHash = (id) => {
            if (!("replaceState" in history)) {
                return;
            }
            const base = `${window.location.pathname}${window.location.search}`;
            if (!id || id === "details") {
                history.replaceState(null, "", base);
            } else {
                history.replaceState(null, "", `${base}#${id}`);
            }
        };

        tabs.forEach(tab => tab.addEventListener("click", () => {
            const id = tab.getAttribute("data-tab");
            activateTab(id);
            syncHash(id);
        }));

        const initialHash = window.location.hash ? window.location.hash.slice(1) : "";
        if (initialHash) {
            const targetExists = tabs.some(tab => tab.getAttribute("data-tab") === initialHash);
            if (targetExists) {
                activateTab(initialHash);
                return;
            }
        }

        const defaultTab = tabs.find(tab => tab.classList.contains("active"));
        if (defaultTab) {
            activateTab(defaultTab.getAttribute("data-tab"));
        } else if (tabs.length) {
            activateTab(tabs[0].getAttribute("data-tab"));
        }
    }
    function stripDateTimeLabels(root = document) {
        if (!root) return;
        root.querySelectorAll("p.datetime").forEach(p => {
            p.classList.add("js-datetime-wrapper");
        });
        root.querySelectorAll(".js-datetime-wrapper").forEach(wrapper => {
            wrapper.querySelectorAll("br").forEach(br => br.remove());
            wrapper.querySelectorAll(".datetimeshortcuts").forEach(el => el.remove());
            Array.from(wrapper.childNodes).forEach(node => {
                if (node.nodeType === Node.TEXT_NODE) {
                    const cleaned = node.textContent.replace(/\bDate:\s*/i, "").replace(/\bTime:\s*/i, "");
                    if (cleaned.trim()) {
                        node.textContent = cleaned;
                    } else {
                        node.remove();
                    }
                }
            });
            wrapper.querySelectorAll("label").forEach(label => label.remove());
            wrapper.querySelectorAll("input").forEach(input => {
                if (!input.classList.contains("ab-input")) {
                    input.classList.add("ab-input");
                }
                if (input.name && input.name.endsWith("_0")) {
                    try { input.type = "date"; } catch (err) { /* ignore */ }
                }
                if (input.name && input.name.endsWith("_1")) {
                    try { input.type = "time"; } catch (err) { /* ignore */ }
                    input.setAttribute("step", "900");
                }
            });
        });
    }

    function initAutoPhotoUpload() {
        const mainForm = document.querySelector(".ab-wrap form");
        if (!mainForm) return;
        const uploadButton = mainForm.querySelector("[data-photo-upload-submit]");
        if (!uploadButton || !uploadButton.getAttribute("formaction")) return;
        const fileInput = mainForm.querySelector("input[type='file'][name$='-files']");
        if (!fileInput) return;
        const statusEl = mainForm.querySelector("[data-photo-upload-status]");

        let autoSubmitting = false;

        const setStatus = (text) => {
            if (!statusEl) return;
            statusEl.textContent = text || "";
            if (text) {
                statusEl.hidden = false;
                statusEl.dataset.state = "uploading";
            } else {
                statusEl.hidden = true;
                statusEl.removeAttribute("data-state");
            }
        };

        const triggerSubmit = () => {
            if (typeof mainForm.requestSubmit === "function") {
                mainForm.requestSubmit(uploadButton);
            } else if (typeof uploadButton.click === "function") {
                uploadButton.click();
            } else {
                mainForm.submit();
            }
        };

        fileInput.addEventListener("change", () => {
            if (autoSubmitting) return;
            if (!fileInput.files || fileInput.files.length === 0) return;
            autoSubmitting = true;
            setStatus("Uploading photos...");
            triggerSubmit();
        });

        window.addEventListener("pageshow", () => {
            autoSubmitting = false;
            setStatus("");
        });
    }
    document.addEventListener("DOMContentLoaded", () => {
        initToastSystem();
        refreshSaleClientDefaultFromAppointment();
        if (appointmentClientSelect) {
            appointmentClientSelect.addEventListener("change", refreshSaleClientDefaultFromAppointment);
        }
        cardFeeApplied = initialFeeAppliedState();
        initExistingRows();
        initExistingSales();
        recomputeAllTotals();
        initTabs();
        stripDateTimeLabels(document);
        initAutoPhotoUpload();
        const btnAdd = $("#btn-add-item");
        if (btnAdd) btnAdd.addEventListener("click", addItem);
        const btnAddSale = document.getElementById("btn-add-product-sale");
        if (btnAddSale) btnAddSale.addEventListener("click", addProductSale);
        // при с   абмите — убедимся, что все disabled реальные поля имеют hidden-клоны
        const containerForm = itemsContainer ? itemsContainer.closest("form") : (salesContainer ? salesContainer.closest("form") : null);
        const form = containerForm;
        if (form) {
            form.addEventListener("submit", () => {
                if (itemsContainer) {
                    $$(".ab-item", itemsContainer).forEach(row => {

                        syncRowToNative(row);
                        if (row.classList.contains("readonly")) {
                            const nativeStartDate = $("[name$='-start_time_0']", row);
                            const nativeStartTime = $("[name$='-start_time_1']", row);
                            const nativePrice = $("[name$='-unit_price']", row);
                            if (nativeStartDate) ensureHiddenClone(nativeStartDate);
                            if (nativeStartTime) ensureHiddenClone(nativeStartTime);
                            if (nativePrice)     ensureHiddenClone(nativePrice);
                        }

                        // master всегда не редактируем: UI disabled, но нативное поле активно — ничего делать не нужно
                    });
                }
            });
        }
        const container = document.getElementById('items-container');
        if (container) {
            const mo = new MutationObserver(muts => {
                muts.forEach(m => m.addedNodes.forEach(node => {
                    if (node.nodeType === 1) stripDateTimeLabels(node);
                }));
            });
            mo.observe(container, { childList: true, subtree: true });
        }
        document.querySelectorAll(".ab-item").forEach(initItemStatusControls);
        if (salesContainer) { // CHANGED
            const salesObserver = new MutationObserver(mutations => { // CHANGED
                mutations.forEach(mutation => { // CHANGED
                    mutation.addedNodes.forEach(node => { // CHANGED
                        if (node.nodeType !== 1) return; // CHANGED
                        if (node.classList.contains("ps-item")) { // CHANGED
                            applySaleDefaults(node); // CHANGED
                            initSaleRow(node); // CHANGED
                            return; // CHANGED
                        } // CHANGED
                        $$(".ps-item", node).forEach(child => { // CHANGED
                            applySaleDefaults(child); // CHANGED
                            initSaleRow(child); // CHANGED
                        }); // CHANGED
                    }); // CHANGED
                }); // CHANGED
            }); // CHANGED
            salesObserver.observe(salesContainer, { childList: true }); // CHANGED
        } // CHANGED
        document.addEventListener("formset:added", evt => {
            const node = evt && evt.detail && evt.detail.form;
            if (!node || !node.classList) return;
            if (node.classList.contains("ab-item")) {
                initItemStatusControls(node);
            } // CHANGED
            if (node.classList.contains("ps-item")) { // CHANGED
                applySaleDefaults(node); // CHANGED
                initSaleRow(node); // CHANGED
            }
        });
        const deleteButton = document.getElementById("delete-appointment-btn");
        if (deleteButton) {
            deleteButton.addEventListener("click", () => {
                const message = deleteButton.dataset.confirmMessage
                    || "Are you sure you want to delete this appointment?";
                if (!window.confirm(message)) {
                    return;
                }
                const target = deleteButton.dataset.deleteUrl;
                if (target) {
                    window.location.href = target;
                }
            });
        }
        initRefundMenu();
        initPayMenu();
    });

})();
