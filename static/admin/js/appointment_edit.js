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
            const raw = (timeEl.value || "").trim();
            const val = raw.length > 5 ? raw.slice(0, 5) : raw;
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

        function buildSlotButton(slotIso) {
            const dt = parseIsoSlot(slotIso);
            if (!dt) return null;
            const label = formatSlotLabel(dt);
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "ab-timeslots__btn";
            btn.dataset.iso = slotIso;
            btn.dataset.time = label;
            btn.setAttribute("role", "option");
            btn.setAttribute("aria-selected", "false");
            btn.textContent = label;
            btn.addEventListener("click", () => {
                activateButton(btn);
                updateInput(label, slotIso, true);
                setStatus("ready", `Selected ${label}`);
            });
            return btn;
        }

        function renderSlots(slots) {
            grid.innerHTML = "";
            if (!Array.isArray(slots) || !slots.length) {
                clearSelection({ emit: true });
                setStatus("empty", "No available slots for this date.");
                return;
            }
            slots.forEach(iso => {
                const btn = buildSlotButton(iso);
                if (btn) grid.appendChild(btn);
            });
            const highlighted = highlightCurrent();
            if (timeEl.value && !highlighted) {
                clearSelection({ emit: true });
                setStatus("warning", "Previous time is no longer available. Please choose another slot.");
                return;
            }
            if (highlighted) {
                const label = highlighted.dataset.time || "";
                const count = grid.querySelectorAll(".ab-timeslots__btn").length;
                const suffix = count > 1 ? ` · ${count - 1} more` : "";
                setStatus("ready", `Selected ${label}${suffix}`);
            } else {
                const count = grid.querySelectorAll(".ab-timeslots__btn").length;
                const info = count === 1 ? "1 available slot" : `${count} available slots`;
                setStatus("ready", info);
            }
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
        const deleteCheckbox = row.querySelector(`input[type="checkbox"][name$='-DELETE']`);
        const removeBtn = $(".js-sale-remove", row);
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
    document.addEventListener("DOMContentLoaded", () => {
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
        document.addEventListener("formset:added", evt => {
            const node = evt && evt.detail && evt.detail.form;
            if (!node || !node.classList) return;
            if (node.classList.contains("ab-item")) {
                initItemStatusControls(node);
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
