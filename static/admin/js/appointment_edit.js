(function(){
    /* Tabs */
    const tabs = document.getElementById('tabs');
    function switchTab(name){
        document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab===name));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.dataset.tabPanel===name));
        try { localStorage.setItem('appt_tab', name); } catch(e){}
    }
    tabs.addEventListener('click',(e)=>{
        const btn=e.target.closest('.tab'); if(!btn) return;
        switchTab(btn.dataset.tab);
    });
    switchTab(localStorage.getItem('appt_tab') || 'details');

    /* Data */
    const masters = JSON.parse(document.getElementById('masters-data').textContent || '[]');
    const msMap  = JSON.parse(document.getElementById('ms-map-data').textContent || '{}');
    const svcDisc = JSON.parse(document.getElementById('svc-discounts-data').textContent || '{}');
    const promosByService = JSON.parse(document.getElementById('promos-by-service-data').textContent || '{}');
    const promosGlobal = JSON.parse(document.getElementById('promos-global-data').textContent || '[]');

    const container = document.getElementById('items-container');
    const addBtn = document.getElementById('btn-add-item');
    const totalInput = document.getElementById('id_items-TOTAL_FORMS');

    /* Helpers */
    function fillSelect(el, options, placeholder) {
        el.innerHTML = "";
        if (placeholder) {
            const opt0 = document.createElement('option');
            opt0.value = ""; opt0.textContent = placeholder;
            el.appendChild(opt0);
        }
        options.forEach(o=>{
            const opt=document.createElement('option');
            opt.value=o.id; opt.textContent=o.name||o.text;
            if(o.discount!=null) opt.setAttribute('data-discount', String(o.discount));
            if(o.base_price!=null) opt.setAttribute('data-base-price', String(o.base_price));
            el.appendChild(opt);
        });
    }
    function findNative(itemBox, cls) {
        const wrap = itemBox.querySelector('.' + cls);
        return wrap ? wrap.querySelector('select,input,textarea') : null;
    }
    function findNativePromo(itemBox){
        const wrap = itemBox.querySelector('.native-promocode');
        if(!wrap) return null;
        return wrap.querySelector('select[name$="-promocode"],input[name$="-promocode"]');
    }
    function findNativePromoForce(itemBox){
        const wrap = itemBox.querySelector('.native-promocode');
        if(!wrap) return null;
        return wrap.querySelector('input[type="checkbox"]');
    }
    function setNativeValue(input, value) {
        if (!input) return;
        input.value = value || "";
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }
    function setNativeChecked(input, checked){
        if(!input) return;
        input.checked = !!checked;
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }
    function priceToNumber(v){
        if (typeof v === "number") return v;
        v = (v || "").toString().replace(",", ".");
        const n = parseFloat(v);
        return isFinite(n) ? n : 0;
    }
    function formatMoney(n){
        return '$' + (Math.round(n*100)/100).toFixed(2);
    }
    const personalPct = (() => {
        const el = document.getElementById('id_personal_discount_percent');
        if (!el) return 0;
        const raw = (el.value || el.textContent || '0').toString();
        const v = parseFloat(raw.replace(/[^\d.]/g, '')) || 0;
        return Math.max(0, Math.min(100, v));
    })();
    /* Totals */
    // function recomputeItemTotal(itemBox){
    //     const serviceSel = itemBox.querySelector('.js-service');
    //     const priceInput = itemBox.querySelector('input[name$="-unit_price"]');
    //     const totalEl = itemBox.querySelector('.js-item-total');
    //     if (!serviceSel || !totalEl) return;
    //
    //     const svcOpt = serviceSel.options[serviceSel.selectedIndex];
    //     const basePrice = svcOpt ? priceToNumber(svcOpt.getAttribute('data-base-price')) : 0;
    //     const entered = priceToNumber(priceInput ? priceInput.value : 0);
    //     let price = entered > 0 ? entered : basePrice;
    //
    //     let disc = 0;
    //     const serviceId = serviceSel.value || "";
    //     if (serviceId && svcDisc[serviceId]) disc = Math.max(disc, parseInt(svcDisc[serviceId], 10) || 0);
    //
    //     const promoSel = itemBox.querySelector('.js-promocode');
    //     if (promoSel && promoSel.value){
    //         const opt = promoSel.options[promoSel.selectedIndex];
    //         const pct = parseInt(opt.getAttribute('data-discount')||'0', 10) || 0;
    //         disc = Math.max(disc, pct);
    //     }
    //
    //     // ИТОГ ПОЗИЦИИ — без персональной
    //     const final = price * (100 - disc) / 100;
    //
    //     // Пишем текст и сохраняем "сырое" число для grand total
    //     totalEl.textContent = formatMoney(final);
    //     totalEl.dataset.raw = String(final);
    //
    //     recomputeGrandTotal(); // ← добавили
    // }
    // function recomputeGrandTotal(){
    //     const totals = Array.from(document.querySelectorAll('.js-item-total'));
    //     const subtotal = totals.reduce((s, el) => {
    //         const raw = el.dataset.raw || el.textContent.replace(/[^\d.]/g, '');
    //         return s + (parseFloat(raw) || 0);
    //     }, 0);
    //     console.log(personalPct);
    //     const withPersonal = subtotal * (100 - (personalPct || 0)) / 100;
    //     console.log("Total Price:");
    //     console.log(withPersonal);
    //     const grandEl = document.getElementById('grand-total');
    //     if (grandEl) grandEl.textContent = formatMoney(withPersonal);
    //
    //     // опционально: показывать подсказку «−X% personal»
    //     const badge = document.getElementById('personal-discount-badge');
    //     if (badge) badge.textContent = personalPct ? `−${personalPct}% personal` : '';
    // }
    /* Date/Time enhancers */
    function enhanceTimeInput(timeInput){
        if (!timeInput || timeInput.dataset.enhanced) return;
        timeInput.dataset.enhanced = '1';
        timeInput.classList.add('ab-hidden');

        const sel = document.createElement('select');
        sel.className = 'ab-select js-timepicker';
        for(let h=0; h<24; h++){
            for(let m=0; m<60; m+=15){
                const v = String(h).padStart(2,'0') + ':' + String(m).padStart(2,'0') + ':00';
                const opt = document.createElement('option');
                opt.value = v; opt.textContent = v.slice(0,5);
                sel.appendChild(opt);
            }
        }
        // set initial
        if (timeInput.value){
            const val = timeInput.value.length===5 ? (timeInput.value+':00') : timeInput.value;
            if ([...sel.options].some(o=>o.value===val)) sel.value = val;
        }
        timeInput.parentNode.insertBefore(sel, timeInput.nextSibling);
        sel.addEventListener('change', ()=>{
            timeInput.value = sel.value;
            timeInput.dispatchEvent(new Event('change',{bubbles:true}));
        });
    }
    function enhanceDateInput(dateInput){
        if (!dateInput) return;
        try { dateInput.type = 'date'; } catch(e){}
    }
    function enhanceDateTimeIn(scope){
        // Appointment main form or item row
        const dateInputs = scope.querySelectorAll('input[name="start_time_0"], input[name$="-start_time_0"]');
        const timeInputs = scope.querySelectorAll('input[name="start_time_1"], input[name$="-start_time_1"]');
        dateInputs.forEach(enhanceDateInput);
        timeInputs.forEach(enhanceTimeInput);
    }

    /* UI handlers */
    function rebuildPromos(itemBox){
        const serviceSel = itemBox.querySelector('.js-service');
        const promoSel = itemBox.querySelector('.js-promocode');
        const nativePromo = findNativePromo(itemBox);
        if (!promoSel) return;

        const sid = serviceSel.value || "";
        const list = []
            .concat(promosByService[sid] || [])
            .concat(promosGlobal || [])
            .filter((x,i,arr)=>arr.findIndex(y=>y.id===x.id)===i);

        fillSelect(promoSel, list, list.length ? "Select promo…" : "No promos");
        promoSel.disabled = list.length===0;

        if (nativePromo && nativePromo.value){
            if (list.some(p=>p.id===nativePromo.value)) promoSel.value = nativePromo.value;
            else promoSel.value = "";
        }
    }

    function onMasterChange(itemBox){
        const nativeMaster = findNative(itemBox, 'native-master');
        const nativeService = findNative(itemBox, 'native-service');
        const masterSel = itemBox.querySelector('.js-master');
        const serviceSel = itemBox.querySelector('.js-service');

        const masterId = masterSel.value || "";
        setNativeValue(nativeMaster, masterId);

        const services = msMap[masterId] || [];
        fillSelect(serviceSel, services, services.length ? "Select service…" : "No services");
        serviceSel.disabled = services.length === 0;

        const prev = nativeService ? nativeService.value : "";
        const still = services.some(s => s.id === prev);
        if (still) { serviceSel.value = prev; }
        else { serviceSel.value = ""; setNativeValue(nativeService, ""); }

        rebuildPromos(itemBox);
    }

    function onServiceChange(itemBox){
        const nativeService = findNative(itemBox, 'native-service');
        const serviceSel = itemBox.querySelector('.js-service');
        const priceInput = itemBox.querySelector('input[name$="-unit_price"]');

        const sid = serviceSel.value || "";
        setNativeValue(nativeService, sid);

        const opt = serviceSel.options[serviceSel.selectedIndex];
        const base = opt ? (opt.getAttribute('data-base-price') || "") : "";
        if (priceInput && (priceInput.value === "" || Number(priceInput.value) === 0)) {
            priceInput.value = base;
        }

        rebuildPromos(itemBox);
    }

    function onPromoChange(itemBox){
        const promoSel = itemBox.querySelector('.js-promocode');
        const nativePromo = findNativePromo(itemBox);
        setNativeValue(nativePromo, promoSel ? promoSel.value : "");
    }

    function onPromoForceChange(itemBox){
        const fake = itemBox.querySelector('.js-promo-force');
        const native = findNativePromoForce(itemBox);
        setNativeChecked(native, fake ? fake.checked : false);
    }

    function initItem(itemBox){
        const nativeMaster = findNative(itemBox, 'native-master');
        const nativeService = findNative(itemBox, 'native-service');

        const masterSel = itemBox.querySelector('.js-master');
        const serviceSel = itemBox.querySelector('.js-service');
        const promoSel = itemBox.querySelector('.js-promocode');
        const promoForce = itemBox.querySelector('.js-promo-force');
        const unitPrice = itemBox.querySelector('input[name$="-unit_price"]');

        // master list
        fillSelect(masterSel, masters, "Select master…");
        if (nativeMaster && nativeMaster.value) masterSel.value = nativeMaster.value;

        masterSel.addEventListener('change', ()=>onMasterChange(itemBox));
        serviceSel.addEventListener('change', ()=>onServiceChange(itemBox));
        if (promoSel) promoSel.addEventListener('change', ()=>onPromoChange(itemBox));
        if (promoForce) promoForce.addEventListener('change', ()=>onPromoForceChange(itemBox));

        // enhance date/time in this row
        enhanceDateTimeIn(itemBox);

        // initial fill
        onMasterChange(itemBox);
        if (nativeService && nativeService.value){
            serviceSel.value = nativeService.value;
            onServiceChange(itemBox);
        }

        const nativePromo = findNativePromo(itemBox);
        if (promoSel && nativePromo && nativePromo.value){
            promoSel.value = nativePromo.value;
        }
        const nativeForce = findNativePromoForce(itemBox);
        if (promoForce && nativeForce) promoForce.checked = !!nativeForce.checked;

    }

    /* init existing rows + main form date/time */
    container.querySelectorAll('.ab-item').forEach(initItem);
    enhanceDateTimeIn(document);  // main appointment start_time (details tab)

    /* add new row */
    function nextIndex(){ return container.querySelectorAll('.ab-item').length; }
    function addItem(){
        const idx = nextIndex();
        const tpl = document.getElementById('empty-form-tpl').innerHTML.replaceAll('__prefix__', idx);
        const wrap = document.createElement('div'); wrap.innerHTML = tpl.trim();
        const node = wrap.firstElementChild;
        container.appendChild(node);
        if (totalInput) totalInput.value = String(idx + 1);
        initItem(node);
    }
    addBtn && addBtn.addEventListener('click', addItem);

})();