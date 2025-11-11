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

  const bind = (node, event, handler, options) => {
    if (node && typeof node.addEventListener === 'function') {
      node.addEventListener(event, handler, options);
      return true;
    }
    return false;
  };

  function parseUtc(iso) {
    const d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }
  const lockClickHandlers = new WeakMap();
  function enforce24hLock(root = document) {
  const scope = root && typeof root.querySelectorAll === 'function' ? root : document;
  const nowMs = Date.now();

  const items = scope.querySelectorAll('.appointment-item[data-appt-start-iso]');
  items.forEach((item) => {
    const iso = item.getAttribute('data-appt-start-iso') || '';
    const start = parseUtc(iso);
    if (!start) return;

    const msLeft = start.getTime() - nowMs;

    // Only lock actions for FUTURE slots inside the next 24h.
    // (Old code also locked past items by mistake.)
    const futureWithin24h = msLeft >= 0 && msLeft < 24 * 60 * 60 * 1000;

    // Also treat terminal states as non-manageable (defensive).
    const statusCode = (item.querySelector('[data-role="item-status"]')?.getAttribute('data-status-code') || '').toUpperCase();
    const isTerminal = statusCode === 'CANCELLED' || statusCode === 'COMPLETED';

    const cancelBtn  = item.querySelector('.appt-cancel');
    const reschedBtn = item.querySelector('.appt-reschedule');

    [cancelBtn, reschedBtn].forEach((btn) => {
      if (!btn) return;

      const handler = lockClickHandlers.get(btn);
      const shouldDisable = futureWithin24h || isTerminal;

      if (shouldDisable) {
        btn.setAttribute('aria-disabled', 'true');
        btn.classList.add('is-disabled');
        // Ensure the click truly does nothing
        if (!handler) {
          const prevent = (event) => event.preventDefault();
          btn.addEventListener('click', prevent);
          lockClickHandlers.set(btn, prevent);
        }
      } else {
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
  const ChartLib = window.Chart;
  if (el && typeof ChartLib === 'function') {
    const labels = el.dataset.labels ? el.dataset.labels.split(',') : [];
    const data   = el.dataset.data   ? el.dataset.data.split(',').map(Number) : [];
    statsChart = new ChartLib(el, {
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
  } else if (el && !ChartLib) {
    console.warn('[dashboard] Chart.js is not available, stats chart disabled.');
  }

  /* helpers */
  const csrftoken = (document.cookie.match('(^|;)\\s*csrftoken\\s*=\\s*([^;]+)')||[])[2] || '';
  const fmtHM = d => d.toLocaleTimeString(getLocale(), {hour:'numeric', minute:'2-digit'});
  const fmtTime = iso => { try { return new Date(iso).toLocaleTimeString(getLocale(), {hour:'2-digit', minute:'2-digit'});} catch(e){ return iso; } };
  const ymd = d => { const m=String(d.getMonth()+1).padStart(2,'0'), day=String(d.getDate()).padStart(2,'0'); return `${d.getFullYear()}-${m}-${day}`; };
  const fmtDateTime = (iso, options) => {
    if (!iso) return '';
    try {
      const opts = options || { dateStyle: 'medium', timeStyle: 'short' };
      return new Date(iso).toLocaleString(getLocale(), opts);
    } catch (err) {
      return iso;
    }
  };

  function cssEscape(value) {
    const str = value === undefined || value === null ? '' : String(value);
    if (!str) return '';
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(str);
    }
    return str.replace(/[\0-\x1F\x7F"#$%&'()*+,./:;<=>?@[\\\]^`{|}~]/g, '\\$&');
  }

  function findAppointmentNodes(apptId) {
    const escaped = cssEscape(apptId);
    if (!escaped) return [];
    return Array.from(document.querySelectorAll(`[data-appt-id="${escaped}"]`));
  }

  function findItemNodes(itemId) {
    const escaped = cssEscape(itemId);
    if (!escaped) return [];
    return Array.from(document.querySelectorAll(`[data-item-id="${escaped}"]`))
      .filter((node) => {
        if (!(node instanceof Element)) return false;
        if (node.matches('.appt-cancel, .appt-reschedule')) return false;
        if (node.classList.contains('appointment-item')) return true;
        return Boolean(node.querySelector('[data-role="item-status"]'));
      });
  }

  function setLoadingState(node, loading) {
    if (!node || !node.dataset) return;
    if (loading) {
      node.dataset.loading = 'true';
      node.setAttribute('aria-busy', 'true');
      node.classList.add('is-loading');
    } else {
      delete node.dataset.loading;
      node.removeAttribute('aria-busy');
      node.classList.remove('is-loading');
    }
  }

  function updateItemStatusDisplay(node, status) {
    if (!node || !status) return;
    const badge = node.querySelector('[data-role="item-status"]');
    if (!badge) return;
    const code = (status.code || '').toUpperCase();
    const label = status.label || code || badge.textContent || '';
    if (code) badge.setAttribute('data-status-code', code);
    badge.textContent = label;
  }

  function freezeItemActions(node, noteText) {
    if (!node) return;
    node.querySelectorAll('.appt-cancel, .appt-reschedule').forEach((link) => {
      link.setAttribute('aria-disabled', 'true');
      link.classList.add('is-disabled');
      link.removeAttribute('href');
      link.tabIndex = -1;
    });
    if (noteText) {
      let note = node.querySelector('[data-role="item-note"]');
      if (!note) {
        note = document.createElement('span');
        note.className = 'text-xs text-[#4D4D4D]/70 block';
        note.style.display = 'block';
        note.setAttribute('data-role', 'item-note');
        node.appendChild(note);
      }
      note.style.display = 'block';
      note.textContent = noteText;
    }
  }

  function setAppointmentStatus(apptId, status) {
    if (!apptId || !status) return false;
    const nodes = findAppointmentNodes(apptId);
    if (!nodes.length) return false;
    const code = (status.code || '').toUpperCase();
    const label = status.label || code || '';
    nodes.forEach((node) => {
      node.querySelectorAll('[data-role="appointment-status"]').forEach((badge) => {
        if (code) badge.setAttribute('data-status-code', code);
        badge.textContent = label;
      });
    });
    return true;
  }

  function setAppointmentStart(apptId, iso) {
    if (!apptId || !iso) return false;
    const nodes = findAppointmentNodes(apptId);
    if (!nodes.length) return false;
    const text = fmtDateTime(iso);
    nodes.forEach((node) => {
      node.setAttribute('data-appt-start-iso', iso);
      node.querySelectorAll('.appt-dt').forEach((el) => {
        el.textContent = text;
      });
    });
    return true;
  }

  function setItemStart(itemId, iso) {
    if (!itemId || !iso) return false;
    const nodes = findItemNodes(itemId);
    if (!nodes.length) return false;
    const text = fmtDateTime(iso);
    nodes.forEach((node) => {
      if (node.classList && node.classList.contains('appointment-item')) {
        node.setAttribute('data-appt-start-iso', iso);
        node.querySelectorAll('.appt-dt').forEach((el) => {
          el.textContent = text;
        });
      }
      node.querySelectorAll('[data-role="item-start"]').forEach((el) => {
        el.textContent = text;
      });
    });
    return true;
  }

  function applyCancellationResult(payload) {
    if (!payload) return false;
    let mutated = false;
    const status = payload.item_status || { code: 'CANCELLED', label: 'Cancelled' };
    const noteText = status.label || 'Cancelled';
    const targets = [];
    if (payload.item_id) targets.push(payload.item_id);
    if (Array.isArray(payload.item_ids)) targets.push(...payload.item_ids);
    targets.forEach((itemId) => {
      const nodes = findItemNodes(itemId);
      if (nodes.length) mutated = true;
      nodes.forEach((node) => {
        updateItemStatusDisplay(node, status);
        freezeItemActions(node, noteText);
      });
    });
    if (payload.appointment_id && payload.appointment_aggregated_status) {
      if (setAppointmentStatus(payload.appointment_id, payload.appointment_aggregated_status)) {
        mutated = true;
      }
    }
    return mutated;
  }

  function applyRescheduleResult(payload) {
    if (!payload) return false;
    let mutated = false;
    const apptId = (payload.appointment && payload.appointment.id) || payload.appointment_id;
    const apptStart = payload.appointment && payload.appointment.start_time;
    if (apptId && apptStart) {
      if (setAppointmentStart(apptId, apptStart)) mutated = true;
    }
    const itemId = (payload.item && payload.item.id) || payload.item_id;
    const itemStart = payload.item && payload.item.start_time;
    if (itemId && itemStart) {
      if (setItemStart(itemId, itemStart)) mutated = true;
    }
    const aggregated = payload.appointment_aggregated_status
      || (payload.appointment && payload.appointment.aggregated_status);
    if (apptId && aggregated) {
      if (setAppointmentStatus(apptId, aggregated)) mutated = true;
    }
    return mutated;
  }

  /* ===== отмена с подтверждением + «перечёркивание» без перезагрузки ===== */
  async function cancelAppointment(apptId, itemId, trigger){
    if(!apptId) return;
    const confirmation = window.confirm(translate('dashboard.reschedule.confirmCancel', null, 'Cancel this appointment?'));
    if(!confirmation) return;
    const payload = itemId ? { item_id: itemId } : {};
    setLoadingState(trigger, true);
    try{
      const response = await fetch(`/accounts/api/appointment/${apptId}/cancel/`, {
        method:'POST',
        headers:{'Content-Type':'application/json','X-CSRFToken': csrftoken},
        credentials:'same-origin',
        body: JSON.stringify(payload)
      });
      let data = {};
      try{
        data = await response.json();
      }catch(_){
        data = {};
      }
      if(!response.ok){
        const detail = data.error || data.detail || data.message || 'Unable to cancel appointment.';
        throw new Error(detail);
      }
      const mutated = applyCancellationResult(data);
      if(!mutated){
        window.setTimeout(()=> location.reload(), 150);
      }else{
        enforce24hLock();
      }
    }catch(err){
      const detail = err && err.message ? err.message : '';
      alert(translate('dashboard.reschedule.cancelError', { detail }, `Cancel error: ${detail || 'Unable to cancel'}`));
    }finally{
      setLoadingState(trigger, false);
    }
  }
  document.addEventListener('click', (event)=>{
    const target = event.target;
    if (!(target instanceof Element)) return;
    const link = target.closest('.appt-cancel');
    if(!link) return;
    if (
      link.hasAttribute('aria-disabled')
      || link.classList.contains('is-disabled')
      || link.dataset.loading === 'true'
    ){
      event.preventDefault();
      return;
    }
    event.preventDefault();
    const apptId = link.dataset.apptId;
    const itemId = link.dataset.itemId || '';
    if(!apptId) return;
    cancelAppointment(apptId, itemId, link);
  });

  /* ===== RESCHEDULE: новый горизонтальный пикер ===== */
  const resModal  = document.getElementById('resModal');
  const resClose  = document.getElementById('resClose');
  const resCancel = document.getElementById('resCancel');
  const resSubmit = document.getElementById('resSubmit');
  const resMaster = document.getElementById('resMaster');
  const resMasterHint = document.getElementById('resMasterHint');
  const resErr    = document.getElementById('resErr');
  const resOk     = document.getElementById('resOk');

  const rsGrid = document.getElementById('rsGrid');
  const rsWrap = document.getElementById('rsWrap');
  const rsRange= document.getElementById('rsRange');
  const rsPrev = document.getElementById('rsPrev');
  const rsNext = document.getElementById('rsNext');
  const rsToday= document.getElementById('rsToday');
  const rsCurrent = document.getElementById('rsCurrent');
  const rsMobileContainer = document.getElementById('rsMobileContainer');
  const rsMobileDays = document.getElementById('rsMobileDays');
  const rsMobileTimes = document.getElementById('rsMobileTimes');
  const rsMobileEmpty = document.getElementById('rsMobileEmpty');
  const rsMobileHint = document.getElementById('rsMobileHint');

  const WINDOW_DAYS = 14, START=6, END=23, STEP=30;
  const DAY_MS = 24 * 60 * 60 * 1000;
  const INITIAL_ANCHOR_THRESHOLD_DAYS = 28;
  const AUTO_WINDOW_HOPS = 6;
  const normalizeId = (value) => (value === undefined || value === null ? "" : String(value));
  const startOfDay = (value) => {
    if (!value) return null;
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return null;
    d.setHours(0, 0, 0, 0);
    return d;
  };
  const getTodayStart = () => {
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    return now;
  };
  const clampInitialBaseStart = (anchor) => {
    const today = getTodayStart();
    if (!anchor) return today;
    const diffDays = Math.floor((anchor.getTime() - today.getTime()) / DAY_MS);
    if (diffDays >= 0 && diffDays <= INITIAL_ANCHOR_THRESHOLD_DAYS) {
      return anchor;
    }
    return today;
  };

  const createDefaultResState = () => {
    const start = getTodayStart();
    return {
      apptId: null,
      serviceId: null,
      itemId: null,
      serviceName: '',
      masterId: null,
      preferredMasterId: '',
      slot: null,
      masters: [],
      baseStart: start,
      apptStart: null,
      autoSeekBudget: AUTO_WINDOW_HOPS,
      cache: new Map(),
      selectedDayIndex: 0,
      days: [],
      dayData: [],
      timeRows: [],
      locale: getLocale(),
      guardMessage: null,
    };
  };
  let resState = createDefaultResState();

  const hideResMasterHint = () => {
    if (!resMasterHint) return;
    resMasterHint.hidden = true;
    resMasterHint.textContent = '';
  };
  const showResMasterHint = (key, vars, fallback) => {
    if (!resMasterHint) return;
    const fallbackText = typeof fallback === 'string' ? fallback : '';
    const resolved = key ? translate(key, vars, fallbackText) : fallbackText;
    resMasterHint.textContent = resolved;
    resMasterHint.hidden = !resolved;
  };
  const syncResMasterHint = () => {
    if (!resMasterHint) return;
    const masters = Array.isArray(resState.masters) ? resState.masters : [];
    if (!masters.length) {
      showResMasterHint('services.modal.masterHintUnavailable', { service: resState.serviceName || '' }, 'No masters are available for this service yet.');
      return;
    }
    if (!resState.masterId) {
      showResMasterHint('services.modal.masterHintSelect', { service: resState.serviceName || '' }, 'Select a master to view availability.');
      return;
    }
    const match = masters.find((entry) => normalizeId(entry.id) === normalizeId(resState.masterId));
    const masterLabel = match?.name || translate('services.modal.masterFallbackName', null, 'selected master');
    showResMasterHint('services.modal.masterHintActive', { master: masterLabel }, `Showing availability for ${masterLabel}.`);
  };
  const syncCurrentButton = () => {
    if (!rsCurrent) return;
    const hasAnchor = Boolean(resState.apptStart);
    rsCurrent.classList.toggle('hidden', !hasAnchor);
    rsCurrent.disabled = !hasAnchor;
  };
  const resolveGuardMessage = (record) => {
    if (!record) return '';
    const fallback = record.fallback || '';
    return record.key ? translate(record.key, record.vars, fallback) : fallback;
  };

  function openRes(apptId, serviceId, itemId, meta = {}){
    if (!resModal || !resMaster || !rsGrid) {
      alert(translate('dashboard.reschedule.unavailable', null, 'Reschedule is temporarily unavailable.'));
      return;
    }
    if (!serviceId) {
      alert(translate('dashboard.reschedule.errorLoad', null, 'Unable to fetch availability for this service.'));
      return;
    }
    const base = meta.startIso ? parseUtc(meta.startIso) : null;
    const anchor = startOfDay(base);
    resState = createDefaultResState();
    resState.apptId = apptId;
    resState.serviceId = serviceId;
    resState.itemId = itemId;
    resState.serviceName = meta.serviceName || '';
    resState.preferredMasterId = normalizeId(meta.masterId || meta.preferredMasterId || '');
    resState.apptStart = anchor;
    resState.baseStart = clampInitialBaseStart(anchor);
    resState.autoSeekBudget = AUTO_WINDOW_HOPS;
    resMaster.innerHTML = '';
    hideResMasterHint();
    if (resSubmit) resSubmit.disabled = true;
    if (resErr) { resErr.classList.add('hidden'); clearTextKey(resErr); }
    if (resOk) { resOk.classList.add('hidden'); clearTextKey(resOk); }
    resModal.classList.remove('hidden');
    resModal.classList.add('flex');
    syncCurrentButton();
    loadMastersAndRender();
  }
  function closeRes(){
    if (!resModal) return;
    resModal.classList.add('hidden');
    resModal.classList.remove('flex');
  }

  async function fetchAvail(dayISO, masterId){
    if (!resState.serviceId) {
      throw new Error(translate('dashboard.reschedule.errorLoad', null, 'Unable to fetch availability'));
    }
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
    const activeMaster = normalizeId(resState.masterId);
    if (!activeMaster) return;
    const jobs=[];
    for(let i=0;i<days;i++){
      const d=new Date(start); d.setDate(d.getDate()+i); const ds=ymd(d);
      if(!resState.cache.has(ds)){
        jobs.push((async()=>{
          resState.cache.set(ds, {loading:true});
          const {set,map}=await fetchAvail(ds, activeMaster);
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
    if (!resMaster) return;
    resErr.classList.add('hidden');
    clearTextKey(resErr);
    hideResMasterHint();
    resState.guardMessage = null;
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
        showResMasterHint('services.modal.masterHintUnavailable', { service: resState.serviceName || '' }, 'No masters are available for this service yet.');
        rsGrid.innerHTML = `<div class="p-4 text-sm text-center" data-i18n="dashboard.reschedule.noAvailability">${translate('dashboard.reschedule.noAvailability', null, 'No availability')}</div>`;
        if (rsMobileDays) rsMobileDays.innerHTML='';
        if (rsMobileTimes) rsMobileTimes.innerHTML='';
        if (rsMobileEmpty){
          setTextKey(rsMobileEmpty, 'dashboard.reschedule.noAvailability', null, 'No availability yet.');
          rsMobileEmpty.classList.remove('hidden');
        }
        resState.masterId = null;
        queueRefresh();
        return;
      }
      const preferredId = normalizeId(resState.preferredMasterId);
      const preferredMaster = preferredId ? resState.masters.find((entry) => normalizeId(entry.id) === preferredId) : null;
      const requireManualSelection = resState.masters.length > 1 && !preferredMaster;
      if (requireManualSelection){
        const placeholder=document.createElement('option');
        placeholder.value='';
        placeholder.textContent = translate('services.modal.masterPlaceholder', null, 'Select a master');
        placeholder.dataset.placeholder='true';
        resMaster.appendChild(placeholder);
      }
      resState.masters.forEach(m=>{ const opt=document.createElement('option'); opt.value=normalizeId(m.id); opt.textContent=m.name; resMaster.appendChild(opt); });
      if (preferredMaster){
        resMaster.value = normalizeId(preferredMaster.id);
        resState.masterId = resMaster.value;
      }else if (!requireManualSelection){
        const withSlots = resState.masters.find(m=>(m.slots||[]).length) || resState.masters[0];
        resMaster.value = normalizeId(withSlots?.id || '');
        resState.masterId = resMaster.value || null;
      }else{
        resMaster.value = '';
        resState.masterId = null;
      }
      resState.cache.clear();
      syncResMasterHint();
      if (!resState.masterId){
        resState.guardMessage = {
          key: 'services.modal.masterHintSelect',
          vars: { service: resState.serviceName || '' },
          fallback: 'Select a master to view availability.'
        };
        renderWindow({ autoSeek: false });
        return;
      }
      await renderWindow({ autoSeek: true });
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

  const windowHasAvailability = (records = []) => records.some((entry) => entry && entry.set && entry.set.size);

  async function buildWindowSnapshot(baseDate) {
    await ensureRangeLoaded(baseDate, WINDOW_DAYS);
    const days = Array.from({ length: WINDOW_DAYS }, (_, i) => {
      const d = new Date(baseDate);
      d.setDate(d.getDate() + i);
      return d;
    });
    const dayStrs = days.map(ymd);
    const dayData = dayStrs.map((ds) => resState.cache.get(ds));
    const timeRows = buildTimeRows(dayData.map((x) => x?.set));
    return { days, dayData, timeRows };
  }

  async function renderWindow(options = {}){
    const { autoSeek = false } = options;
    const locale = getLocale();
    resState.locale = locale;

    if (!resState.masterId){
      resState.days = [];
      resState.dayData = [];
      resState.timeRows = [];
      if (rsRange) {
        rsRange.textContent = '—';
      }
      renderDesktopGrid(locale);
      renderMobileLayout(locale);
      if (resSubmit) resSubmit.disabled = true;
      return;
    }

    resState.guardMessage = null;
    resState.baseStart = startOfDay(resState.baseStart) || getTodayStart();

    let hopsRemaining = autoSeek ? Math.max(0, resState.autoSeekBudget || AUTO_WINDOW_HOPS) : 0;
    let snapshot = await buildWindowSnapshot(resState.baseStart);

    while (autoSeek && hopsRemaining > 0 && !windowHasAvailability(snapshot.dayData)) {
      hopsRemaining -= 1;
      const next = new Date(resState.baseStart);
      next.setDate(next.getDate() + WINDOW_DAYS);
      resState.baseStart = startOfDay(next) || next;
      resState.selectedDayIndex = 0;
      resState.slot = null;
      snapshot = await buildWindowSnapshot(resState.baseStart);
    }

    resState.autoSeekBudget = hopsRemaining;
    const { days, dayData, timeRows } = snapshot;

    if (rsRange) {
      if (days.length) {
        const from = days[0].toLocaleDateString(locale, {month:'short', day:'numeric'});
        const to   = days[days.length-1].toLocaleDateString(locale, {month:'short', day:'numeric'});
        rsRange.textContent = `${from} – ${to}`;
      } else {
        rsRange.textContent = '—';
      }
    }

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
      setTextKey(rsMobileHint, 'dashboard.reschedule.hint', null, 'Tap a date to see available times.');
    }

    renderDesktopGrid(locale);
    renderMobileLayout(locale);

    resSubmit.disabled = !resState.slot;
  }

  function renderDesktopGrid(locale = resState.locale || getLocale()){
    if (!rsGrid) return;
    const guardText = resolveGuardMessage(resState.guardMessage);
    if (guardText){
      rsGrid.innerHTML = `<div class="p-4 text-sm text-center">${guardText}</div>`;
      if (rsRange) rsRange.textContent = '—';
      if (resSubmit) resSubmit.disabled = true;
      return;
    }
    const days = resState.days || [];
    const dayData = resState.dayData || [];
    const timeRows = resState.timeRows || [];
    if (!days.length || !timeRows.length){
      rsGrid.innerHTML = `<div class="p-4 text-sm text-center" data-i18n="dashboard.reschedule.noAvailability">${translate('dashboard.reschedule.noAvailability', null, 'No availability')}</div>`;
      if (resSubmit) resSubmit.disabled = true;
      return;
    }

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
    const guardText = resolveGuardMessage(resState.guardMessage);
    if (guardText){
      rsMobileTimes.innerHTML = '';
      if (rsMobileEmpty){
        clearTextKey(rsMobileEmpty);
        rsMobileEmpty.textContent = guardText;
        rsMobileEmpty.classList.remove('hidden');
      }
      if (resSubmit) resSubmit.disabled = true;
      return;
    }

    if (!days.length){
      rsMobileTimes.innerHTML = '';
      if (rsMobileEmpty){
        setTextKey(rsMobileEmpty, 'dashboard.reschedule.noAvailability', null, 'No availability yet.');
        rsMobileEmpty.classList.remove('hidden');
      }
      return;
    }

    if (rsMobileEmpty){
      rsMobileEmpty.classList.add('hidden');
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
      renderWindow({ autoSeek: false }).catch(()=>{});
    }, 180);
  });

  async function shiftWindow(delta){
    const d=new Date(resState.baseStart); d.setDate(d.getDate()+delta); d.setHours(0,0,0,0); resState.baseStart = d;
    resState.selectedDayIndex = 0;
    resState.slot = null;
    resSubmit.disabled = true;
    await renderWindow({ autoSeek: false });
  }

  bind(resMaster, 'change', async ()=>{
    resState.masterId = normalizeId(resMaster.value) || null;
    resState.slot = null;
    if (resSubmit) resSubmit.disabled = true;
    resState.cache.clear();
    resState.selectedDayIndex = 0;
    resState.guardMessage = null;
    if (resErr) { resErr.classList.add('hidden'); clearTextKey(resErr); }
    if (resOk) { resOk.classList.add('hidden'); clearTextKey(resOk); }
    if (!resState.masterId){
      resState.guardMessage = {
        key: 'services.modal.masterHintSelect',
        vars: { service: resState.serviceName || '' },
        fallback: 'Select a master to view availability.'
      };
      syncResMasterHint();
      renderWindow({ autoSeek: false });
      return;
    }
    resState.preferredMasterId = resState.masterId;
    syncResMasterHint();
    resState.autoSeekBudget = AUTO_WINDOW_HOPS;
    await renderWindow({ autoSeek: true });
  });
  bind(rsPrev, 'click', ()=>shiftWindow(-WINDOW_DAYS));
  bind(rsNext, 'click', ()=>shiftWindow(WINDOW_DAYS));
  bind(rsToday, 'click', async ()=>{
    const d = getTodayStart();
    resState.baseStart = d;
    resState.slot = null;
    resState.selectedDayIndex = 0;
    resState.autoSeekBudget = AUTO_WINDOW_HOPS;
    await renderWindow({ autoSeek: true });
  });
  bind(rsCurrent, 'click', async ()=>{
    if (!resState.apptStart) return;
    const anchor = startOfDay(resState.apptStart);
    if (!anchor) return;
    resState.baseStart = anchor;
    resState.slot = null;
    resState.selectedDayIndex = 0;
    resState.autoSeekBudget = 0;
    await renderWindow({ autoSeek: false });
  });

  // UX: Shift+Wheel — горизонтальный скролл
  bind(rsWrap, 'wheel', (e)=>{
    if(e.shiftKey && Math.abs(e.deltaY)>Math.abs(e.deltaX)){
      e.preventDefault();
      rsWrap.scrollLeft += e.deltaY;
    }
  }, {passive:false});

  async function submitRes(){
    if(!resState.apptId || !resState.slot || !resSubmit) return;
    resSubmit.disabled = true;
    if (resErr) { resErr.classList.add('hidden'); clearTextKey(resErr); }
    if (resOk) { resOk.classList.add('hidden'); clearTextKey(resOk); }
    try{
      const response = await fetch(`/accounts/api/appointment/${resState.apptId}/reschedule/`, {
        method:'POST',
        headers:{'Content-Type':'application/json','X-CSRFToken': csrftoken},
        credentials:'same-origin',
        body: JSON.stringify({ start_time: resState.slot, master: resState.masterId, item_id: resState.itemId })
      });
      const data = await response.json().catch(()=> ({}));
      if(response.ok){
        const startISO = data.appointment?.start_time || '';
        const locale = getLocale();
        const localized = startISO ? new Date(startISO).toLocaleString(locale) : '';
        if (resOk) {
          setTextKey(resOk, 'dashboard.reschedule.success', { datetime: localized }, `Rescheduled to ${localized}`);
          resOk.classList.remove('hidden');
        }
        const mutated = applyRescheduleResult(data);
        resState.slot = null;
        if(!mutated){
          window.setTimeout(()=> location.reload(), 500);
        }else{
          enforce24hLock();
        }
        resSubmit.disabled = true;
      }else{
        const fallback = data.error || data.detail;
        if(resErr){
          resErr.classList.remove('hidden');
          if(fallback){
            clearTextKey(resErr);
            resErr.textContent = fallback;
          }else{
            setTextKey(resErr, 'dashboard.reschedule.failed');
          }
        }else if(fallback){
          alert(fallback);
        }
        resSubmit.disabled = false;
      }
    }catch(err){
      if(resErr){
        resErr.classList.remove('hidden');
        const message = err && err.message ? err.message : '';
        if(message){
          clearTextKey(resErr);
          resErr.textContent = message;
        }else{
          setTextKey(resErr, 'dashboard.reschedule.failed');
        }
      }
      resSubmit.disabled = false;
    }
  }

  document.addEventListener('click', (event)=>{
    const target = event.target;
    if (!(target instanceof Element)) return;
    const trigger = target.closest('.appt-reschedule');
    if(!trigger) return;
    if (trigger.hasAttribute('aria-disabled') || trigger.classList.contains('is-disabled')) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    const dataset = trigger.dataset || {};
    const apptId = dataset.apptId;
    const serviceId = dataset.serviceId;
    const itemId = dataset.itemId || '';
    const masterId = dataset.masterId || '';
    const fallbackAppt = trigger.closest('[data-appt-start-iso]');
    const startIso = dataset.startIso || fallbackAppt?.getAttribute('data-appt-start-iso') || '';
    const serviceName = dataset.serviceName || trigger.getAttribute('data-service-name') || '';
    openRes(apptId, serviceId, itemId, { masterId, startIso, serviceName });
  });
  bind(resClose, 'click', closeRes);
  bind(resCancel, 'click', closeRes);
  if (resModal) {
    resModal.addEventListener('click', (event)=>{
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (target === resModal) closeRes();
    });
  }
  bind(resSubmit, 'click', submitRes);

  applyServiceNameTranslations();
  enforce24hLock();

  if (I18N && typeof I18N.onChange === 'function') {
    I18N.onChange(() => {
      applyServiceNameTranslations();
      enforce24hLock();
      if (resModal && resModal.classList.contains('flex')) {
        renderWindow({ autoSeek: false }).catch(()=>{});
      }
      if (statsChart) {
        statsChart.data.datasets[0].label = translate('dashboard.chartLabel', null, 'Appointments');
        statsChart.update();
      }
    });
  }
});

// --- Mobile collapsible list for appointments (or any list) ---
(() => {
  const SELECTOR = '[data-collapse-mobile]';
  const mql = window.matchMedia('(max-width: 900px)');
  const instances = new Map();

  function measure(container){
    const first = container.firstElementChild;
    if (!first) return;
    // Height = first item + bottom spacing
    const cr = container.getBoundingClientRect();
    const fr = first.getBoundingClientRect();
    const csFirst = getComputedStyle(first);
    const gap = parseFloat(csFirst.marginBottom || '0')
             || parseFloat(getComputedStyle(container).rowGap || '0')
             || parseFloat(getComputedStyle(container).gap || '0')
             || 0;
    const h = Math.max(0, Math.ceil(fr.bottom - cr.top + gap));
    container.style.setProperty('--collapsed-height', `${h}px`);
    if (!container.classList.contains('is-open')) {
      container.style.maxHeight = `${h}px`;
    }
  }

  function attach(container){
    if (instances.has(container)) return;

    // Insert the toggle button after the container
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'collapse-toggle';
    btn.setAttribute('aria-expanded', 'false');
    btn.innerHTML = `<span class="collapse-toggle__label">Show more</span>
                     <span class="collapse-toggle__icon" aria-hidden="true">▾</span>`;
    container.parentNode.insertBefore(btn, container.nextSibling);

    const toggle = () => {
      const open = btn.getAttribute('aria-expanded') === 'true';
      if (open) {
        btn.setAttribute('aria-expanded', 'false');
        container.classList.remove('is-open');
        const h = container.style.getPropertyValue('--collapsed-height') || '0px';
        container.style.maxHeight = h;
        btn.querySelector('.collapse-toggle__label').textContent = 'Show more';
      } else {
        btn.setAttribute('aria-expanded', 'true');
        container.classList.add('is-open');
        container.style.maxHeight = 'none';
        btn.querySelector('.collapse-toggle__label').textContent = 'Show less';
      }
    };
    btn.addEventListener('click', toggle);

    // Keep size correct on content changes/resizes
    let ro = null;
    if ('ResizeObserver' in window) {
      ro = new ResizeObserver(() => measure(container));
      ro.observe(container);
      if (container.firstElementChild) ro.observe(container.firstElementChild);
    }
    const sync = () => {
      if (mql.matches) {
        container.classList.remove('is-open');
        btn.setAttribute('aria-expanded', 'false');
        btn.style.display = '';
        measure(container);
      } else {
        container.style.maxHeight = '';
        btn.style.display = 'none';
      }
    };
    sync();
    if (mql.addEventListener) mql.addEventListener('change', sync);
    else mql.addListener(sync);

    instances.set(container, { btn, ro, sync });
  }

  function init(){
    document.querySelectorAll(SELECTOR).forEach(attach);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
