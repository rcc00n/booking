document.addEventListener('DOMContentLoaded', () => {
  const I18N = window.MalvaI18n;
  let refreshPending = false;
  const queueRefresh = () => {
    if (!I18N || typeof I18N.refresh !== 'function' || refreshPending) return;
    refreshPending = true;
    window.requestAnimationFrame(() => {
      refreshPending = false;
      I18N.refresh({ silent: true });
    });
  };
  const translate = (key, vars, fallback) => {
    if (!key) return fallback || '';
    if (I18N) {
      try {
        return I18N.t(key, vars);
      } catch (err) {
        return fallback !== undefined ? fallback : key;
      }
    }
    return fallback !== undefined ? fallback : key;
  };
  const setTextKey = (el, key, vars, fallback) => {
    if (!el) return;
    if (I18N && key) {
      el.setAttribute('data-i18n', key);
      if (vars) {
        el.setAttribute('data-i18n-vars', JSON.stringify(vars));
      } else {
        el.removeAttribute('data-i18n-vars');
      }
      queueRefresh();
    } else if (fallback !== undefined) {
      el.textContent = fallback;
    }
  };
  const clearTextKey = (el) => {
    if (!el) return;
    el.removeAttribute('data-i18n');
    el.removeAttribute('data-i18n-vars');
  };
  const getLocale = () => (I18N && typeof I18N.getLocale === 'function'
    ? I18N.getLocale()
    : (navigator.languages && navigator.languages[0]) || navigator.language || 'en');
  const translateServiceNameText = (name) => {
    if (!name) return '';
    if (I18N && typeof I18N.translateServiceName === 'function') {
      return I18N.translateServiceName(name);
    }
    return name;
  };
  const applyServiceNameTranslations = (root) => {
    const scope = root || document;
    scope.querySelectorAll('[data-service-name-original]').forEach((el) => {
      const original = el.getAttribute('data-service-name-original') || el.textContent;
      if (!original) return;
      el.textContent = translateServiceNameText(original) || original;
    });
  };

  function parseUtc(iso) {
    const d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }
  const lockClickHandlers = new WeakMap();
  function enforce24hLock(root = document) {
    const scope = root && typeof root.querySelectorAll === 'function' ? root : document;
    const now = new Date();
    const items = scope.querySelectorAll('.appointment-item[data-appt-start-iso]');
    items.forEach((item) => {
      const iso = item.getAttribute('data-appt-start-iso');
      const start = parseUtc(iso);
      if (!start) return;

      const msLeft = start.getTime() - now.getTime();
      const within24h = msLeft < 24 * 60 * 60 * 1000;

      const cancelBtn = item.querySelector('.appt-cancel');
      const reschedBtn = item.querySelector('.appt-reschedule');

      [cancelBtn, reschedBtn].forEach((btn) => {
        if (!btn) return;
        const handler = lockClickHandlers.get(btn);
        if (within24h) {
          btn.setAttribute('disabled', 'disabled');
          btn.setAttribute('aria-disabled', 'true');
          btn.classList.add('is-disabled');
          if (!handler) {
            const prevent = (event) => {
              event.preventDefault();
            };
            btn.addEventListener('click', prevent);
            lockClickHandlers.set(btn, prevent);
          }
        } else {
          btn.removeAttribute('disabled');
          btn.removeAttribute('aria-disabled');
          btn.classList.remove('is-disabled');
          if (handler) {
            btn.removeEventListener('click', handler);
            lockClickHandlers.delete(btn);
          }
        }
      });
    });
  }
  function observeAppointments(){
    const host = document.getElementById('upcomingAppointments');
    if (!host || !('MutationObserver' in window)) return;
    const mo = new MutationObserver(() => {
      window.requestAnimationFrame(() => enforce24hLock(host));
    });
    mo.observe(host, { childList: true, subtree: true });
  }

  enforce24hLock();
  observeAppointments();
  document.addEventListener('appointments:render', (event) => {
    const detail = event && event.detail && event.detail.root;
    if (detail && typeof detail.querySelectorAll === 'function') {
      enforce24hLock(detail);
    } else {
      enforce24hLock();
    }
  });

  const links = document.querySelectorAll('[data-tab]');
  const tabs  = document.querySelectorAll('.tab');
  const bodyEl = document.body;
  const navToggle = document.querySelector('[data-nav-toggle]');
  const navClose = document.querySelector('[data-nav-close]');
  const navBackdrop = document.querySelector('[data-nav-backdrop]');
  const sidebarNav = document.getElementById('sidebar');

  const closeNav = () => bodyEl.classList.remove('nav-open');

  if (navToggle) {
    navToggle.addEventListener('click', () => {
      bodyEl.classList.toggle('nav-open');
    });
  }
  navClose?.addEventListener('click', closeNav);
  navBackdrop?.addEventListener('click', closeNav);
  sidebarNav?.addEventListener('click', (event) => {
    if (event.target.closest('a')) closeNav();
  });
  window.addEventListener('resize', () => {
    if (window.innerWidth >= 1024) closeNav();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeNav();
  });

  function setActive(link, active) {
    link.classList.toggle('is-active', active);
    link.setAttribute('aria-current', active ? 'page' : 'false');
  }
  function activate(tabName) {
    tabs.forEach(t => t.classList.toggle('hidden', t.id !== 'tab-' + tabName));
    links.forEach(l => setActive(l, l.dataset.tab === tabName));
  }

  /* hash-навигация */
  const allowed = ['overview','appointments','billing','forms','settings','support'];
  const initialHash = location.hash.replace('#','');
  const initial = allowed.includes(initialHash) ? initialHash : 'overview';
  activate(initial);
  links.forEach(link => link.addEventListener('click', e => {
    e.preventDefault();
    activate(link.dataset.tab);
    history.replaceState(null, '', '#'+link.dataset.tab);
    closeNav();
  }));

  document.querySelectorAll('[data-tab-jump]').forEach((btn) => {
    btn.addEventListener('click', (event) => {
      event.preventDefault();
      const target = btn.getAttribute('data-tab-jump');
      if (!target || !allowed.includes(target)) return;
      activate(target);
      history.replaceState(null, '', '#' + target);
      closeNav();
      const section = document.getElementById(`tab-${target}`);
      if (section) {
        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  const autofillScript = document.getElementById('autofill-defaults');
  let autofillDefaults = {};
  if (autofillScript) {
    try {
      autofillDefaults = JSON.parse(autofillScript.textContent) || {};
    } catch (err) {
      console.warn('[dashboard] Failed to parse autofill defaults', err);
      autofillDefaults = {};
    }
  }
  const autofillApi = window.MalvaAutofill;
  const resolvedUserId = (document.body?.dataset?.autofillUser) ? String(document.body.dataset.autofillUser) : 'guest';
  const paymentEndpoint = document.body?.dataset?.autofillPaymentEndpoint || '';
  const paymentAccountCard = document.querySelector('[data-payment-account-card]');
  const paymentAccountUpdatedEl = paymentAccountCard?.querySelector('[data-payment-account-updated]');
  const paymentAccountFieldNodes = paymentAccountCard ? paymentAccountCard.querySelectorAll('[data-payment-account-field]') : [];
  const autofillGroups = ['profile', 'health', 'payment'];
  const deviceListEl = document.querySelector('[data-autofill-list]');
  const deviceEmptyEl = document.querySelector('[data-autofill-empty]');
  const syncButtons = document.querySelectorAll('[data-autofill-sync]');
  const clearButtons = document.querySelectorAll('[data-autofill-clear]');
  const clearAllButton = document.querySelector('[data-autofill-clear-all]');
  const accountSyncButtons = document.querySelectorAll('[data-autofill-sync-account]');
  const accountClearButtons = document.querySelectorAll('[data-autofill-clear-account]');
  const paymentAllowedKeys = ['name', 'email', 'phone', 'address_line1', 'address_line2', 'city', 'state', 'postal_code', 'country'];
  const defaultPayment = Object.assign({}, autofillDefaults.payment || {});
  autofillDefaults.payment = defaultPayment;
  const groupLabels = {
    profile: 'Profile form',
    health: 'Health questionnaire',
    payment: 'Payment details',
  };
  const formatAutofillTimestamp = (iso) => {
    if (!iso) return '';
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return '';
    return `Updated ${dt.toLocaleString(getLocale(), { dateStyle: 'medium', timeStyle: 'short' })}`;
  };
  const updatePaymentAccountCard = (values, updatedAt) => {
    if (!paymentAccountCard) return;
    const data = values || {};
    paymentAccountFieldNodes.forEach((el) => {
      const key = el.dataset.paymentAccountField;
      if (!key) return;
      let text = '—';
      if (key === 'address') {
        const addr = [data.address_line1, data.address_line2].filter(Boolean).join('\n');
        if (addr) text = addr;
      } else if (data[key]) {
        text = data[key];
      }
      el.textContent = text;
    });
    if (paymentAccountUpdatedEl) {
      paymentAccountUpdatedEl.textContent = updatedAt ? formatAutofillTimestamp(updatedAt) : 'Not updated yet.';
    }
  };
  updatePaymentAccountCard(defaultPayment, defaultPayment.updated_at || defaultPayment.updatedAt || '');

  const normalizePaymentPayload = (payload) => {
    const result = {};
    Object.entries(payload || {}).forEach(([key, value]) => {
      if (!paymentAllowedKeys.includes(key)) return;
      if (value === undefined || value === null) return;
      let str = value;
      if (typeof str !== 'string') {
        str = String(str);
      }
      str = str.trim();
      if (!str) return;
      result[key] = str;
    });
    return result;
  };

  let paymentPersistTimer = null;
  const sendPaymentContact = async (payload, { clear = false } = {}) => {
    if (!paymentEndpoint) return;
    const body = clear ? { clear: true } : normalizePaymentPayload(payload);
    if (!clear && Object.keys(body).length === 0) {
      return;
    }
    try {
      const resp = await fetch(paymentEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrftoken,
        },
        credentials: 'same-origin',
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      const contact = data?.billing_contact || {};
      const updatedAt = data?.updated_at || '';
      autofillDefaults.payment = Object.assign({}, contact, updatedAt ? { updated_at: updatedAt } : {});
      updatePaymentAccountCard(autofillDefaults.payment, updatedAt);
    } catch (err) {
      console.warn('[dashboard] Failed to persist payment contact', err);
    }
  };

  const persistPaymentContact = (payload, { immediate = false } = {}) => {
    if (!paymentEndpoint) return;
    const task = () => sendPaymentContact(payload);
    if (immediate) {
      task();
      return;
    }
    window.clearTimeout(paymentPersistTimer);
    paymentPersistTimer = window.setTimeout(task, 600);
  };

  const fallbackPaymentPayload = () => {
    const profileDefaults = autofillDefaults.profile || {};
    const paymentDefaults = Object.assign({}, autofillDefaults.payment || {});
    const finalPayload = Object.assign({}, paymentDefaults);
    if (!finalPayload.name) {
      const fullName = `${profileDefaults.first_name || ''} ${profileDefaults.last_name || ''}`.trim();
      if (fullName) finalPayload.name = fullName;
    }
    ['email', 'phone', 'postal_code'].forEach((key) => {
      if (!finalPayload[key] && profileDefaults[key]) {
        finalPayload[key] = profileDefaults[key];
      }
    });
    if (!finalPayload.address_line1 && profileDefaults.address) {
      const lines = String(profileDefaults.address).split('\n').map((line) => line.trim()).filter(Boolean);
      if (lines.length) {
        finalPayload.address_line1 = lines[0];
        if (lines.length > 1) {
          finalPayload.address_line2 = lines.slice(1).join(' ');
        }
      }
    }
    return normalizePaymentPayload(finalPayload);
  };
  const renderAutofillDevice = () => {
    if (!autofillApi || !deviceListEl || !deviceEmptyEl) {
      return;
    }
    deviceListEl.innerHTML = '';
    let hasData = false;
    autofillGroups.forEach((group) => {
      const state = autofillApi.load(group, { userId: resolvedUserId });
      const values = state?.values || {};
      const savedKeys = Object.keys(values).filter((key) => {
        const value = values[key];
        if (Array.isArray(value)) return value.length > 0;
        return value !== undefined && value !== null && value !== '';
      });
      if (!savedKeys.length) {
        return;
      }
      hasData = true;
      const row = document.createElement('div');
      row.className = 'flex flex-wrap items-center justify-between gap-3 rounded-lg bg-white border border-[#DAD3C1] px-4 py-3';
      const info = document.createElement('div');
      info.innerHTML = `
        <div class="font-semibold text-[#204029]">${groupLabels[group] || (group.charAt(0).toUpperCase() + group.slice(1))}</div>
        <div class="text-xs text-[#4D4D4D]/70">${savedKeys.length} field${savedKeys.length === 1 ? '' : 's'} saved${state?.updatedAt ? ' • ' + formatAutofillTimestamp(state.updatedAt) : ''}</div>
      `;
      const actions = document.createElement('div');
      actions.className = 'flex items-center gap-2';
      const clearBtn = document.createElement('button');
      clearBtn.type = 'button';
      clearBtn.className = 'px-3 py-1 text-xs border border-[#204029]/40 rounded-lg text-[#204029] hover:border-[#204029] transition';
      clearBtn.textContent = 'Clear';
      clearBtn.addEventListener('click', () => autofillApi.clear(group, { userId: resolvedUserId }));
      actions.appendChild(clearBtn);
      row.append(info, actions);
      deviceListEl.appendChild(row);
    });
    if (hasData) {
      deviceEmptyEl.classList.add('hidden');
      deviceListEl.classList.remove('hidden');
    } else {
      deviceListEl.classList.add('hidden');
      deviceEmptyEl.classList.remove('hidden');
    }
  };
  const flash = (el, message) => {
    if (!el) return;
    const original = el.dataset.originalText || el.textContent;
    el.dataset.originalText = original;
    el.textContent = message;
    el.disabled = true;
    el.classList.add('opacity-70');
    window.setTimeout(() => {
      el.textContent = el.dataset.originalText || original;
      el.disabled = false;
      el.classList.remove('opacity-70');
    }, 1800);
  };
  if (autofillApi) {
    autofillApi.attachAll('form[data-autofill-group]');
  }

  const storageSupported = autofillApi ? autofillApi.storageAvailable() : false;
  if (!storageSupported) {
    if (deviceEmptyEl) {
      deviceEmptyEl.textContent = 'Autofill requires local storage support. Enable cookies/local storage or switch to another browser.';
      deviceEmptyEl.classList.remove('hidden');
    }
    document.querySelectorAll('[data-autofill-sync],[data-autofill-clear],[data-autofill-clear-all]').forEach((btn) => {
      btn.disabled = true;
      btn.classList.add('opacity-50', 'cursor-not-allowed');
    });
  } else {
    renderAutofillDevice();
  }

  if (autofillApi) {
    autofillApi.subscribe(({ group, userId, state }) => {
      if (String(userId || 'guest') !== resolvedUserId) return;
      if (storageSupported && autofillGroups.includes(group)) {
        renderAutofillDevice();
      }
      if (group === 'payment') {
        const source = (state && state.values) || (state && state.state && state.state.values) || {};
        persistPaymentContact(source);
      }
    });
  }

  const profileKeys = ['first_name', 'last_name', 'email', 'phone', 'birth_date', 'address', 'postal_code', 'how_heard', 'email_marketing_consent'];
  if (autofillApi) {
    syncButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        const group = btn.dataset.autofillSync;
        if (!group) return;
        let payload = autofillDefaults[group] || {};
        if (group === 'profile') {
          payload = {};
          const defaults = autofillDefaults.profile || {};
          profileKeys.forEach((key) => {
            if (defaults[key] !== undefined && defaults[key] !== null && defaults[key] !== '') {
              payload[key] = defaults[key];
            }
          });
        }
        autofillApi.save(group, payload, { userId: resolvedUserId });
        if (group === 'payment') {
          persistPaymentContact(payload, { immediate: true });
        }
        flash(btn, 'Synced');
      });
    });
    clearButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        const group = btn.dataset.autofillClear;
        if (!group) return;
        autofillApi.clear(group, { userId: resolvedUserId });
        if (group === 'payment') {
          sendPaymentContact({}, { clear: true });
        }
        flash(btn, 'Cleared');
      });
    });
    clearAllButton?.addEventListener('click', () => {
      autofillGroups.forEach((group) => {
        autofillApi.clear(group, { userId: resolvedUserId });
        if (group === 'payment') {
          sendPaymentContact({}, { clear: true });
        }
      });
      flash(clearAllButton, 'Cleared');
    });
  }

  accountSyncButtons.forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (!paymentEndpoint) {
        flash(btn, 'Unavailable');
        return;
      }
      let payload = {};
      if (autofillApi) {
        const state = autofillApi.load('payment', { userId: resolvedUserId });
        payload = Object.assign({}, (state && state.values) || {});
      }
      if (!Object.keys(payload).length) {
        payload = fallbackPaymentPayload();
      }
      await sendPaymentContact(payload);
      flash(btn, 'Synced');
    });
  });
  accountClearButtons.forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (!paymentEndpoint) {
        flash(btn, 'Unavailable');
        return;
      }
      await sendPaymentContact({}, { clear: true });
      flash(btn, 'Cleared');
    });
  });

  /* chart */
  const el = document.getElementById('stats_chart');
  let statsChart = null;
  if (el) {
    const labels = el.dataset.labels ? el.dataset.labels.split(',') : [];
    const data   = el.dataset.data   ? el.dataset.data.split(',').map(Number) : [];
    statsChart = new Chart(el, {
      type: 'bar',
      data: { labels, datasets: [{ data, label: translate('dashboard.chartLabel', null, 'Appointments'), backgroundColor: '#AF9525', borderRadius: 6 }] },
      options: {
        plugins: { legend: { display: false }},
        scales : {
          x: { ticks: { color: '#4D4D4D' }, grid: { color: '#DAD3C1' } },
          y: { beginAtZero: true, ticks: { stepSize: 1, color: '#4D4D4D' }, grid: { color: '#DAD3C1' } }
        }
      }
    });
  }

  /* helpers */
  const csrftoken = (document.cookie.match('(^|;)\\s*csrftoken\\s*=\\s*([^;]+)')||[])[2] || '';
  const fmtHM = d => d.toLocaleTimeString(getLocale(), {hour:'numeric', minute:'2-digit'});
  const fmtTime = iso => { try { return new Date(iso).toLocaleTimeString(getLocale(), {hour:'2-digit', minute:'2-digit'});} catch(e){ return iso; } };
  const ymd = d => { const m=String(d.getMonth()+1).padStart(2,'0'), day=String(d.getDate()).padStart(2,'0'); return `${d.getFullYear()}-${m}-${day}`; };

  /* ===== отмена с подтверждением + «перечёркивание» без перезагрузки ===== */
  async function cancelAppointment(apptId, itemId){
    if(!confirm(translate('dashboard.reschedule.confirmCancel', null, 'Cancel this appointment?'))) return;
    const payload = itemId ? { item_id: itemId } : {};
    const r = await fetch(`/accounts/api/appointment/${apptId}/cancel/`, {
      method:'POST',
      headers:{'Content-Type':'application/json','X-CSRFToken': csrftoken},
      credentials:'same-origin',
      body: JSON.stringify(payload)
    });
    const data = await r.json().catch(()=> ({}));
    if(!r.ok){
      const fallback = data.error || data.detail || await r.text();
      alert(translate('dashboard.reschedule.cancelError', { detail: fallback }, `Cancel error: ${fallback}`));
      return;
    }
    location.reload();
  }
  document.addEventListener('click', async (e)=>{
    const a = e.target.closest('.appt-cancel');
    if(!a) return;
    if (a.hasAttribute('aria-disabled') || a.classList.contains('is-disabled')) {
      e.preventDefault();
      return;
    }
    e.preventDefault();
    const apptId = a.dataset.apptId;
    const itemId = a.dataset.itemId || '';
    if(!apptId) return;
    cancelAppointment(apptId, itemId);
  });

  /* ===== RESCHEDULE: новый горизонтальный пикер ===== */
  const resModal  = document.getElementById('resModal');
  const resClose  = document.getElementById('resClose');
  const resCancel = document.getElementById('resCancel');
  const resSubmit = document.getElementById('resSubmit');
  const resMaster = document.getElementById('resMaster');
  const resErr    = document.getElementById('resErr');
  const resOk     = document.getElementById('resOk');

  const rsGrid = document.getElementById('rsGrid');
  const rsWrap = document.getElementById('rsWrap');
  const rsRange= document.getElementById('rsRange');
  const rsPrev = document.getElementById('rsPrev');
  const rsNext = document.getElementById('rsNext');
  const rsToday= document.getElementById('rsToday');
  const rsMobileContainer = document.getElementById('rsMobileContainer');
  const rsMobileDays = document.getElementById('rsMobileDays');
  const rsMobileTimes = document.getElementById('rsMobileTimes');
  const rsMobileEmpty = document.getElementById('rsMobileEmpty');
  const rsMobileHint = document.getElementById('rsMobileHint');

  const WINDOW_DAYS = 14, START=6, END=23, STEP=30;
  const normalizeId = (value) => (value === undefined || value === null ? "" : String(value));

  let resState = {
    apptId:null, serviceId:null, itemId:null, masterId:null, slot:null, masters:[],
    baseStart: (()=>{const d=new Date(); d.setHours(0,0,0,0); return d;})(),
    cache: new Map(), // dateStr -> { set:Set('HH:MM'), iso:Map('HH:MM'->iso) }
    selectedDayIndex:0,
    days: [],
    dayData: [],
    timeRows: [],
    locale: getLocale()
  };

  function openRes(apptId, serviceId, itemId){
    const startOfDay = new Date();
    startOfDay.setHours(0,0,0,0);
    resState.apptId = apptId;
    resState.serviceId = serviceId;
    resState.itemId = itemId;
    resState.masterId = null;
    resState.slot = null;
    resState.masters = [];
    resState.cache = new Map();
    resState.baseStart = startOfDay;
    resState.selectedDayIndex = 0;
    resState.days = [];
    resState.dayData = [];
    resState.timeRows = [];
    resState.locale = getLocale();
    resMaster.innerHTML = '';
    resSubmit.disabled = true;
    resErr.classList.add('hidden'); resOk.classList.add('hidden');
    resModal.classList.remove('hidden'); resModal.classList.add('flex');
    loadMastersAndRender();
  }
  function closeRes(){ resModal.classList.add('hidden'); resModal.classList.remove('flex'); }

  async function fetchAvail(dayISO, masterId){
    const params = new URLSearchParams({ service: resState.serviceId, date: dayISO });
    const masterParam = normalizeId(masterId);
    if (masterParam) params.set('master', masterParam);
    const r = await fetch(`/accounts/api/availability/?${params.toString()}`, {credentials:'same-origin'});
    if(!r.ok) throw new Error(translate('dashboard.reschedule.loadFailed'));
    const data = await r.json();

    let slots=[];
    if (masterParam){
      if (Array.isArray(data.slots)) {
        slots = data.slots;
      } else {
        const match = (data.masters || []).find((entry) => normalizeId(entry.id) === masterParam);
        slots = match ? (match.slots || []) : [];
      }
    }else{
      // возьмём слоты первого мастера только чтобы понять список мастеров
      const firstWithSlots = Array.isArray(data.masters)
        ? data.masters.find((entry) => Array.isArray(entry.slots) && entry.slots.length)
        : null;
      slots = firstWithSlots ? firstWithSlots.slots : [];
    }
    const set=new Set(), map=new Map();
    (slots||[]).forEach(iso=>{ const d=new Date(iso); const key=`${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`; set.add(key); if(!map.has(key)) map.set(key, iso); });
    return { raw:data, set, map };
  }

  async function ensureRangeLoaded(start, days){
    const jobs=[];
    for(let i=0;i<days;i++){
      const d=new Date(start); d.setDate(d.getDate()+i); const ds=ymd(d);
      if(!resState.cache.has(ds)){
        jobs.push((async()=>{
          resState.cache.set(ds, {loading:true});
          const {set,map}=await fetchAvail(ds, resState.masterId);
          resState.cache.set(ds,{set,iso:map});
        })());
      }
    }
    if (jobs.length) await Promise.allSettled(jobs);
  }

  function buildTimeRows(extraSets){
    const out=[];
    for(let h=START;h<=END;h++) for(let m=0;m<60;m+=STEP) out.push(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`);
    (extraSets||[]).forEach(s=>s && s.forEach(t=>{ if(!out.includes(t)) out.push(t); }));
    return out.sort();
  }

  async function loadMastersAndRender(){
    resErr.classList.add('hidden');
    clearTextKey(resErr);
    try{
      const first = await fetchAvail(ymd(resState.baseStart), null);
      resState.masters = (first.raw && first.raw.masters) || [];
      resMaster.innerHTML = '';
      if(resState.masters.length===0){
        const opt=document.createElement('option');
        opt.value='';
        opt.textContent = translate('dashboard.reschedule.noMasters', null, 'No masters available');
        opt.setAttribute('data-i18n', 'dashboard.reschedule.noMasters');
        resMaster.appendChild(opt);
        rsGrid.innerHTML = `<div class="p-4 text-sm" data-i18n="dashboard.reschedule.noAvailability">${translate('dashboard.reschedule.noAvailability', null, 'No availability')}</div>`;
        if (rsMobileDays) rsMobileDays.innerHTML='';
        if (rsMobileTimes) rsMobileTimes.innerHTML='';
        if (rsMobileEmpty){
          setTextKey(rsMobileEmpty, 'dashboard.reschedule.noAvailability', null, 'No availability yet.');
          rsMobileEmpty.classList.remove('hidden');
        }
        queueRefresh();
        return;
      }
      resState.masters.forEach(m=>{ const opt=document.createElement('option'); opt.value=normalizeId(m.id); opt.textContent=m.name; resMaster.appendChild(opt); });
      const withSlots = resState.masters.find(m=>(m.slots||[]).length) || resState.masters[0];
      resMaster.value = normalizeId(withSlots.id);
      resState.masterId = resMaster.value;
      resState.cache.clear();
      await renderWindow();
    }catch(e){
      const fallback = e && e.message;
      const defaultMsg = translate('dashboard.reschedule.errorLoad');
      resErr.classList.remove('hidden');
      if(fallback && fallback !== defaultMsg){
        clearTextKey(resErr);
        resErr.textContent = fallback;
      }else{
        setTextKey(resErr, 'dashboard.reschedule.errorLoad');
      }
    }
  }

  async function renderWindow(){
    await ensureRangeLoaded(resState.baseStart, WINDOW_DAYS);

    const locale = getLocale();

    const days = Array.from({length:WINDOW_DAYS}, (_,i)=>{ const d=new Date(resState.baseStart); d.setDate(d.getDate()+i); return d;});
    const dayStrs = days.map(ymd);
    const dayData = dayStrs.map(ds => resState.cache.get(ds));
    const timeRows = buildTimeRows(dayData.map(x=>x?.set));

    const from = days[0].toLocaleDateString(locale, {month:'short', day:'numeric'});
    const to   = days[days.length-1].toLocaleDateString(locale, {month:'short', day:'numeric'});
    if (rsRange) {
      rsRange.textContent = `${from} – ${to}`;
    }

    resState.locale = locale;
    resState.days = days;
    resState.dayData = dayData;
    resState.timeRows = timeRows;

    if (resState.slot){
      let stillExists = false;
      for (const data of dayData){
        if (data?.iso){
          for (const value of data.iso.values()){
            if (value === resState.slot){ stillExists = true; break; }
          }
        }
        if (stillExists) break;
      }
      if (!stillExists){
        resState.slot = null;
      }
    }

    if (typeof resState.selectedDayIndex !== 'number' || resState.selectedDayIndex < 0){
      resState.selectedDayIndex = 0;
    }
    if (resState.selectedDayIndex >= days.length){
      resState.selectedDayIndex = Math.max(days.length - 1, 0);
    }
    const firstAvailableIndex = dayData.findIndex(entry => entry && entry.set && entry.set.size);
    if (firstAvailableIndex !== -1){
      const currentData = dayData[resState.selectedDayIndex];
      if (!currentData || !currentData.set || !currentData.set.size){
        resState.selectedDayIndex = firstAvailableIndex;
        resState.slot = null;
      }
    }

    if (rsMobileHint){
      setTextKey(rsMobileHint, 'dashboard.reschedule.mobileHint', null, 'Tap a date to see available times.');
    }

    renderDesktopGrid(locale);
    renderMobileLayout(locale);

    resSubmit.disabled = !resState.slot;
  }

  function renderDesktopGrid(locale = resState.locale || getLocale()){
    if (!rsGrid) return;
    const days = resState.days || [];
    const dayData = resState.dayData || [];
    const timeRows = resState.timeRows || [];

    rsGrid.style.setProperty('--days', String(WINDOW_DAYS));
    rsGrid.innerHTML='';

    const corner=document.createElement('div');
    corner.className='ol2__cell ol2__head time';
    rsGrid.appendChild(corner);

    const todayString = (new Date()).toDateString();

    days.forEach(d=>{
      const header=document.createElement('div');
      const isToday = todayString === d.toDateString();
      header.className='ol2__cell ol2__head';
      header.innerHTML = `<div class="ol2__day ${isToday?'today':''}">
        <div class="t">${d.toLocaleDateString(locale, {weekday:'long'})}</div>
        <div class="s">${d.toLocaleDateString(locale, {month:'short', day:'numeric'})}</div>
      </div>`;
      rsGrid.appendChild(header);
    });

    timeRows.forEach(t=>{
      const [hh,mm]=t.split(':').map(Number);
      const fake=new Date(); fake.setHours(hh,mm,0,0);
      const timeCell=document.createElement('div');
      timeCell.className='ol2__cell time'; timeCell.textContent = fmtHM(fake);
      rsGrid.appendChild(timeCell);

      days.forEach((d, idx)=>{
        const cell=document.createElement('div'); cell.className='ol2__cell';
        const data = dayData[idx];
        const isFree = data?.set?.has(t);
        const chip=document.createElement('button');
        chip.type='button'; chip.className='chip ' + (isFree?'chip--free':'chip--busy');
        chip.textContent = fmtHM(fake);
        chip.disabled = !isFree;

        if(isFree){
          const isoValue = data.iso.get(t);
          if (isoValue === resState.slot){
            chip.classList.add('chip--sel');
            resState.selectedDayIndex = idx;
          }
          chip.addEventListener('click', ()=>{
            resState.slot = isoValue;
            resState.selectedDayIndex = idx;
            resSubmit.disabled = false;
            renderDesktopGrid(locale);
            renderMobileLayout(locale);
          });
        }
        cell.appendChild(chip);
        rsGrid.appendChild(cell);
      });
    });

    if (rsWrap){
      const selectedChip = rsGrid.querySelector('.chip--sel');
      if (selectedChip){
        selectedChip.scrollIntoView({ block:'nearest', inline:'center' });
      }else{
        const todayIdx = days.findIndex(x=>x.toDateString()===todayString);
        if (todayIdx>0){
          rsWrap.scrollLeft = Math.max(todayIdx*140 - 140, 0);
        } else {
          rsWrap.scrollLeft = 0;
        }
      }
    }

    resSubmit.disabled = !resState.slot;
  }

  function renderMobileLayout(locale = resState.locale || getLocale()){
    if (!rsMobileContainer || !rsMobileDays || !rsMobileTimes) return;
    const days = resState.days || [];

    rsMobileDays.innerHTML = '';

    if (!days.length){
      rsMobileTimes.innerHTML = '';
      if (rsMobileEmpty){
        setTextKey(rsMobileEmpty, 'dashboard.reschedule.noAvailability', null, 'No availability yet.');
        rsMobileEmpty.classList.remove('hidden');
      }
      return;
    }

    days.forEach((day, idx) => {
      const btn=document.createElement('button');
      btn.type='button';
      btn.className='rs-mobile-day';
      if (idx === resState.selectedDayIndex){
        btn.classList.add('rs-mobile-day--active');
      }
      const dateLabel = day.toLocaleDateString(locale, {month:'short', day:'numeric'});
      const weekdayLabel = day.toLocaleDateString(locale, {weekday:'short'});
      btn.innerHTML = `<strong>${dateLabel}</strong><span>${weekdayLabel}</span>`;
      btn.addEventListener('click', ()=>{
        if (resState.selectedDayIndex === idx) return;
        resState.selectedDayIndex = idx;
        resState.slot = null;
        resSubmit.disabled = true;
        renderMobileTimes(locale);
      });
      rsMobileDays.appendChild(btn);
    });

    renderMobileTimes(locale);

    const activeBtn = rsMobileDays.querySelector('.rs-mobile-day--active');
    if (activeBtn){
      activeBtn.scrollIntoView({ block:'nearest', inline:'center', behavior:'smooth' });
    }
  }

  function renderMobileTimes(locale = resState.locale || getLocale()){
    if (!rsMobileTimes) return;
    const dayData = resState.dayData || [];
    const days = resState.days || [];

    let idx = typeof resState.selectedDayIndex === 'number' ? resState.selectedDayIndex : 0;
    if (idx < 0) idx = 0;
    if (idx >= days.length) idx = Math.max(days.length - 1, 0);
    resState.selectedDayIndex = idx;

    if (rsMobileDays){
      const buttons = rsMobileDays.querySelectorAll('.rs-mobile-day');
      buttons.forEach((btn, buttonIdx) => {
        btn.classList.toggle('rs-mobile-day--active', buttonIdx === idx);
      });
    }

    rsMobileTimes.innerHTML = '';

    const data = dayData[idx];
    if (!data || !data.set || !data.set.size){
      if (rsMobileEmpty){
        setTextKey(rsMobileEmpty, 'dashboard.reschedule.noAvailability', null, 'No available times on this day.');
        rsMobileEmpty.classList.remove('hidden');
      }
      resSubmit.disabled = true;
      return;
    }

    if (rsMobileEmpty){
      rsMobileEmpty.classList.add('hidden');
    }

    const times = Array.from(data.set).sort();
    times.forEach(timeKey => {
      const iso = data.iso.get(timeKey);
      if (!iso) return;
      const btn=document.createElement('button');
      btn.type='button';
      btn.className='rs-mobile-time';
      btn.textContent = fmtHM(new Date(iso));
      if (iso === resState.slot){
        btn.classList.add('rs-mobile-time--selected');
      }
      btn.addEventListener('click', ()=>{
        resState.slot = iso;
        resState.selectedDayIndex = idx;
        resSubmit.disabled = false;
        rsMobileTimes.querySelectorAll('.rs-mobile-time--selected').forEach(el=>el.classList.remove('rs-mobile-time--selected'));
        btn.classList.add('rs-mobile-time--selected');
        renderDesktopGrid(locale);
      });
      rsMobileTimes.appendChild(btn);
    });

    if (!times.length){
      if (rsMobileEmpty){
        setTextKey(rsMobileEmpty, 'dashboard.reschedule.noAvailability', null, 'No available times on this day.');
        rsMobileEmpty.classList.remove('hidden');
      }
      resSubmit.disabled = true;
    }

    resSubmit.disabled = !resState.slot;
  }

  let resWindowResizeTimer = null;
  window.addEventListener('resize', ()=>{
    if (!resModal || resModal.classList.contains('hidden')) return;
    if (resWindowResizeTimer) window.clearTimeout(resWindowResizeTimer);
    resWindowResizeTimer = window.setTimeout(()=>{
      renderWindow().catch(()=>{});
    }, 180);
  });

  async function shiftWindow(delta){
    const d=new Date(resState.baseStart); d.setDate(d.getDate()+delta); d.setHours(0,0,0,0); resState.baseStart = d;
    resState.selectedDayIndex = 0;
    resState.slot = null;
    resSubmit.disabled = true;
    await renderWindow();
  }

  resMaster.addEventListener('change', async ()=>{
    resState.masterId = resMaster.value;
    resState.slot = null; resSubmit.disabled=true; resState.cache.clear();
    resState.selectedDayIndex = 0;
    resErr.classList.add('hidden'); clearTextKey(resErr);
    resOk.classList.add('hidden'); clearTextKey(resOk);
    await renderWindow();
  });
  rsPrev.addEventListener('click', ()=>shiftWindow(-WINDOW_DAYS));
  rsNext.addEventListener('click', ()=>shiftWindow(WINDOW_DAYS));
  rsToday.addEventListener('click', async ()=>{ const d=new Date(); d.setHours(0,0,0,0); resState.baseStart=d; await renderWindow(); });

  // UX: Shift+Wheel — горизонтальный скролл
  rsWrap.addEventListener('wheel', (e)=>{ if(e.shiftKey && Math.abs(e.deltaY)>Math.abs(e.deltaX)){ e.preventDefault(); rsWrap.scrollLeft += e.deltaY; } }, {passive:false});

  async function submitRes(){
    if(!resState.apptId || !resState.slot) return;
    resSubmit.disabled = true; resErr.classList.add('hidden'); resOk.classList.add('hidden');
    clearTextKey(resErr); clearTextKey(resOk);
    const r = await fetch(`/accounts/api/appointment/${resState.apptId}/reschedule/`, {
      method:'POST',
      headers:{'Content-Type':'application/json','X-CSRFToken': csrftoken},
      credentials:'same-origin',
      body: JSON.stringify({ start_time: resState.slot, master: resState.masterId, item_id: resState.itemId })
    });
    const data = await r.json().catch(()=> ({}));
    if(r.ok){
      const startISO = data.appointment?.start_time || '';
      const locale = getLocale();
      const localized = startISO ? new Date(startISO).toLocaleString(locale) : '';
      setTextKey(resOk, 'dashboard.reschedule.success', { datetime: localized }, `Rescheduled to ${localized}`);
      resOk.classList.remove('hidden');
      // мгновенно обновим дату в карточке (если она на странице)
      document.querySelectorAll(`[data-appt-id="${resState.apptId}"] .appt-dt`).forEach(dt=>{
        try{ dt.textContent = new Date(data.appointment.start_time).toLocaleString(locale); }catch(_){}
      });
      setTimeout(()=> location.reload(), 700);
    }else{
      const fallback = data.error || data.detail;
      resErr.classList.remove('hidden');
      if(fallback){
        clearTextKey(resErr);
        resErr.textContent = fallback;
      }else{
        setTextKey(resErr, 'dashboard.reschedule.failed');
      }
      resSubmit.disabled = false;
    }
  }

  document.addEventListener('click', (e)=>{
    const a = e.target.closest('.appt-reschedule');
    if(!a) return;
    if (a.hasAttribute('aria-disabled') || a.classList.contains('is-disabled')) {
      e.preventDefault();
      return;
    }
    e.preventDefault();
    openRes(a.dataset.apptId, a.dataset.serviceId, a.dataset.itemId || '');
  });
  resClose.addEventListener('click', closeRes);
  resCancel.addEventListener('click', closeRes);
  resModal.addEventListener('click', (e)=>{ if(e.target===resModal) closeRes(); });
  resSubmit.addEventListener('click', submitRes);

  applyServiceNameTranslations();
  enforce24hLock();

  if (I18N && typeof I18N.onChange === 'function') {
    I18N.onChange(() => {
      applyServiceNameTranslations();
      enforce24hLock();
      if (resModal && resModal.classList.contains('flex')) {
        renderWindow().catch(()=>{});
      }
      if (statsChart) {
        statsChart.data.datasets[0].label = translate('dashboard.chartLabel', null, 'Appointments');
        statsChart.update();
      }
    });
  }
});
