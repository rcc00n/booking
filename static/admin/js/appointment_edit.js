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

    const $ = (sel, root = document) => root.querySelector(sel);
    const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

    const itemsContainer = $("#items-container");
    if (!itemsContainer) return;

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
            select.appendChild(opt);
        }
        select.value = val;
    }
    function populateMasters(uiSelect) {
           uiSelect.innerHTML = "";
           // всегда показываем всех — нужно корректно отрисовать чужие строки
            (MASTERS || []).forEach(m => uiSelect.appendChild(buildOption(m.id, m.name || m.label || String(m.id))));
        }

    function populateServices(uiSelect, masterId) {
        uiSelect.innerHTML = "";
        const list = MS_MAP[String(masterId)] || [];
        list.forEach(s => uiSelect.appendChild(buildOption(s.id, s.name)));
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
        const nativeStart  = $("[name$='-start_time']", row);   // реальное поле
        const nativePrice  = $("[name$='-unit_price']", row);   // реальное поле
        const delWrap      = $(".js-del-wrap", row);
        const roBadge      = $(".js-ro-badge", row);

        // наполним мастеров и выставим значения
        populateMasters(uiMaster);

        // не трогаем значение master у существующих строк; просто отражаем его в UI
        if (nativeMaster && uiMaster) uiMaster.value = String(nativeMaster.value || "");
        // мастер не может менять мастера
        if (IS_MASTER && uiMaster) uiMaster.disabled = true;

        // услуги исходя из мастер-id
        const effectiveMasterId = (nativeMaster ? nativeMaster.value : (uiMaster ? uiMaster.value : ""));
        populateServices(uiSvc, effectiveMasterId);
        if (nativeSvc && nativeSvc.value) uiSvc.value = String(nativeSvc.value);
        mirrorOptions(nativeSvc, uiSvc);


// после того как uiSvc.value задан — протолкнём в native

        const label = uiSvc.selectedOptions?.[0]?.textContent || "";
        setSelectValueEnsuringOption(nativeSvc, uiSvc.value, label);


// при изменении сервиса пользователем: и в native опции/значение
        uiSvc.addEventListener("change", () => {
            mirrorOptions(nativeSvc, uiSvc);
            const label = uiSvc.selectedOptions?.[0]?.textContent || "";
            setSelectValueEnsuringOption(nativeSvc, uiSvc.value, label);
            // и пересобрать промокоды UI (как было у тебя)
            if (typeof populatePromos === "function") {
                populatePromos(uiPromo, uiSvc.value);
            }
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
                });

                // промо в нативу
                if (nativePromo) {
                    uiPromo.addEventListener("change", () => { nativePromo.value = uiPromo.value; });
                }
                if (promoForceUI) {
                    const nativeForce = $(".native-promocode input[name$='-force_apply']", row);
                    promoForceUI.addEventListener("change", () => { if (nativeForce) nativeForce.checked = !!promoForceUI.checked; });
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
            });
            uiSvc.disabled = false;
            uiSvc.addEventListener("change", () => {
                if (nativeSvc) nativeSvc.value = uiSvc.value;
                populatePromos(uiPromo, uiSvc.value);
            });
            if (nativePromo) {
                uiPromo.disabled = false;
                uiPromo.addEventListener("change", () => { nativePromo.value = uiPromo.value; });
            }
        }
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
    }
    // вкладки
    function initTabs() {
        const tabs = $$(".tab");
        const panels = $$(".tab-panel");
        tabs.forEach(t => t.addEventListener("click", () => {
            tabs.forEach(x => x.classList.remove("active"));
            panels.forEach(p => p.classList.remove("active"));
            t.classList.add("active");
            const id = t.getAttribute("data-tab");
            const panel = $(`.tab-panel[data-tab-panel="${id}"]`);
            if (panel) panel.classList.add("active");
        }));
    }
    function stripDateTimeLabels(root=document){
        root.querySelectorAll('p.datetime').forEach(p => {
            // убрать <br>
            [...p.querySelectorAll('br')].forEach(br => br.remove());
            // убрать текстовые узлы "Date:" / "Time:"
            [...p.childNodes].forEach(n => {
                if (n.nodeType === Node.TEXT_NODE) {
                    const t = n.textContent.replace(/\bDate:\s*/i, '').replace(/\bTime:\s*/i, '');
                    if (t.trim().length === 0) {
                        n.remove();
                    } else {
                        n.textContent = t;
                    }
                }
            });
        });
    }
    document.addEventListener("DOMContentLoaded", () => {
        initExistingRows();
        initTabs();
        stripDateTimeLabels(document);
        const btnAdd = $("#btn-add-item");
        if (btnAdd) btnAdd.addEventListener("click", addItem);
        // при с   абмите — убедимся, что все disabled реальные поля имеют hidden-клоны
        const form = itemsContainer.closest("form");
        if (form) {
            form.addEventListener("submit", () => {
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
    });

})();
