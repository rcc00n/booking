(function(){
      let detailCtaHandlerBound = false;
      function handleServiceCardCtaClick(event){
        if (event.defaultPrevented) return;
        if (typeof event.button === 'number' && event.button !== 0) return;
        const target = event.target;
        if (!(target instanceof Element)) return;
        const btn = target.closest('.service-card__cta');
        if (!btn) return;
        const card = btn.closest('[data-service-card]');
        if (!card) return;
        event.preventDefault();
        event.stopPropagation();
        openServiceDetail(card, btn);
      }
      const initMainmenuInteractions = () => {
        if (!detailCtaHandlerBound) {
          document.addEventListener('click', handleServiceCardCtaClick);
          detailCtaHandlerBound = true;
        } 
        try {
      const I18N = window.MalvaI18n;
      const bind = (node, event, handler, options) => {
        if (node) {
          node.addEventListener(event, handler, options);
        }
      };
      const getNestedValue = (source, path) => {
        if (!source || !Array.isArray(path) || path.length === 0) {
          return source;
        }
        let current = source;
        for (let i = 0; i < path.length; i += 1) {
          if (current === undefined || current === null) {
            return undefined;
          }
          current = current[path[i]];
        }
        return current;
      };
      const bodyDataset = document.body && document.body.dataset ? document.body.dataset : null;
      const serverContentNode = document.getElementById('serverContent');
      const userMenu = document.querySelector('[data-user-menu]');
      if (userMenu) {
        const trigger = userMenu.querySelector('[data-user-menu-trigger]');
        const dropdown = userMenu.querySelector('[data-user-menu-dropdown]');
        const closeUserMenu = () => {
          userMenu.classList.remove('is-open');
          if (trigger) trigger.setAttribute('aria-expanded', 'false');
        };
        const toggleUserMenu = () => {
          const isOpen = userMenu.classList.toggle('is-open');
          if (trigger) trigger.setAttribute('aria-expanded', String(isOpen));
        };
        if (trigger) {
          trigger.addEventListener('click', (event) => {
            event.preventDefault();
            toggleUserMenu();
          });
        }
        document.addEventListener('click', (event) => {
          if (!userMenu.contains(event.target)) {
            closeUserMenu();
          }
        });
        document.addEventListener('keydown', (event) => {
          if (event.key === 'Escape') {
            closeUserMenu();
          }
        });
      }
      const resolvedUserId = bodyDataset && bodyDataset.autofillUser ? String(bodyDataset.autofillUser) : 'guest';
      const autofillScriptNode = document.getElementById('autofill-defaults');
      let autofillDefaults = {};
      if (autofillScriptNode) {
        try {
          autofillDefaults = JSON.parse(autofillScriptNode.textContent) || {};
        } catch (err) {
          console.warn('[mainmenu] Failed to parse autofill defaults', err);
          autofillDefaults = {};
        }
      }
      const autofillApi = window.MalvaAutofill;
      const profileDefaults = autofillDefaults.profile || {};
      const paymentDefaults = autofillDefaults.payment || {};
      const paymentEndpoint = bodyDataset && bodyDataset.autofillPaymentEndpoint ? bodyDataset.autofillPaymentEndpoint : '';
      const csrftoken = (document.cookie.match('(^|;)\\s*csrftoken\\s*=\\s*([^;]+)')||[])[2] || '';
      const paymentAllowedKeys = ['name', 'email', 'phone', 'address_line1', 'address_line2', 'city', 'state', 'postal_code', 'country'];
      const paymentFormEl = document.getElementById('paymentForm');
      const paymentFields = paymentFormEl ? {
        name: document.getElementById('paymentName'),
        email: document.getElementById('paymentEmail'),
        address_line1: document.getElementById('paymentAddress1'),
        address_line2: document.getElementById('paymentAddress2'),
        city: document.getElementById('paymentCity'),
        state: document.getElementById('paymentState'),
        postal_code: document.getElementById('paymentPostal'),
        country: document.getElementById('paymentCountry'),
      } : {};

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
          const billingContact = data && data.billing_contact ? data.billing_contact : {};
          const updatedMeta = data && data.updated_at ? { updated_at: data.updated_at } : {};
          autofillDefaults.payment = Object.assign({}, billingContact, updatedMeta);
        } catch (err) {
          console.warn('[mainmenu] Unable to sync payment contact', err);
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

      const collectPaymentValues = () => {
        const data = {};
        Object.entries(paymentFields).forEach(([key, element]) => {
          if (element && element.value) {
            data[key] = element.value;
          }
        });
        return data;
      };

      const hydratePaymentFromProfile = (persistToStorage) => {
        if (!paymentFormEl) {
          return false;
        }
        const fields = {
          name: paymentFields.name,
          email: paymentFields.email,
          address_line1: paymentFields.address_line1,
          address_line2: paymentFields.address_line2,
          city: paymentFields.city,
          state: paymentFields.state,
          postal_code: paymentFields.postal_code,
          country: paymentFields.country,
        };
        const setIfEmpty = (element, value) => {
          if (!element || !value || element.value) {
            return false;
          }
          element.value = value;
          if (element.tagName === 'SELECT') {
            element.dispatchEvent(new Event('change', { bubbles: true }));
          }
          return true;
        };
        let hydrated = false;
        Object.entries(paymentDefaults).forEach(([key, value]) => {
          if (!fields[key]) return;
          hydrated = setIfEmpty(fields[key], value) || hydrated;
        });
        const fullName = `${profileDefaults.first_name || ''} ${profileDefaults.last_name || ''}`.trim();
        hydrated = setIfEmpty(fields.name, fullName) || hydrated;
        hydrated = setIfEmpty(fields.email, profileDefaults.email) || hydrated;
        if (profileDefaults.address) {
          const addressParts = String(profileDefaults.address).split(/\n+/);
          hydrated = setIfEmpty(fields.address_line1, addressParts[0]) || hydrated;
          if (addressParts.length > 1) {
            hydrated = setIfEmpty(fields.address_line2, addressParts[1]) || hydrated;
          }
        }
        if (profileDefaults.postal_code) {
          hydrated = setIfEmpty(fields.postal_code, profileDefaults.postal_code) || hydrated;
          if (profileDefaults.postal_code.toUpperCase().startsWith('T')) {
            hydrated = setIfEmpty(fields.state, 'Alberta') || hydrated;
            if (fields.country && !fields.country.value) {
              fields.country.value = 'CA';
              fields.country.dispatchEvent(new Event('change', { bubbles: true }));
              hydrated = true;
            }
          }
        }
        if (hydrated && persistToStorage && autofillApi) {
          const payload = {};
          Object.entries(fields).forEach(([key, element]) => {
            if (element && element.value) {
              payload[key] = element.value;
            }
          });
          if (Object.keys(payload).length) {
            autofillApi.save('payment', payload, { userId: resolvedUserId });
            persistPaymentContact(payload, { immediate: true });
          }
        }
        return hydrated;
      };
      if (paymentFormEl) {
        try {
          if (autofillApi) {
            autofillApi.attach(paymentFormEl, { userId: resolvedUserId });
            const storedPayment = autofillApi.load('payment', { userId: resolvedUserId });
            const hasStoredPayment = storedPayment && Object.keys(storedPayment.values || {}).length > 0;
            if (!hasStoredPayment) {
              const hydrated = hydratePaymentFromProfile(true);
              if (!hydrated && paymentDefaults && Object.keys(paymentDefaults).length) {
                persistPaymentContact(paymentDefaults, { immediate: true });
              }
            }
          } else if (Object.keys(profileDefaults).length) {
            hydratePaymentFromProfile(false);
          }
          if (paymentEndpoint) {
            const eventType = (field) => (field && (field.tagName === 'SELECT' || field.type === 'checkbox' || field.type === 'radio') ? 'change' : 'input');
            Object.values(paymentFields).forEach((field) => {
              if (!field) return;
              field.addEventListener(eventType(field), () => {
                const payload = collectPaymentValues();
                persistPaymentContact(payload);
              });
            });
          }
        } catch (err) {
          console.error('[services] Payment autofill failed', err);
        }
      }
      if (autofillApi && paymentEndpoint) {
        try {
          autofillApi.subscribe(({ group, userId, state }) => {
            if (group !== 'payment') return;
            if (String(userId || 'guest') !== resolvedUserId) return;
            const values = (state && state.values) || (state && state.state && state.state.values) || {};
            if (!Object.keys(values).length) {
              return;
            }
            persistPaymentContact(values, { immediate: true });
          });
        } catch (err) {
          console.error('[services] Payment autofill subscription failed', err);
        }
      }
      let refreshPending = false;
      const queueRefresh = () => {
        if (!I18N || typeof I18N.refresh !== 'function' || refreshPending) {
          return;
        }
        refreshPending = true;
        window.requestAnimationFrame(() => {
          refreshPending = false;
          I18N.refresh({ silent: true });
        });
      };
      function translate(key, vars, fallback) {
        if (!key) {
          return fallback !== undefined ? fallback : '';
        }
        let result;
        if (I18N && typeof I18N.t === 'function') {
          try {
            result = I18N.t(key, vars);
          } catch (err) {
            result = undefined;
          }
        }
        const resultIsString = typeof result === 'string';
        const normalized = resultIsString ? result.trim() : result;
        const shouldFallback =
          result === undefined ||
          result === null ||
          (resultIsString && normalized === '') ||
          (resultIsString && normalized === key);
        if (shouldFallback) {
          if (fallback !== undefined) {
            return fallback;
          }
          if (resultIsString && normalized) {
            return result;
          }
          return key;
        }
        return result;
      }
      const mainmenuConfig = window.MalvaMainmenuConfig || {};
      const defaultPrepaymentPercent =
        Number(mainmenuConfig.defaultPrepaymentPercent ?? 100) || 100;
      const stripePublicKey = mainmenuConfig.stripePublicKey || "";
      let stripeClient = null;
      let stripeElements = null;
      let stripeCardElement = null;
      let stripeCardComplete = false;
      let currentPaymentContext = null;
      let currentPrepaymentPercent = defaultPrepaymentPercent;
      let lastPrepaymentQuote = null;
      let lastPrepaymentCartId = null;
      const PAYMENT_COPY = {
        title: 'Secure payment',
        summary: (amount, percent = 100) => percent < 100
          ? `Pay ${percent}% now: ${amount}.`
          : `Complete your payment of ${amount}.`,
        amountLabel: (percent = 100) => percent < 100 ? `Paying now (${percent}%)` : 'Amount due',
        feeLabel: (percent = 100) => percent < 100 ? `Card fee on ${percent}%` : 'Card processing fee',
        feeNotice: (fee, percent = 100) => percent < 100
          ? `Today's charge includes ${fee} card processing fee.`
          : `Includes ${fee} card processing fee (3% + $0.50).`,
        button: (percent = 100) => percent < 100 ? `Pay ${percent}% now` : 'Pay now',
        partialNote: (percent = 100) => `Remaining ${Math.max(0, 100 - percent)}% will be due in person or later.`,
        missingKey: 'Payments are temporarily unavailable.',
        noCharge: (amount) => `No payment needed (${amount}).`,
        offline: (amount) => `Payments are currently handled offline. Click "Confirm booking" to finish.`,
        enterCard: 'Enter your card details to finish.',
        processing: 'Processing payment…',
        verifyFailed: 'Unable to verify payment.',
        failedGeneric: 'Payment did not complete. Please try again.',
        failedShort: 'Payment failed.',
        success: 'Payment confirmed! Redirecting…',
      };
      const setTextKey = (el, key, vars, fallback) => {
        if (!el) return;

        const resolved = key
          ? translate(key, vars, fallback !== undefined ? fallback : el.textContent)
          : fallback;
        if (resolved !== undefined && resolved !== null) {
          el.textContent = resolved;
        }

        if (I18N && key) {
          el.setAttribute('data-i18n', key);
          if (vars) {
            el.setAttribute('data-i18n-vars', JSON.stringify(vars));
          } else {
            el.removeAttribute('data-i18n-vars');
          }
          queueRefresh();
        } else if (!key) {
          el.removeAttribute('data-i18n');
          el.removeAttribute('data-i18n-vars');
        }
      };
      const clearTextKey = (el) => {
        if (!el) return;
        el.removeAttribute('data-i18n');
        el.removeAttribute('data-i18n-vars');
      };
      const formatMinutes = (minutes) => translate('services.units.minutes', { value: String(minutes) }, `${minutes} min`);
      const getLocale = () => (I18N && typeof I18N.getLocale === 'function'
        ? I18N.getLocale()
        : (navigator.languages && navigator.languages[0]) || navigator.language || 'en');
      const getCurrentLang = () => (I18N && typeof I18N.getCurrent === 'function'
        ? I18N.getCurrent()
        : (document.documentElement && document.documentElement.getAttribute('lang')) || 'en');
      const isEnglish = (lang) => !lang || lang === 'en';
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
      const bindServiceCardInteractions = (root) => {
        const scope = root instanceof Element ? root : document;
        const cards = scope.querySelectorAll('[data-service-card]');
        cards.forEach((card) => {
          if (card.dataset.cardBound === '1') return;
          card.dataset.cardBound = '1';
          card.addEventListener('click', (event) => {
            if (event.defaultPrevented) return;
            const target = event.target;
            if (target instanceof Element && target.closest('.service-card__payload')) {
              return;
            }
            event.preventDefault();
            openServiceDetail(card, card);
          });
          card.addEventListener('keydown', (event) => {
            if (event.defaultPrevented) return;
            if (event.key !== 'Enter' && event.key !== ' ') return;
            event.preventDefault();
            openServiceDetail(card, card);
          });
        });
      };
      const attachServiceCardBindings = (root) => {
        if (!root) return;
        try {
          bindServiceCardInteractions(root);
          applyServiceNameTranslations(root);
        } catch (err) {
          console.warn('[mainmenu] attachServiceCardBindings failed', err);
        }
      };
      attachServiceCardBindings(serverContentNode);
      const servicePayloadCache = new WeakMap();
      const serializeServicePayload = (value) => {
        try {
          return JSON.stringify(value)
            .replace(/</g, '\\u003C')
            .replace(/>/g, '\\u003E')
            .replace(/\u2028/g, '\\u2028')
            .replace(/\u2029/g, '\\u2029');
        } catch (err) {
          console.warn('[mainmenu] Failed to serialize service payload', err);
          return '{}';
        }
      };
      const readServicePayload = (card) => {
        if (!card) return null;
        if (servicePayloadCache.has(card)) return servicePayloadCache.get(card);
        const script = card.querySelector('.service-card__payload');
        if (!script) return null;
        try {
          const payload = JSON.parse(script.textContent || '{}');
          servicePayloadCache.set(card, payload);
          return payload;
        } catch (err) {
          console.warn('[mainmenu] Failed to parse service payload', err);
          return null;
        }
      };
      const translationEndpoint = '/accounts/api/services/translations/';
      let translationRequest = null;

      const collectVisibleIds = () => {
        const serviceIds = new Set();
        const categoryIds = new Set();
        document.querySelectorAll('[data-service-card]').forEach((card) => {
          const payload = readServicePayload(card);
          if (payload && payload.id) {
            serviceIds.add(String(payload.id));
          }
          if (payload && payload.category_id) {
            categoryIds.add(String(payload.category_id));
          }
        });
        document.querySelectorAll('[data-category-id]').forEach((el) => {
          const cid = el.getAttribute('data-category-id');
          if (cid) {
            categoryIds.add(cid);
          }
        });
        return {
          services: Array.from(serviceIds),
          categories: Array.from(categoryIds),
        };
      };

      const applyCategoryLabels = (lang, categoryTranslations) => {
        const categoryMap = categoryTranslations || {};
        document.querySelectorAll('[data-category-id][data-category-name-original]').forEach((el) => {
          const cid = el.getAttribute('data-category-id');
          const original = el.getAttribute('data-category-name-original') || el.textContent || '';
          if (isEnglish(lang)) {
            el.textContent = original;
            return;
          }
          const translated = (cid && categoryMap[cid] && categoryMap[cid].name) ? categoryMap[cid].name : '';
          el.textContent = translated || original;
        });
      };

      const renderCardFromPayload = (card, payload, lang) => {
        if (!card || !payload) return;
        const nameEl = card.querySelector('[data-service-name-original]');
        const descEl = card.querySelector('.service-card__desc');
        const categoryTag = card.querySelector('[data-category-name-original]');

        const localizedName = isEnglish(lang)
          ? (payload.name || translateServiceNameText(payload.name) || translate('common.service', null, 'Service'))
          : (payload.translated_name || translateServiceNameText(payload.name) || payload.name || translate('common.service', null, 'Service'));
        if (nameEl) {
          nameEl.textContent = localizedName;
        }

        if (descEl) {
          const descSource = isEnglish(lang)
            ? (payload.description || '')
            : (payload.translated_description || payload.description || '');
          descEl.textContent = descSource ? truncateWords(descSource, 16) : '';
        }

        if (categoryTag) {
          const cid = categoryTag.getAttribute('data-category-id') || payload.category_id || '';
          const original = categoryTag.getAttribute('data-category-name-original') || payload.category || '';
          const translatedCategory = payload.translated_category || original;
          categoryTag.textContent = isEnglish(lang) ? original : (translatedCategory || original);
          if (cid) {
            categoryTag.setAttribute('data-category-id', cid);
          }
        }
      };

      const applyTranslationsToDom = (lang, data) => {
        const servicesTranslations = (data && data.services) || {};
        const categoryTranslations = (data && data.categories) || {};
        document.querySelectorAll('[data-service-card]').forEach((card) => {
          const payload = readServicePayload(card);
          if (!payload || !payload.id) return;
          const key = String(payload.id);
          if (isEnglish(lang)) {
            payload.translated_name = '';
            payload.translated_description = '';
            payload.translated_category = '';
          } else {
            const entry = servicesTranslations[key] || {};
            if (entry.name) payload.translated_name = entry.name;
            if (entry.description) payload.translated_description = entry.description;
            if (entry.category) payload.translated_category = entry.category;
            if (!payload.translated_category && payload.category_id) {
              const catEntry = categoryTranslations[payload.category_id];
              if (catEntry && catEntry.name) {
                payload.translated_category = catEntry.name;
              }
            }
          }
          renderCardFromPayload(card, payload, lang);
        });

        applyCategoryLabels(lang, categoryTranslations);
        if (activeServiceDetail && activeServiceDetail.payload) {
          hydrateServiceDetail(activeServiceDetail.payload);
        }
      };

      const refreshTranslations = async (lang) => {
        const targetLang = lang || getCurrentLang();
        if (isEnglish(targetLang)) {
          applyTranslationsToDom('en', { services: {}, categories: {} });
          return;
        }
        const { services, categories } = collectVisibleIds();
        if (!services.length && !categories.length) {
          return;
        }
        const payload = JSON.stringify({
          lang: targetLang,
          services,
          categories,
        });
        const request = fetch(translationEndpoint, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken,
          },
          body: payload,
        });
        translationRequest = request;
        try {
          const response = await request;
          if (!response.ok) {
            throw new Error(`Translation request failed: ${response.status}`);
          }
          const data = await response.json();
          applyTranslationsToDom(targetLang, data);
        } catch (err) {
          console.warn('[mainmenu] translation fetch failed', err);
        } finally {
          if (translationRequest === request) {
            translationRequest = null;
          }
        }
      };
      const formatPriceDisplay = (value) => {
        if (value === null || value === undefined || value === '') {
          return '$0.00';
        }
        const num = Number(value);
        if (!Number.isNaN(num)) {
          return `$${num.toFixed(2)}`;
        }
        return typeof value === 'string' && value.trim() ? value : '$0.00';
      };
      const FOCUSABLE_SELECTORS = 'a[href],area[href],input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),button:not([disabled]),summary,[tabindex]:not([tabindex="-1"]),[contenteditable="true"]';

      const menuToggle = document.querySelector('[data-menu-toggle]');
      const menuClose = document.querySelector('[data-menu-close]');
      const menuDrawer = document.querySelector('[data-menu-drawer]');
      const menuBackdrop = document.querySelector('[data-menu-backdrop]');

      const navScrollLock = {
        active: false,
        y: 0,
        previous: {
          position: '',
          top: '',
          width: '',
        },
      };
      const lockMenuScroll = () => {
        if (navScrollLock.active) return;
        navScrollLock.active = true;
        navScrollLock.y = window.scrollY || document.documentElement.scrollTop || 0;
        navScrollLock.previous.position = document.body.style.position || '';
        navScrollLock.previous.top = document.body.style.top || '';
        navScrollLock.previous.width = document.body.style.width || '';
        document.body.style.position = 'fixed';
        document.body.style.top = `-${navScrollLock.y}px`;
        document.body.style.width = '100%';
      };
      const unlockMenuScroll = () => {
        if (!navScrollLock.active) return;
        navScrollLock.active = false;
        document.body.style.position = navScrollLock.previous.position;
        document.body.style.top = navScrollLock.previous.top;
        document.body.style.width = navScrollLock.previous.width;
        window.scrollTo(0, navScrollLock.y);
        navScrollLock.previous = { position: '', top: '', width: '' };
        navScrollLock.y = 0;
      };
      let menuKeydownHandler = null;
      const focusMenuDrawer = () => {
        if (!menuDrawer) return;
        window.requestAnimationFrame(() => focusElement(menuDrawer));
      };
      const attachMenuFocusTrap = () => {
        if (menuKeydownHandler || !menuDrawer) return;
        menuKeydownHandler = (event) => {
          if (!document.body.classList.contains('nav-open')) return;
          if (event.key === 'Escape') {
            event.preventDefault();
            closeMenuDrawer();
            return;
          }
          if (event.key !== 'Tab') return;
          const focusables = collectFocusable(menuDrawer);
          if (!focusables.length) return;
          const first = focusables[0];
          const last = focusables[focusables.length - 1];
          const active = document.activeElement;
          if (event.shiftKey) {
            if (active === first || !menuDrawer.contains(active)) {
              event.preventDefault();
              focusElement(last);
            }
          } else if (active === last) {
            event.preventDefault();
            focusElement(first);
          }
        };
        document.addEventListener('keydown', menuKeydownHandler, true);
      };
      const detachMenuFocusTrap = () => {
        if (!menuKeydownHandler) return;
        document.removeEventListener('keydown', menuKeydownHandler, true);
        menuKeydownHandler = null;
      };

      const openMenuDrawer = () => {
        if (document.body.classList.contains('nav-open')) return;
        document.body.classList.add('nav-open');
        document.documentElement.classList.add('nav-open');
        lockMenuScroll();
        if (menuToggle) {
          menuToggle.setAttribute('aria-expanded', 'true');
        }
        if (menuDrawer) {
          menuDrawer.setAttribute('aria-hidden', 'false');
          menuDrawer.scrollTop = 0;
        }
        attachMenuFocusTrap();
        focusMenuDrawer();
      };
      const closeMenuDrawer = () => {
        document.body.classList.remove('nav-open');
        document.documentElement.classList.remove('nav-open');
        if (menuToggle) {
          menuToggle.setAttribute('aria-expanded', 'false');
        }
        if (menuDrawer) {
          menuDrawer.setAttribute('aria-hidden', 'true');
        }
        detachMenuFocusTrap();
        unlockMenuScroll();
      };

      if (menuToggle) {
        menuToggle.addEventListener('click', () => {
          if (document.body.classList.contains('nav-open')) {
            closeMenuDrawer();
          } else {
            openMenuDrawer();
          }
        });
      }
      if (menuClose) {
        menuClose.addEventListener('click', closeMenuDrawer);
      }
      if (menuBackdrop) {
        menuBackdrop.addEventListener('click', closeMenuDrawer);
      }
      if (menuDrawer) {
        menuDrawer.addEventListener('click', (event) => {
          if (window.innerWidth <= 900 && event.target.closest('a')) {
            closeMenuDrawer();
            return;
          }
          event.stopPropagation();
        });
      }
      window.addEventListener('resize', () => {
        if (window.innerWidth > 900) closeMenuDrawer();
      });

            // --- Mobile drawer portal: prevent fixed-position clipping in Safari/iOS ---
      (() => {
        const drawer = document.querySelector('[data-menu-drawer]');
        if (!drawer) return;

        const placeholder = document.createComment('nav-drawer-placeholder');
        let portaled = false;

        const toBody = () => {
          if (portaled) return;
          if (drawer.parentNode) {
            drawer.parentNode.insertBefore(placeholder, drawer);
          }
          document.body.appendChild(drawer);
          portaled = true;
        };

        const toOriginal = () => {
          if (!portaled) return;
          if (placeholder.parentNode) {
            placeholder.parentNode.insertBefore(drawer, placeholder);
            placeholder.remove();
          }
          portaled = false;
        };

        const mq = window.matchMedia('(max-width: 900px)');
        const sync = () => (mq.matches ? toBody() : toOriginal());

        // Initial placement + responsive updates
        sync();
        if (mq.addEventListener) mq.addEventListener('change', sync);
        else mq.addListener(sync);
      })();


      const isAuth = Boolean(mainmenuConfig.isAuthenticated);
      const loginUrl =
        typeof mainmenuConfig.loginUrl === "string" && mainmenuConfig.loginUrl.length
          ? mainmenuConfig.loginUrl
          : "/accounts/login/";
      const apiAvail= "/accounts/api/availability/";
      const apiCart = "/accounts/api/cart/";
      const apiCartAdd = "/accounts/api/cart/add/";
      const apiStripeCartIntent = "/accounts/api/payments/cart/create-intent/";
      const apiStripeCartFinalize = "/accounts/api/payments/cart/finalize/";
      const cartRemoveUrl = (id)=>`/accounts/api/cart/${id}/remove/`;
      const paymentVerifyUrl = (id)=>`/accounts/api/appointment/${id}/payments/verify/`;

      // ===== helpers =====
      function getCookie(name){ const m=document.cookie.match('(^|;)\\s*'+name+'\\s*=\\s*([^;]+)'); return m?m.pop():''; }
      function ymd(d){ const m=String(d.getMonth()+1).padStart(2,'0'); const day=String(d.getDate()).padStart(2,'0'); return `${d.getFullYear()}-${m}-${day}`; }
      function parseISO(iso){ try{return new Date(iso);}catch(_){return null;} }
      function fmtHM(d){ return d.toLocaleTimeString(getLocale(), {hour:'numeric', minute:'2-digit'}); }
      function fmtTime(iso){ try { return new Date(iso).toLocaleTimeString(getLocale(), {hour:'2-digit', minute:'2-digit'}); } catch(e){ return iso; } }

      // ===== modal nodes =====
      const modal=document.getElementById('bookModal');
      const btnClose=document.getElementById('bookClose');
      const btnCancel=document.getElementById('bookCancel');
      const btnSubmit=document.getElementById('bookSubmit');
      const elServiceName=document.getElementById('bookServiceName');
      const elMaster=document.getElementById('bookMaster');
      const elMasterHint=document.getElementById('bookMasterHint');
      const elSummary=document.getElementById('bookSummary');
      const bookCartPreview=document.getElementById('bookCartPreview');
      const bookCartEmpty=document.getElementById('bookCartEmpty');
      const elError=document.getElementById('bookError');
      const elSuccess=document.getElementById('bookSuccess');
      const cartBtn=document.getElementById('cartButton');
      const cartModal=document.getElementById('cartModal');
      const cartClose=document.getElementById('cartClose');
      const cartItems=document.getElementById('cartItems');
      const cartEmpty=document.getElementById('cartEmpty');
      const cartError=document.getElementById('cartError');
      const cartSuccess=document.getElementById('cartSuccess');
      const cartSummary=document.getElementById('cartSummary');
      const cartFeeNotice=document.getElementById('cartFeeNotice');
      const cartCheckout=document.getElementById('cartCheckout');
      const cartCount=document.getElementById('cartCount');
      const floatingCartBtn=document.getElementById('floatingCart');
      const floatingCartCount=document.getElementById('floatingCartCount');
      const paymentModal=document.getElementById('paymentModal');
      const paymentClose=document.getElementById('paymentClose');
      const paymentConfirm=document.getElementById('paymentConfirm');
      const paymentSummary=document.getElementById('paymentSummary');
      const paymentFeeNotice=document.getElementById('paymentFeeNotice');
      const paymentTitle=document.getElementById('paymentTitle');
      const paymentCardLabel=document.querySelector('label[for="cardElement"]');
      const cardElementWrapper=document.getElementById('cardElementWrapper');
      const cardElementTarget=document.getElementById('cardElement');
      const paymentForm=document.getElementById('paymentForm');
      const paymentSummaryAmount=document.getElementById('paymentSummaryAmount');
      const paymentSummaryTime=document.getElementById('paymentSummaryTime');
      const paymentSummaryItems=document.getElementById('paymentSummaryItems');
      const paymentFeeLine=document.getElementById('paymentFeeLine');
      const paymentFeeLineAmount=document.getElementById('paymentFeeLineAmount');
      const paymentSummaryLabel=document.getElementById('paymentSummaryLabel');
      const paymentFeeLineLabel=document.getElementById('paymentFeeLineLabel');
      const paymentOptionGroup=document.getElementById('paymentOptionGroup');
      const paymentPartialNote=document.getElementById('paymentPartialNote');
      const paymentMessage=document.getElementById('paymentMessage');
      const detailModal=document.getElementById('serviceDetailModal');
      const detailImage=document.getElementById('serviceDetailImage');
      const detailImageEmpty=document.getElementById('serviceDetailImageEmpty');
      const detailBadge=document.getElementById('serviceDetailBadge');
      const detailName=document.getElementById('serviceDetailName');
      const detailCategory=document.getElementById('serviceDetailCategory');
      const detailCategoryLabel=document.getElementById('serviceDetailCategoryLabel');
      const detailDescription=document.getElementById('serviceDetailDescription');
      const detailDuration=document.getElementById('serviceDetailDuration');
      const detailExtra=document.getElementById('serviceDetailExtra');
      const detailPriceOld=document.getElementById('serviceDetailPriceOld');
      const detailPriceCurrent=document.getElementById('serviceDetailPriceCurrent');
      const detailDiscount=document.getElementById('serviceDetailDiscount');
      const detailFormsList=document.getElementById('serviceDetailFormsList');
      const detailFormsFootnote=document.getElementById('serviceDetailFormsFootnote');
      const detailBook=document.getElementById('serviceDetailBook');
      const detailClose=document.getElementById('serviceDetailClose');
      const detailDismiss=document.getElementById('serviceDetailDismiss');
      const detailBody=document.getElementById('serviceDetailBody');
      const detailDialog=detailModal ? detailModal.querySelector('.service-detail') : null;
      const inputName=document.getElementById('paymentName');
      const inputEmail=document.getElementById('paymentEmail');
      const inputAddress1=document.getElementById('paymentAddress1');
      const inputAddress2=document.getElementById('paymentAddress2');
      const inputCity=document.getElementById('paymentCity');
      const inputState=document.getElementById('paymentState');
      const inputPostal=document.getElementById('paymentPostal');
      const inputCountry=document.getElementById('paymentCountry');

      function hideMasterHint(){
        if (!elMasterHint) return;
        elMasterHint.hidden = true;
        elMasterHint.textContent = '';
      }

      function showMasterHint(key, vars, fallback){
        if (!elMasterHint) return;
        const fallbackText = typeof fallback === 'string' ? fallback : '';
        let resolved = fallbackText;
        if (key){
          const translated = translate(key, vars);
          if (translated && translated !== key){
            resolved = translated;
          }
        }
        elMasterHint.textContent = resolved;
        elMasterHint.hidden = !resolved;
      }

      syncPrepaymentInputs(currentPrepaymentPercent);

      const BODY_MODAL_CLASS = 'modal-open';
      const MASTER_REQUIRED_GUARD = {
        key: 'services.modal.masterRequired',
        fallback: 'Select a master to view availability.'
      };

      const modalState = {
        current: null,
        dialog: null,
        restoreFocus: null,
        restoreFocusFallback: null,
        inertRecords: [],
        keydownHandler: null,
        onRequestClose: null,
      };

      function getModalDialog(el){
        if(!el) return null;
        return el.querySelector('.modal__dialog') || el;
      }

      function isFocusable(element){
        if(!(element instanceof HTMLElement) && !(element instanceof SVGElement)) return false;
        if(element.hasAttribute('disabled')) return false;
        if(element.getAttribute('aria-hidden') === 'true') return false;
        if(element.hidden) return false;
        const style = window.getComputedStyle(element);
        if(style.display === 'none' || style.visibility === 'hidden') return false;
        return true;
      }

      function collectFocusable(container){
        if(!container) return [];
        return Array.from(container.querySelectorAll(FOCUSABLE_SELECTORS)).filter(isFocusable);
      }

      function focusElement(el){
        if(!el || typeof el.focus !== 'function') return;
        try{
          el.focus({ preventScroll:true });
        }catch(_){
          try{
            el.focus();
          }catch(__){}
        }
      }

      function canRestoreFocusTo(el){
        if(!el || typeof el.focus !== 'function') return false;
        if(!el.isConnected) return false;
        if(!document.body.contains(el)) return false;
        if(el.closest('[aria-hidden="true"]')) return false;
        if(el.closest('[inert]')) return false;
        return true;
      }

      function setBackgroundInert(except){
        const records = [];
        const nodes = Array.from(document.body.children);
        nodes.forEach((node)=>{
          if(node === except) return;
          if(!(node instanceof HTMLElement)) return;
          if(node.hasAttribute('data-modal-ignore')) return;
          if(node.hasAttribute('inert')) return;
          node.setAttribute('inert','');
          records.push(node);
        });
        return records;
      }

      function clearBackgroundInert(records){
        if(!Array.isArray(records)) return;
        records.forEach((node)=>{
          if(node && node.hasAttribute && node.hasAttribute('inert')){
            node.removeAttribute('inert');
          }
        });
      }

      function focusModalDialog(dialog, selector){
        if(!dialog) return;
        let target = null;
        if(selector){
          try{
            target = dialog.querySelector(selector);
          }catch(_){
            target = null;
          }
        }
        if(!(target instanceof HTMLElement || target instanceof SVGElement)){
          target = dialog.querySelector('[autofocus]');
        }
        if(!(target instanceof HTMLElement || target instanceof SVGElement)){
          const focusables = collectFocusable(dialog);
          target = focusables[0];
        }
        if(!(target instanceof HTMLElement || target instanceof SVGElement)){
          if(!dialog.hasAttribute('tabindex')){
            dialog.setAttribute('tabindex','-1');
          }
          target = dialog;
        }
        focusElement(target);
      }

      function handleModalKeydown(event){
        const { current, dialog, onRequestClose } = modalState;
        if(!current || !dialog) return;
        if(!current.classList.contains('modal--open')) return;
        if(event.key === 'Escape'){
          event.preventDefault();
          event.stopPropagation();
          if(typeof onRequestClose === 'function'){
            onRequestClose(event);
          }else{
            closeModalElement(current);
          }
          return;
        }
        if(event.key === 'Tab'){
          const focusables = collectFocusable(dialog);
          if(focusables.length === 0){
            event.preventDefault();
            event.stopPropagation();
            focusElement(dialog);
            return;
          }
          const first = focusables[0];
          const last = focusables[focusables.length-1];
          const active = document.activeElement;
          if(event.shiftKey){
            if(active === first || !dialog.contains(active)){
              event.preventDefault();
              event.stopPropagation();
              focusElement(last);
            }
          }else{
            if(active === last || !dialog.contains(active)){
              event.preventDefault();
              event.stopPropagation();
              focusElement(first);
            }
          }
        }
      }

      function openModalElement(el, options = {}){
        if(!el) return;
        const dialog = getModalDialog(el);
        if(modalState.current && modalState.current !== el){
          if(typeof modalState.onRequestClose === 'function'){
            modalState.onRequestClose({ restoreFocus:false });
          }else{
            closeModalElement(modalState.current, { restoreFocus:false });
          }
        }
        const activeElement = document.activeElement;
        const trigger = options.trigger instanceof HTMLElement || options.trigger instanceof SVGElement
          ? options.trigger
          : (activeElement instanceof HTMLElement || activeElement instanceof SVGElement ? activeElement : null);

        modalState.current = el;
        modalState.dialog = dialog;
        modalState.restoreFocus = trigger;
        modalState.restoreFocusFallback = options.restoreFocusFallback instanceof HTMLElement || options.restoreFocusFallback instanceof SVGElement
          ? options.restoreFocusFallback
          : null;
        modalState.onRequestClose = typeof options.onRequestClose === 'function' ? options.onRequestClose : null;

        modalState.inertRecords = setBackgroundInert(el);

        el.classList.add('modal--open');
        el.removeAttribute('aria-hidden');
        document.body.classList.add(BODY_MODAL_CLASS);
        if(dialog && !dialog.hasAttribute('tabindex')){
          dialog.setAttribute('tabindex','-1');
        }

        const selector = options.initialFocusSelector || el.getAttribute('data-initial-focus') || (dialog ? dialog.getAttribute('data-initial-focus') : null);
        window.requestAnimationFrame(()=>{ focusModalDialog(dialog, selector); });

        if(!modalState.keydownHandler){
          modalState.keydownHandler = (event)=>handleModalKeydown(event);
          document.addEventListener('keydown', modalState.keydownHandler, true);
        }
      }

      function closeModalElement(el, options = {}){
        if(!el) return;
        const wasActive = modalState.current === el;
        el.classList.remove('modal--open');

        if(wasActive){
          clearBackgroundInert(modalState.inertRecords);
          modalState.inertRecords = [];
          if(modalState.keydownHandler){
            document.removeEventListener('keydown', modalState.keydownHandler, true);
            modalState.keydownHandler = null;
          }
          const shouldRestore = options.restoreFocus !== false;
          const focusTarget = modalState.restoreFocus;
          const focusFallback = modalState.restoreFocusFallback;
          modalState.current = null;
          modalState.dialog = null;
          modalState.restoreFocus = null;
          modalState.restoreFocusFallback = null;
          modalState.onRequestClose = null;
          let ariaHiddenUpdateScheduled = false;

          if(shouldRestore){
            let nextFocus = canRestoreFocusTo(focusTarget) ? focusTarget : null;
            if(!nextFocus && canRestoreFocusTo(focusFallback)){
              nextFocus = focusFallback;
            }
            if(nextFocus){
              ariaHiddenUpdateScheduled = true;
              window.requestAnimationFrame(()=>{
                focusElement(nextFocus);
                el.setAttribute('aria-hidden','true');
              });
            }
          }
          if(!ariaHiddenUpdateScheduled){
            el.setAttribute('aria-hidden','true');
          }
        } else {
          el.setAttribute('aria-hidden','true');
        }

        if(!document.querySelector('.modal.modal--open')){
          document.body.classList.remove(BODY_MODAL_CLASS);
        }
      }

      if(floatingCartBtn){
        floatingCartBtn.setAttribute('aria-hidden','true');
        floatingCartBtn.tabIndex = -1;
      }

      let summaryState = { key: 'services.modal.summaryPlaceholder', vars: null };
      let cartState = {
        items: [],
        count: 0,
        total: 0,
        total_price: '0.00',
        total_decimal: '0.00',
        total_display: 'CA$0.00',
        pre_fee_total: 0,
        pre_fee_total_decimal: '0.00',
        pre_fee_total_display: 'CA$0.00',
        processing_fee: 0,
        processing_fee_decimal: '0.00',
        processing_fee_display: 'CA$0.00',
        total_duration_min: 0,
        currency: 'cad'
      };
      const cartSlotsByMaster = new Map();
      const cartSlotsNoMaster = new Set();
      let scheduleState = {
        days: [],
        dayData: [],
        timeRows: [],
        locale: getLocale(),
        selectedDate: null,
        guardMessage: null,
      };
      let lastCartOpener = null;

      function rebuildCartSlotIndex(){
        cartSlotsByMaster.clear();
        cartSlotsNoMaster.clear();
        const items = Array.isArray(cartState && cartState.items) ? cartState.items : [];
        items.forEach((item) => {
          const iso = item ? item.start_time : null;
          if (!iso) return;
          const ts = Date.parse(iso);
          if (!Number.isFinite(ts)) return;
          const masterId = getNestedValue(item, ['master', 'id']);
          if (masterId !== undefined && masterId !== null){
            const key = String(masterId);
            if (!cartSlotsByMaster.has(key)){
              cartSlotsByMaster.set(key, new Set());
            }
            cartSlotsByMaster.get(key).add(ts);
          }else{
            cartSlotsNoMaster.add(ts);
          }
        });
      }

      function slotIsInCart(masterId, iso){
        if (!iso) return false;
        const ts = Date.parse(iso);
        if (!Number.isFinite(ts)) return false;
        if (masterId !== null && masterId !== undefined){
          const key = String(masterId);
          const slots = cartSlotsByMaster.get(key);
          if (slots && slots.has(ts)) return true;
        }
        return cartSlotsNoMaster.has(ts);
      }

      function normalizeMasterValue(value){
        if (value === undefined || value === null) return null;
        const str = typeof value === 'string' ? value.trim() : String(value).trim();
        if (!str) return null;
        const num = Number(str);
        return Number.isFinite(num) ? num : str;
      }

      function getActiveMasterValue(){
        if (elMaster){
          const normalized = normalizeMasterValue(elMaster.value);
          if (normalized !== null && normalized !== undefined){
            return normalized;
          }
        }
        if (current && current.masterId !== null && current.masterId !== undefined){
          return current.masterId;
        }
        return null;
      }

      function getSelectedMasterKey(){
        const active = getActiveMasterValue();
        return active !== null && active !== undefined ? String(active) : null;
      }

      function updateBookCartPreview(){
        if (!bookCartPreview) return;
        const items = Array.isArray(cartState && cartState.items) ? cartState.items : [];
        bookCartPreview.innerHTML = '';

        if (!items.length){
          if (bookCartEmpty){
            bookCartEmpty.style.display = 'block';
            setTextKey(bookCartEmpty, 'services.modal.cartPreviewEmpty', null, 'Add services to your cart to see them here.');
            bookCartPreview.appendChild(bookCartEmpty);
          }
          return;
        }

        const currency = (cartState && cartState.currency) || 'cad';
        if (bookCartEmpty){
          bookCartEmpty.style.display = 'none';
        }

        items.forEach((item) => {
          const card = document.createElement('div');
          card.className = 'book-cart-preview__item';

          const title = document.createElement('strong');
          const rawName = getNestedValue(item, ['service', 'name']) || getNestedValue(item, ['name']) || '';
          title.textContent = translateServiceNameText(rawName) || rawName || translate('common.service', null, 'Service');
          card.appendChild(title);

          const meta = document.createElement('div');
          meta.className = 'book-cart-preview__meta';
          const masterName = getNestedValue(item, ['master', 'name']) || translate('services.modal.cartPreviewUnknownMaster', null, 'Any master');
          const slotStart = item ? item.start_time : null;
          const timeLabel = slotStart ? fmtDateTime(slotStart) : translate('common.noTime', null, 'No time');
          const hasDirectDuration = item && Number.isFinite(item.duration_min);
          const durationValue = hasDirectDuration
            ? item.duration_min
            : ((getNestedValue(item, ['service', 'duration_min']) || 0) + (getNestedValue(item, ['service', 'extra_time_min']) || 0));
          const durationText = formatMinutes(durationValue);
          meta.textContent = translate(
            'services.modal.cartPreviewMeta',
            { master: masterName, time: timeLabel, duration: durationText },
            `${masterName} · ${timeLabel} · ${durationText}`
          );
          card.appendChild(meta);

          const unitPriceDisplay = getNestedValue(item, ['unit_price_display']);
          const servicePriceDisplay = getNestedValue(item, ['service', 'price_display']);
          const unitPriceDecimal = getNestedValue(item, ['unit_price_decimal']);
          const priceValue = unitPriceDisplay
            || servicePriceDisplay
            || (unitPriceDecimal ? formatCurrency(unitPriceDecimal, currency) : '');
          if (priceValue){
            const price = document.createElement('div');
            price.className = 'book-cart-preview__meta';
            price.textContent = priceValue;
            card.appendChild(price);
          }

          bookCartPreview.appendChild(card);
        });

        const totalDisplay = (cartState && cartState.total_display)
          || formatCurrency((cartState && (cartState.total_decimal || cartState.total_price)) || '0', currency);
        const durationText = formatMinutes((cartState && cartState.total_duration_min) || 0);
        const totals = document.createElement('div');
        totals.className = 'book-cart-preview__totals';
        totals.textContent = translate(
          'services.modal.cartPreviewTotals',
          { total: totalDisplay, duration: durationText },
          `Total: ${totalDisplay} • ${durationText}`
        );
        bookCartPreview.appendChild(totals);

        const feeMinor = Number((cartState && cartState.processing_fee) || 0);
        if (feeMinor > 0){
          const feeDisplay = (cartState && cartState.processing_fee_display)
            || formatCurrency((cartState && cartState.processing_fee_decimal) || (feeMinor / 100), currency);
          const feeNote = document.createElement('div');
          feeNote.className = 'book-cart-preview__note';
          feeNote.textContent = translate(
            'services.modal.cartPreviewFee',
            { fee: feeDisplay },
            `${feeDisplay} card processing fee (3% + $0.50) included.`
          );
          bookCartPreview.appendChild(feeNote);
        }
      }

      function fmtDateTime(iso){
        try{
          const d=new Date(iso);
          return `${d.toLocaleDateString(getLocale())} ${d.toLocaleTimeString(getLocale(), {hour:'2-digit', minute:'2-digit'})}`;
        }catch(_){
          return iso;
        }
      }

      function formatCurrency(amount, currency){
        try{
          return new Intl.NumberFormat(getLocale(), {style:'currency', currency:(currency||'CAD').toUpperCase()}).format(Number(amount||0));
        }catch(_){
          return `${(currency||'CAD').toUpperCase()} ${amount}`;
        }
      }

      function syncPrepaymentInputs(percent){
        if (!paymentOptionGroup) return;
        const inputs = paymentOptionGroup.querySelectorAll('input[name="prepaymentPercent"]');
        inputs.forEach((input)=>{ input.checked = Number(input.value) === Number(percent); });
      }

      function setPaymentOptionLoading(loading){
        if (!paymentOptionGroup) return;
        paymentOptionGroup.classList.toggle('is-loading', Boolean(loading));
        const inputs = paymentOptionGroup.querySelectorAll('input[name="prepaymentPercent"]');
        inputs.forEach((input)=>{ input.disabled = Boolean(loading); });
      }

      function clearPrepaymentQuote(){
        lastPrepaymentQuote = null;
        lastPrepaymentCartId = null;
      }

      function resolveActivePrepaymentPercent(context){
        if (context && context.payment && Number.isFinite(context.payment.prepayment_percent)){
          return Number(context.payment.prepayment_percent);
        }
        if (lastPrepaymentQuote && Number.isFinite(lastPrepaymentQuote.percent)){
          return Number(lastPrepaymentQuote.percent);
        }
        if (Number.isFinite(currentPrepaymentPercent)){
          return Number(currentPrepaymentPercent);
        }
        return defaultPrepaymentPercent;
      }

      function updatePaymentButtonLabel(){
        if (!paymentConfirm || paymentConfirm.classList.contains('btn--loading')) return;
        const requiresCard = currentPaymentContext ? Boolean(getNestedValue(currentPaymentContext, ['payment', 'client_secret'])) : true;
        if (!requiresCard){
          paymentConfirm.textContent = translate('services.payment.confirmButton', null, 'Confirm booking');
          return;
        }
        const percent = resolveActivePrepaymentPercent(currentPaymentContext);
        paymentConfirm.textContent = PAYMENT_COPY.button(percent);
      }

      function renderPaymentSummary(context){
        const payment = context && context.payment ? context.payment : {};
        const prepayment = context && context.prepayment ? context.prepayment : lastPrepaymentQuote;
        const percent = resolveActivePrepaymentPercent({ payment });
        const currency = payment.currency || (cartState && cartState.currency) || 'cad';
        const amountDecimal = (prepayment && prepayment.total_decimal) || payment.amount || '0';
        const amountText = formatCurrency(amountDecimal, currency);
        if (paymentSummary){
          paymentSummary.textContent = PAYMENT_COPY.summary(amountText, percent);
        }
        if (paymentSummaryAmount){
          paymentSummaryAmount.textContent = amountText;
        }
        if (paymentSummaryLabel){
          paymentSummaryLabel.textContent = PAYMENT_COPY.amountLabel(percent);
        }
        const feeMinor = Number((prepayment && prepayment.processing_fee_minor) || 0);
        const feeDisplay = feeMinor > 0
          ? (prepayment && prepayment.processing_fee_decimal
            ? formatCurrency(prepayment.processing_fee_decimal, currency)
            : formatCurrency(feeMinor / 100, currency))
          : null;
        if (paymentFeeLine){
          if (feeDisplay){
            paymentFeeLine.style.display = '';
            if (paymentFeeLineLabel){
              paymentFeeLineLabel.textContent = PAYMENT_COPY.feeLabel(percent);
            }
            if (paymentFeeLineAmount){
              paymentFeeLineAmount.textContent = feeDisplay;
            }
          }else{
            paymentFeeLine.style.display = 'none';
          }
        }
        if (paymentFeeNotice){
          if (feeDisplay){
            paymentFeeNotice.style.display = '';
            paymentFeeNotice.textContent = PAYMENT_COPY.feeNotice(feeDisplay, percent);
          }else{
            paymentFeeNotice.style.display = 'none';
            paymentFeeNotice.textContent = '';
          }
        }
        if (paymentPartialNote){
          if (percent < 100){
            paymentPartialNote.style.display = '';
            setTextKey(
              paymentPartialNote,
              'services.payment.partialNote',
              { remaining: `${Math.max(0, 100 - percent)}%` },
              PAYMENT_COPY.partialNote(percent)
            );
          }else{
            paymentPartialNote.style.display = 'none';
            clearTextKey(paymentPartialNote);
          }
        }
        updatePaymentButtonLabel();
      }

      function applyCartPrepaymentDecorators(cartData, currency){
        if (!cartData) return;
        const cartId = cartData.cart_id ? String(cartData.cart_id) : null;
        let quote = null;
        if (cartId && lastPrepaymentCartId && String(lastPrepaymentCartId) === cartId){
          quote = lastPrepaymentQuote;
        }
        if (!quote || !quote.percent || quote.percent === 100){
          return;
        }
        const durationText = formatMinutes(cartData.total_duration_min || 0);
        const amountDisplay = formatCurrency(quote.total_decimal || (quote.total_minor / 100), currency);
        if (cartSummary){
          setTextKey(
            cartSummary,
            'services.cart.summaryPartial',
            { total: amountDisplay, duration: durationText, percent: `${quote.percent}%` },
            `Paying now (${quote.percent}%): ${amountDisplay} - ${durationText}`
          );
        }
        if (cartFeeNotice){
          const feeDisplay = formatCurrency(
            quote.processing_fee_decimal || (quote.processing_fee_minor / 100),
            currency
          );
          cartFeeNotice.style.display = 'block';
          setTextKey(
            cartFeeNotice,
            'services.cart.partialFeeNotice',
            {
              fee: feeDisplay,
              percent: `${quote.percent}%`,
              remaining: `${Math.max(0, 100 - quote.percent)}%`,
            },
            `Today's charge includes ${feeDisplay} in card fees. Remaining ${Math.max(0, 100 - quote.percent)}% due later.`
          );
        }
      }

      function resetPaymentForm(){
        if (paymentForm) {
          paymentForm.reset();
        }
        if (paymentConfirm) {
          paymentConfirm.onclick = null;
        }
        stripeCardComplete = false;
        if (stripeCardElement) {
          stripeCardElement.clear();
        }
        if (cardElementWrapper) {
          cardElementWrapper.classList.remove('is-visible');
        }
        if (paymentFeeLine) {
          paymentFeeLine.style.display = 'none';
        }
        if (paymentFeeNotice) {
          paymentFeeNotice.style.display = 'none';
          paymentFeeNotice.textContent = '';
        }
        if (paymentPartialNote){
          paymentPartialNote.style.display = 'none';
          clearTextKey(paymentPartialNote);
        }
        setPaymentOptionLoading(false);
        if (inputCountry) {
          const defaultOption = Array.from(inputCountry.options).find(opt => opt.value === 'CA');
          const fallbackOption = inputCountry.options.length ? inputCountry.options[0].value : '';
          inputCountry.value = defaultOption ? 'CA' : fallbackOption;
        }
        setPaymentMessage(null);
        setConfirmLoading(false);
      }

      function normalizePostal(value){
        const raw = (value || '').toUpperCase().replace(/\s+/g, '');
        if (/^[A-Z]\d[A-Z]\d[A-Z]\d$/.test(raw)){
          return raw.replace(/(.{3})(?=.)/, '$1 ');
        }
        return raw;
      }

      const emailRegex = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
      const readFieldValue = (field) => (field && typeof field.value === 'string' ? field.value : '');

      function gatherBillingDetails(){
        const name = readFieldValue(inputName).trim();
        const email = readFieldValue(inputEmail).trim();
        const line1 = readFieldValue(inputAddress1).trim();
        const line2Raw = readFieldValue(inputAddress2).trim();
        const city = readFieldValue(inputCity).trim();
        const state = readFieldValue(inputState).trim();
        const postal = normalizePostal(readFieldValue(inputPostal));
        const country = readFieldValue(inputCountry).trim();
        return {
          name,
          email,
          address: {
            line1,
            line2: line2Raw || undefined,
            city,
            state,
            postal_code: postal,
            country,
          },
        };
      }

      function checkPaymentForm(){
        if (!paymentConfirm) return;
        const details = gatherBillingDetails();
        const requiresCard = Boolean(getNestedValue(currentPaymentContext, ['payment', 'client_secret']));
        if (!requiresCard){
          paymentConfirm.disabled = false;
          return;
        }
        const requiredFilled = [
          details.name,
          details.email && emailRegex.test(details.email),
          details.address.line1,
          details.address.city,
          details.address.state,
          details.address.postal_code,
          details.address.country,
        ].every(Boolean);
        const cardReady = requiresCard ? stripeCardComplete : true;
        const ready = requiredFilled && cardReady;
        paymentConfirm.disabled = !ready;
      }

      function setConfirmLoading(loading){
        if (!paymentConfirm) return;
        if (loading){
          paymentConfirm.classList.add('btn--loading');
          paymentConfirm.textContent = 'Processing…';
          paymentConfirm.disabled = true;
        } else {
          paymentConfirm.classList.remove('btn--loading');
          updatePaymentButtonLabel();
          checkPaymentForm();
        }
      }

      function setCartMessage(kind, key, vars, fallback){
        if (cartError) {
          cartError.style.display = 'none';
          cartError.textContent = '';
          clearTextKey(cartError);
        }
        if (cartSuccess) {
          cartSuccess.style.display = 'none';
          cartSuccess.textContent = '';
          clearTextKey(cartSuccess);
        }
        if (!kind) return;
        const target = kind === 'error' ? cartError : cartSuccess;
        if (!target) return;
        target.style.display = 'block';
        if (key) {
          setTextKey(target, key, vars, fallback);
        } else if (fallback !== undefined) {
          target.textContent = fallback;
        }
      }

      function setPaymentMessage(kind, message){
        if (!paymentMessage) return;
        paymentMessage.style.display = message ? 'block' : 'none';
        paymentMessage.textContent = message || '';
        paymentMessage.classList.remove('payment-status--error', 'payment-status--success', 'payment-status--info');
        if (!message) return;
        const map = {
          error: 'payment-status--error',
          success: 'payment-status--success',
          status: 'payment-status--info',
        };
        const cls = map[kind] || map.status;
        paymentMessage.classList.add(cls);
      }

      function ensureStripe(){
        if (!stripePublicKey) return null;
        if (!window.Stripe) return null;
        if (!stripeClient){
          stripeClient = window.Stripe(stripePublicKey);
          stripeElements = stripeClient.elements({
            appearance: {
              theme: 'flat',
              variables: {
                colorText: '#204029',
                colorPrimary: '#AF9525',
                fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
                borderRadius: '12px',
              },
            },
          });
        }
        if (!stripeCardElement && cardElementTarget){
          stripeCardElement = stripeElements.create('card', {
            hidePostalCode: true,
            style: {
              base: {
                color: '#204029',
                fontFamily: 'Inter, "Segoe UI", sans-serif',
                fontSize: '16px',
                '::placeholder': { color: 'rgba(77,77,77,.55)' },
                iconColor: '#AF9525',
              },
              invalid: { color: '#d6453d' },
            },
          });
          stripeCardElement.mount('#cardElement');
          stripeCardElement.on('change', (event) => {
            stripeCardComplete = Boolean(event.complete);
            if (event.error) {
              setPaymentMessage('error', event.error.message);
            } else if (paymentMessage && paymentMessage.classList.contains('payment-status--error')) {
              setPaymentMessage(null);
            }
            checkPaymentForm();
          });
        }
        if (!stripeClient) return null;
        if (!stripeElements){
          stripeElements = stripeClient.elements({
            appearance: {
              theme: 'flat',
              variables: {
                colorText: '#204029',
                colorPrimary: '#AF9525',
                fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
                borderRadius: '12px',
              },
            },
          });
        }
        if (!stripeCardElement && cardElementTarget){
          stripeCardElement = stripeElements.create('card', {
            hidePostalCode: true,
            style: {
              base: {
                color: '#204029',
                fontFamily: 'Inter, "Segoe UI", sans-serif',
                fontSize: '16px',
                '::placeholder': { color: 'rgba(77,77,77,.55)' },
                iconColor: '#AF9525',
              },
              invalid: { color: '#d6453d' },
            },
          });
          stripeCardElement.mount('#cardElement');
          stripeCardElement.on('change', (event) => {
            stripeCardComplete = Boolean(event.complete);
            if (event.error) {
              setPaymentMessage('error', event.error.message);
            } else if (paymentMessage && paymentMessage.classList.contains('payment-status--error')) {
              setPaymentMessage(null);
            }
            checkPaymentForm();
          });
        }
        return stripeClient;
      }


function updateCartUI(data){
  if(!data) return;
  cartState = data;
  if(!cartState.currency){
    cartState.currency = data.currency || 'cad';
  }
  const currency = data.currency || cartState.currency || 'cad';
  const items = Array.isArray(data.items) ? data.items : [];
  const count = Number(
    Number.isFinite(data.count) ? data.count : items.length
  );
  if (!count){
    clearPrepaymentQuote();
  }
  if (data.cart_id){
    cartState.cart_id = data.cart_id;
  }
  if(cartCount){ cartCount.textContent = count; }
  if(floatingCartCount){ floatingCartCount.textContent = count; }
  if(floatingCartBtn){
    const hasItems = count > 0;
    floatingCartBtn.classList.toggle('floating-cart--visible', hasItems);
    floatingCartBtn.setAttribute('aria-hidden', hasItems ? 'false' : 'true');
    floatingCartBtn.tabIndex = hasItems ? 0 : -1;
  }

  if(cartItems){
    cartItems.innerHTML='';
    if(items.length){
      cartItems.style.display='flex';
      items.forEach(item=>{
        const row=document.createElement('div');
        row.className='cart-item';
        row.dataset.itemId=item.id;

        const info=document.createElement('div');
        info.className='cart-item__info';

        const rawName=getNestedValue(item, ['service','name']) || getNestedValue(item, ['name']) || '';
        const translatedName=translateServiceNameText(rawName) || translate('common.service', null, 'Service');
        const title=document.createElement('strong');
        title.textContent=translatedName;
        info.appendChild(title);

        const meta=document.createElement('div');
        meta.className='cart-item__meta';
        const masterName=getNestedValue(item, ['master','name']) || '-';
        const slotIso=item ? item.start_time : null;
        const timeLabel=slotIso ? fmtDateTime(slotIso) : translate('common.noTime', null, 'No time');
        const hasDuration=item && Number.isFinite(item.duration_min);
        const durationValue = hasDuration
          ? item.duration_min
          : ((getNestedValue(item, ['service','duration_min']) || 0) + (getNestedValue(item, ['service','extra_time_min']) || 0));
        meta.textContent = `${masterName} - ${timeLabel} - ${formatMinutes(durationValue)}`;
        info.appendChild(meta);

        const unitDisplay=getNestedValue(item, ['unit_price_display']);
        const serviceDisplay=getNestedValue(item, ['service','price_display']);
        const unitDecimal=getNestedValue(item, ['unit_price_decimal']);
        const servicePrice=getNestedValue(item, ['service','price']);
        const priceValue = unitDisplay
          || serviceDisplay
          || (unitDecimal ? formatCurrency(unitDecimal, currency) : '')
          || (servicePrice ? formatCurrency(servicePrice, currency) : '');
        if(priceValue){
          const price=document.createElement('div');
          price.className='cart-item__meta';
          price.textContent=priceValue;
          info.appendChild(price);
        }

        const discounts = getNestedValue(item, ['discounts']);
        if(Array.isArray(discounts) && discounts.length){
          const discountLine=document.createElement('div');
          discountLine.className='cart-item__meta';
          const discountText=discounts.map(d=>{
            const amount=(d && d.amount_display) || formatCurrency((d && d.amount_decimal) || 0, currency);
            const label=(d && d.label) || translate('services.cart.discount', null, 'Discount');
            return `-${amount} ${label}`.trim();
          }).join(', ');
          discountLine.textContent=discountText;
          info.appendChild(discountLine);
        }

        row.appendChild(info);

        const remove=document.createElement('button');
        remove.type='button';
        remove.className='cart-remove';
        remove.dataset.removeId=item.id;
        const img = document.createElement('img');
        img.src = '/static/admin/icons/delete.svg';        // absolute path to the remove icon asset
        img.alt = '';                                      // keep aria-label on button instead of the image
        img.width = 24;                                    // icon size
        img.height = 24;
        img.decoding = 'async';
        img.loading = 'lazy';
        remove.setAttribute('aria-label', translate('services.cart.remove', null, 'Remove item'));
        remove.replaceChildren(img);   
        row.appendChild(remove);

        cartItems.appendChild(row);
      });
    }else{
      cartItems.style.display='none';
    }
  }

  if(cartEmpty){ cartEmpty.style.display = items.length ? 'none' : 'block'; }
  if(cartCheckout){ cartCheckout.disabled = !items.length; }

  if(cartSummary){
    const duration = data.total_duration_min || 0;
    const durationText = formatMinutes(duration);
    const totalDisplay = data.total_display
      || formatCurrency(data.total_decimal || data.total_price || '0', currency);
    setTextKey(
      cartSummary,
      'services.cart.summary',
      { total: totalDisplay, duration: durationText },
      `Total: ${totalDisplay} - ${durationText}`
    );
  }

  if (cartFeeNotice){
    const feeMinor = Number(data.processing_fee || 0);
    if (feeMinor > 0){
      const feeDisplay = data.processing_fee_display
        || formatCurrency(data.processing_fee_decimal || (feeMinor / 100), currency);
      cartFeeNotice.style.display = 'block';
      setTextKey(
        cartFeeNotice,
        'services.cart.processingFeeNotice',
        { fee: feeDisplay },
        `${feeDisplay} card processing fee (3% + $0.50) is included in the total.`
      );
    }else{
      cartFeeNotice.style.display = 'none';
      clearTextKey(cartFeeNotice);
    }
  }
  applyCartPrepaymentDecorators(data, currency);

  rebuildCartSlotIndex();
  updateBookCartPreview();
  if (modal && modal.classList && modal.classList.contains('modal--open')){
    const locale = (scheduleState && scheduleState.locale) || getLocale();
    renderDesktopSchedule(locale);
    renderMobileSchedule(locale);
  }
}

      if (I18N && typeof I18N.onChange === 'function') {
        I18N.onChange(() => {
          applyServiceNameTranslations();
          if (elServiceName && elServiceName.getAttribute('data-service-name-original')) {
            elServiceName.textContent = translateServiceNameText(elServiceName.getAttribute('data-service-name-original'));
          }
          if (cartState) {
            updateCartUI(cartState);
          }
          if (summaryState && summaryState.key) {
            setTextKey(elSummary, summaryState.key, summaryState.vars);
          }
          if (modal.classList.contains('modal--open')) {
            renderWindow().catch(()=>{});
          }
        });
      }

      async function refreshCart(silent=true){
        if(!isAuth) return;
        try{
          const resp=await fetch(apiCart, {credentials:'same-origin'});
          if(resp.status===401){
            if(cartCount) cartCount.textContent='0';
            if(floatingCartCount) floatingCartCount.textContent='0';
            if(floatingCartBtn){
              floatingCartBtn.classList.remove('floating-cart--visible');
              floatingCartBtn.setAttribute('aria-hidden','true');
              floatingCartBtn.tabIndex = -1;
            }
            cartState = {
              items: [],
              count: 0,
              total: 0,
              total_price: '0.00',
              total_decimal: '0.00',
              total_display: formatCurrency(0, (cartState && cartState.currency) || 'cad'),
              pre_fee_total: 0,
              pre_fee_total_decimal: '0.00',
              pre_fee_total_display: formatCurrency(0, (cartState && cartState.currency) || 'cad'),
              processing_fee: 0,
              processing_fee_decimal: '0.00',
              processing_fee_display: formatCurrency(0, (cartState && cartState.currency) || 'cad'),
              total_duration_min: 0,
              currency: (cartState && cartState.currency) || 'cad'
            };
            clearPrepaymentQuote();
            rebuildCartSlotIndex();
            updateBookCartPreview();
            if (modal && modal.classList && modal.classList.contains('modal--open')){
              const locale = (scheduleState && scheduleState.locale) || getLocale();
              renderDesktopSchedule(locale);
              renderMobileSchedule(locale);
            }
            return;
          }
          if(!resp.ok) throw new Error(translate('services.cart.loadFailed'));
          const data=await resp.json();
          updateCartUI(data);
          if(!silent) setCartMessage(null);
        }catch(err){
          if(!silent){
            setCartMessage('error', 'services.cart.loadFailed');
            console.error(err);
          }
        }
      }

      async function removeCartItem(id){
        if(!id) return;
        try{
          const resp=await fetch(cartRemoveUrl(id),{
            method:'POST',
            headers:{'Content-Type':'application/json','X-CSRFToken':getCookie('csrftoken')},
            credentials:'same-origin',
            body:JSON.stringify({})
          });
          const data=await resp.json().catch(()=>({}));
          if(!resp.ok){
            const message = data && (data.error || data.detail);
            throw new Error(message || translate('services.cart.removeFailed'));
          }
          setCartMessage('success','services.cart.removeSuccess');
          await refreshCart(true);
        }catch(err){
          const fallback = err && err.message;
          const defaultMessage = translate('services.cart.removeFailed');
          if(fallback && fallback !== defaultMessage){
            setCartMessage('error', null, null, fallback);
          }else{
            setCartMessage('error','services.cart.removeFailed');
          }
        }
      }

      async function requestCartIntent(percent){
        const payload = Number.isFinite(percent) ? { prepayment_percent: Number(percent) } : {};
        const resp = await fetch(apiStripeCartIntent,{
          method:'POST',
          headers:{'Content-Type':'application/json','X-CSRFToken':getCookie('csrftoken')},
          credentials:'same-origin',
          body:JSON.stringify(payload)
        });
        const data = await resp.json().catch(()=>({}));
        if(!resp.ok){
          const msg = (data && (data.error || data.detail)) ? (data.error || data.detail) : translate('services.cart.checkoutFailed');
          throw new Error(msg);
        }
        return data;
      }

      function buildPaymentContextFromResponse(data){
        const payment = {
          client_secret: data.client_secret || null,
          payment_intent_id: data.payment_intent_id || null,
          amount: data.amount || data.total_decimal || '0',
          amount_minor: Object.prototype.hasOwnProperty.call(data, 'amount_minor') ? data.amount_minor : null,
          currency: data.currency || 'cad',
          prepayment_percent: Number(data.prepayment_percent || defaultPrepaymentPercent),
        };
        const pricing = data.cart || cartState;
        const appointmentItems = Array.isArray(pricing && pricing.items) ? pricing.items : (Array.isArray(cartState.items) ? cartState.items : []);
        const firstAppointment = appointmentItems.length ? appointmentItems[0] : null;
        const primaryStart = firstAppointment && firstAppointment.start_time ? firstAppointment.start_time : null;
        return {
          payment,
          prepayment: data.prepayment || null,
          cart: pricing,
          appointment: {
            items: appointmentItems,
            start_time: primaryStart,
          },
        };
      }

      function applyPrepaymentStateFromContext(context){
        if (!context) return;
        if (context.payment && Number.isFinite(context.payment.prepayment_percent)){
          currentPrepaymentPercent = Number(context.payment.prepayment_percent);
          syncPrepaymentInputs(currentPrepaymentPercent);
        }
        lastPrepaymentQuote = context.prepayment || null;
        if (context.cart && context.cart.cart_id){
          lastPrepaymentCartId = String(context.cart.cart_id);
          if (!cartState.cart_id){
            cartState.cart_id = context.cart.cart_id;
          }
        }
        const derivedCurrency = (context && context.cart && context.cart.currency) || (cartState && cartState.currency) || 'cad';
        applyCartPrepaymentDecorators(context.cart || cartState, derivedCurrency);
      }

      async function reloadPaymentIntentForOption(percent){
        if (!isAuth) return;
        setPaymentOptionLoading(true);
        try{
          const data = await requestCartIntent(percent);
          const context = buildPaymentContextFromResponse(data);
          currentPaymentContext = context;
          applyPrepaymentStateFromContext(context);
          renderPaymentSummary(context);
          setPaymentMessage(null);
          checkPaymentForm();
        }catch(err){
          throw err;
        }finally{
          setPaymentOptionLoading(false);
        }
      }

      async function handlePrepaymentSelection(nextPercent){
        if (!Number.isFinite(nextPercent)){
          return;
        }
        const previousPercent = currentPrepaymentPercent;
        const currentPercent = getNestedValue(currentPaymentContext, ['payment', 'prepayment_percent']);
        if (nextPercent === previousPercent && currentPercent === nextPercent){
          return;
        }
        currentPrepaymentPercent = nextPercent;
        syncPrepaymentInputs(nextPercent);
        if (paymentModal && paymentModal.classList.contains('modal--open')){
          try{
            await reloadPaymentIntentForOption(nextPercent);
          }catch(err){
            currentPrepaymentPercent = previousPercent;
            syncPrepaymentInputs(previousPercent);
          }
        }else{
          applyCartPrepaymentDecorators(cartState, (cartState && cartState.currency) || 'cad');
        }
      }

      async function checkoutCart(){
        if(!cartState.items || !cartState.items.length) return;
        if(cartCheckout) cartCheckout.disabled=true;
        setCartMessage(null);
        try{
          const percent = currentPrepaymentPercent || defaultPrepaymentPercent;
          const data = await requestCartIntent(percent);
          if (data.requires_payment === false) {
            await refreshCart(true);
            const successText = data.message || translate('services.cart.freeSuccess', null, 'Appointment booked. No payment required.');
            setCartMessage('success', 'services.cart.freeSuccess', null, successText);
            const freeFallbackTarget = lastCartOpener instanceof HTMLElement ? lastCartOpener : (cartBtn instanceof HTMLElement ? cartBtn : (floatingCartBtn instanceof HTMLElement ? floatingCartBtn : null));
            closeCartModal({ restoreFocus:false, restoreFocusFallback: freeFallbackTarget });
            return;
          }
          const context = buildPaymentContextFromResponse(data);
          currentPaymentContext = context;
          applyPrepaymentStateFromContext(context);
          const checkoutTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
          const fallbackTarget = lastCartOpener instanceof HTMLElement ? lastCartOpener : (cartBtn instanceof HTMLElement ? cartBtn : (floatingCartBtn instanceof HTMLElement ? floatingCartBtn : null));
          closeCartModal({ restoreFocus:false, restoreFocusFallback: fallbackTarget });
          openPaymentModal(context, { trigger: checkoutTrigger, restoreFocusFallback: fallbackTarget });
        }catch(err){
          const fallback = err && err.message;
          const defaultMessage = translate('services.cart.checkoutFailed');
          if(fallback && fallback !== defaultMessage){
            setCartMessage('error', null, null, fallback);
          }else{
            setCartMessage('error','services.cart.checkoutFailed');
          }
        }finally{
          if(cartCheckout) cartCheckout.disabled=false;
        }
      }

      async function finalizeCartBooking(paymentIntentId, cartId){
        if(!paymentIntentId) return null;
        const payload = {
          payment_intent_id: paymentIntentId,
          cart_id: cartId || null,
        };
        const defaultMessage = translate('services.cart.finalizeFailed', null, 'Failed to finalize booking.');
        try{
          const resp = await fetch(apiStripeCartFinalize, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCookie('csrftoken'),
            },
            credentials: 'same-origin',
            body: JSON.stringify(payload),
          });
          const data = await resp.json().catch(()=>({}));
          if(!resp.ok){
            const message = data && (data.error || data.detail);
            throw new Error(message || defaultMessage);
          }
          return data;
        }catch(err){
          const msg = err && err.message ? err.message : defaultMessage;
          throw new Error(msg);
        }
      }

      async function openCartModal(event){
        closeMenuDrawer();
        if(!isAuth){ window.location=loginUrl; return; }
        const trigger = event && event.currentTarget instanceof HTMLElement
          ? event.currentTarget
          : (document.activeElement instanceof HTMLElement ? document.activeElement : null);
        const defaultCartOpener = cartBtn instanceof HTMLElement ? cartBtn : (floatingCartBtn instanceof HTMLElement ? floatingCartBtn : null);
        lastCartOpener = trigger instanceof HTMLElement && trigger !== document.body ? trigger : defaultCartOpener;
        setCartMessage(null);
        if(cartModal){
          openModalElement(cartModal, {
            trigger,
            initialFocusSelector:'#cartTitle',
            onRequestClose:(opts)=>closeCartModal(opts)
          });
        }
        await refreshCart(true);
      }

      function closeCartModal(arg){
        let options = {};
        if(arg && typeof arg === 'object'){
          if(typeof arg.preventDefault === 'function'){
            arg.preventDefault();
          }else{
            options = arg;
          }
        }
        if(cartModal){ closeModalElement(cartModal, options); }
        setCartMessage(null);
      }

      function openPaymentModal(context, options = {}){
        if(!context || !context.payment) return;
        currentPaymentContext = context;
        resetPaymentForm();
        renderPaymentSummary(context);

        const appointmentData = context.appointment || {};
        const items = Array.isArray(appointmentData.items) ? appointmentData.items : [];
        const firstItem = items.length ? items[0] : null;
        const primaryStart = appointmentData.start_time || (firstItem && firstItem.start_time) || null;
        if (paymentSummaryTime) {
          paymentSummaryTime.textContent = primaryStart ? fmtDateTime(primaryStart) : '—';
        }
        if (paymentSummaryItems) {
          paymentSummaryItems.innerHTML = '';
          if (items.length) {
            items.forEach((it) => {
              const chip = document.createElement('div');
              chip.className = 'payment-panel__chip';
              const title = document.createElement('span');
              title.textContent = getNestedValue(it, ['service', 'name']) || 'Service';
              const meta = document.createElement('div');
              meta.className = 'payment-panel__meta';
              const masterName = getNestedValue(it, ['master', 'name'])
                || getNestedValue(it, ['master', 'user', 'full_name'])
                || getNestedValue(it, ['master', 'user', 'username'])
                || 'Master';
              const slotStart = it && it.start_time ? it.start_time : null;
              const slot = slotStart ? fmtDateTime(slotStart) : 'Scheduled';
              meta.textContent = `${masterName} · ${slot}`;
              chip.appendChild(title);
              chip.appendChild(meta);
              paymentSummaryItems.appendChild(chip);
            });
          } else {
            const empty = document.createElement('div');
            empty.className = 'payment-panel__meta';
            empty.textContent = 'Service details will appear here once confirmed.';
            paymentSummaryItems.appendChild(empty);
          }
        }

        const needCard = Boolean(context.payment.client_secret);
        const amountNumeric = Number(context.payment.amount || 0);
        const zeroDue = !Number.isNaN(amountNumeric) && amountNumeric <= 0;
        if (needCard) {
          stripeCardComplete = false;
          if (cardElementWrapper) {
            cardElementWrapper.classList.add('is-visible');
          }
          const stripe = ensureStripe();
          if (!stripe) {
            setPaymentMessage('error', PAYMENT_COPY.missingKey);
          } else {
            setPaymentMessage('status', PAYMENT_COPY.enterCard);
          }
          if (paymentConfirm) {
            paymentConfirm.disabled = !stripe;
            paymentConfirm.textContent = 'Pay now';
          }
          setTimeout(() => {
            if (stripeCardElement && typeof stripeCardElement.focus === 'function') {
              stripeCardElement.focus();
            }
          }, 120);
        } else {
          stripeCardComplete = true;
          if (paymentConfirm) {
            paymentConfirm.disabled = false;
            paymentConfirm.textContent = 'Confirm booking';
          }
          if (cardElementWrapper) {
            cardElementWrapper.classList.remove('is-visible');
          }
          if (zeroDue) {
            setPaymentMessage('success', PAYMENT_COPY.noCharge(amountText));
          } else {
            setPaymentMessage('status', PAYMENT_COPY.offline(amountText));
          }
        }

        if (paymentModal) {
          const trigger = options && options.trigger instanceof HTMLElement
            ? options.trigger
            : (document.activeElement instanceof HTMLElement ? document.activeElement : null);
          const restoreFocusFallback = options && (options.restoreFocusFallback instanceof HTMLElement || options.restoreFocusFallback instanceof SVGElement)
            ? options.restoreFocusFallback
            : (lastCartOpener instanceof HTMLElement ? lastCartOpener : (cartBtn instanceof HTMLElement ? cartBtn : (floatingCartBtn instanceof HTMLElement ? floatingCartBtn : null)));
          openModalElement(paymentModal, {
            trigger,
            initialFocusSelector:'#paymentTitle',
            onRequestClose:(opts)=>closePaymentModal(opts),
            restoreFocusFallback
          });
        }

        checkPaymentForm();
      }

      function closePaymentModal(arg){
        let options = {};
        if(arg && typeof arg === 'object'){
          if(typeof arg.preventDefault === 'function'){
            arg.preventDefault();
          }else{
            options = arg;
          }
        }
        if(paymentModal){ closeModalElement(paymentModal, options); }
        setPaymentMessage(null);
        resetPaymentForm();
        currentPaymentContext = null;
      }

      function redirectAfterPayment(){
        window.setTimeout(()=>{ window.location.href='/accounts/dashboard/'; }, 1200);
      }

async function confirmPayment(){
        if (!currentPaymentContext || !currentPaymentContext.payment) return;
        const { payment } = currentPaymentContext;
        const cartId = getNestedValue(currentPaymentContext, ['cart', 'cart_id']) || null;
        const stripe = ensureStripe();
        const requiresCard = Boolean(payment.client_secret);
        if (requiresCard && !stripe){
          setPaymentMessage('error', PAYMENT_COPY.missingKey);
          return;
        }
        const details = gatherBillingDetails();
        if (requiresCard && !emailRegex.test(details.email || '')){
          setPaymentMessage('error', 'Please provide a valid email address for your receipt.');
          checkPaymentForm();
          return;
        }
        setConfirmLoading(true);
        try{
          if (!requiresCard){
            setPaymentMessage('success', PAYMENT_COPY.success);
            await refreshCart(true);
            setConfirmLoading(false);
            if (paymentConfirm) paymentConfirm.disabled = true;
            redirectAfterPayment();
            return;
          }
          setPaymentMessage('status', PAYMENT_COPY.processing);
          const result = await stripe.confirmCardPayment(payment.client_secret, {
            payment_method: {
              card: stripeCardElement,
              billing_details: {
                name: details.name || undefined,
                email: details.email || undefined,
                address: {
                  line1: details.address.line1 || undefined,
                  line2: details.address.line2 || undefined,
                  city: details.address.city || undefined,
                  state: details.address.state || undefined,
                  postal_code: details.address.postal_code || undefined,
                  country: details.address.country || undefined,
                },
              },
            },
            receipt_email: details.email || undefined,
          });
          if (result.error){
            throw new Error(result.error.message || PAYMENT_COPY.failedGeneric);
          }
          const intent = result.paymentIntent;
          if (intent && intent.status === 'succeeded'){
            try{
              await finalizeCartBooking(payment.payment_intent_id, cartId);
            }catch(finalizeErr){
              const fallback = finalizeErr && finalizeErr.message ? finalizeErr.message : translate('services.cart.finalizeFailed', null, 'Failed to finalize booking.');
              setPaymentMessage('error', fallback);
              setConfirmLoading(false);
              return;
            }
            setPaymentMessage('success', PAYMENT_COPY.success);
            await refreshCart(true);
            setConfirmLoading(false);
            if (paymentConfirm) paymentConfirm.disabled = true;
            redirectAfterPayment();
            return;
          }
          if (intent && intent.status === 'processing'){
            try{
              await finalizeCartBooking(payment.payment_intent_id, cartId);
            }catch(finalizeErr){
              const fallback = finalizeErr && finalizeErr.message ? finalizeErr.message : translate('services.cart.finalizeFailed', null, 'Failed to finalize booking.');
              setPaymentMessage('error', fallback);
              setConfirmLoading(false);
              return;
            }
            setPaymentMessage('status', PAYMENT_COPY.processing);
            await refreshCart(true);
            setConfirmLoading(false);
            if (paymentConfirm) paymentConfirm.disabled = true;
            redirectAfterPayment();
            return;
          }
          throw new Error(PAYMENT_COPY.failedShort);
        }catch(err){
          const msg = err && err.message ? err.message : PAYMENT_COPY.failedShort;
          setPaymentMessage('error', msg);
          setConfirmLoading(false);
        }
      }

      // outlook
      const olGrid=document.getElementById('olGrid');
      const olWrap=document.getElementById('olWrap');
      const olRange=document.getElementById('olRange');
      const olPrev=document.getElementById('olPrev');
      const olNext=document.getElementById('olNext');
      const olToday=document.getElementById('olToday');
      const mobileScheduleContainer = document.getElementById('bookMobile');
      const mobileDateInput = document.getElementById('bookMobileDate');
      const mobileTimeList = document.getElementById('bookMobileTimes');
      const mobileEmpty = document.getElementById('bookMobileEmpty');

      // ===== state =====
      const WINDOW_DAYS = 14;
      const START_HOUR  = 6;
      const END_HOUR    = 23;
      const STEP_MIN    = 30;

      let current={ serviceId:null, serviceName:'', masterId:null, slot:null, mastersData:[] };
      let baseStart = new Date(); baseStart.setHours(0,0,0,0);
      let availabilityCache = new Map(); // dateStr -> { set:Set(HH:MM), iso:Map(HH:MM->ISO) }
      scheduleState = {
        days: [],
        dayData: [],
        timeRows: [],
        locale: getLocale(),
        selectedDate: null,
        guardMessage: null,
      };
      let activeServiceDetail = null;

      function hydrateServiceDetail(payload){
        if (!payload) return;
        const lang = getCurrentLang();
        const resolvedName = isEnglish(lang)
          ? (payload.name || translateServiceNameText(payload.name) || translate('common.service', null, 'Service'))
          : (payload.translated_name || translateServiceNameText(payload.name) || payload.name || translate('common.service', null, 'Service'));
        if (detailName) {
          detailName.textContent = resolvedName;
        }
        const categoryFallback = translate('services.detail.unknownCategory', null, 'Uncategorized');
        const categoryLabel = isEnglish(lang)
          ? (payload.category || categoryFallback)
          : (payload.translated_category || payload.category || categoryFallback);
        if (detailCategory) {
          clearTextKey(detailCategory);
          detailCategory.textContent = categoryLabel;
        }
        if (detailCategoryLabel) {
          clearTextKey(detailCategoryLabel);
          detailCategoryLabel.textContent = categoryLabel;
        }
        if (detailDescription) {
          if (payload.description) {
            clearTextKey(detailDescription);
            const descriptionText = isEnglish(lang)
              ? payload.description
              : payload.translated_description || payload.description;
            detailDescription.textContent = descriptionText || payload.description || '';
          } else {
            setTextKey(detailDescription, 'services.detail.descriptionFallback');
          }
        }
        if (detailDuration) {
          detailDuration.textContent = formatMinutes(payload.duration_min || 0);
        }
        if (detailExtra) {
          const extra = Number(payload.extra_time_min || 0);
          if (extra > 0) {
            detailExtra.hidden = false;
            setTextKey(detailExtra, 'services.detail.metaExtraTime', { value: String(extra) }, `+${extra} min prep time`);
          } else {
            detailExtra.hidden = true;
            clearTextKey(detailExtra);
          }
        }
        if (detailPriceCurrent) {
          detailPriceCurrent.textContent = formatPriceDisplay(payload.price || payload.base_price);
        }
        if (detailPriceOld) {
          const hasDiscount = Number(payload.discount_percent || 0) > 0;
          if (hasDiscount) {
            detailPriceOld.hidden = false;
            detailPriceOld.textContent = formatPriceDisplay(payload.base_price);
          } else {
            detailPriceOld.hidden = true;
          }
        }
        if (detailDiscount) {
          const percentValue = Number(payload.discount_percent || 0);
          if (percentValue > 0) {
            detailDiscount.hidden = false;
            setTextKey(detailDiscount, 'services.detail.discountLabel', { value: String(percentValue) }, `${percentValue}% off today`);
          } else {
            detailDiscount.hidden = true;
            clearTextKey(detailDiscount);
          }
        }
        if (detailFormsList) {
          detailFormsList.innerHTML = '';
          const forms = Array.isArray(payload.forms) ? payload.forms.filter((form) => form && form.name) : [];
          if (forms.length) {
            detailFormsList.style.display = '';
            forms.forEach((form) => {
              const item = document.createElement('li');
              item.textContent = form.name;
              detailFormsList.appendChild(item);
            });
            if (detailFormsFootnote) {
              const key = forms.length === 1 ? 'services.detail.formsSingular' : 'services.detail.formsPlural';
              setTextKey(detailFormsFootnote, key, { count: String(forms.length) });
            }
          } else {
            detailFormsList.style.display = 'none';
            if (detailFormsFootnote) {
              setTextKey(detailFormsFootnote, 'services.detail.formsEmpty');
            }
          }
        }
        if (detailImage) {
          if (payload.image) {
            detailImage.hidden = false;
            detailImage.src = payload.image;
            detailImage.alt = translate('services.detail.imageAlt', { name: resolvedName }, `Preview for ${resolvedName}`);
            if (detailImageEmpty) {
              detailImageEmpty.style.display = 'none';
            }
          } else {
            detailImage.hidden = true;
            detailImage.removeAttribute('src');
            if (detailImageEmpty) {
              detailImageEmpty.style.display = 'block';
            }
          }
        }
        if (detailBadge) {
          detailBadge.style.display = 'inline-flex';
        }
      }

      function resetServiceDetailScroll(){
        if(detailDialog){
          detailDialog.scrollTop = 0;
          detailDialog.scrollLeft = 0;
        }
        if(detailBody){
          detailBody.scrollTop = 0;
        }
      }

      function openServiceDetail(card, triggerEl){
        if (!detailModal || !card) return;
        const payload = readServicePayload(card);
        if (!payload) return;
        activeServiceDetail = {
          payload,
          trigger: triggerEl instanceof HTMLElement ? triggerEl : card,
        };
        hydrateServiceDetail(payload);
        resetServiceDetailScroll();
        openModalElement(detailModal, {
          trigger: activeServiceDetail.trigger,
          initialFocusSelector:'#serviceDetailBook',
          onRequestClose:(opts)=>closeServiceDetail(opts),
        });
      }

      function closeServiceDetail(arg){
        let options = {};
        if(arg && typeof arg === 'object'){
          if(typeof arg.preventDefault === 'function'){
            arg.preventDefault();
          }else{
            options = arg;
          }
        }
        if(detailModal){
          closeModalElement(detailModal, options);
        }
        activeServiceDetail = null;
      }

      // ===== open/close =====
      function openModal(serviceId, serviceName, triggerEl){
        if(!isAuth){ window.location=loginUrl; return; }
        current={ serviceId, serviceName, masterId:null, slot:null, mastersData:[] };
        if (elServiceName) {
          elServiceName.setAttribute('data-service-name-original', serviceName || '');
          elServiceName.textContent = translateServiceNameText(serviceName);
        }
        elError.style.display='none'; elSuccess.style.display='none';
        clearTextKey(elError); clearTextKey(elSuccess);
        btnSubmit.disabled=true;
        summaryState = { key: 'services.modal.summaryPlaceholder', vars: null };
        setTextKey(elSummary, 'services.modal.summaryPlaceholder');
        resetSelection();

        availabilityCache.clear();
        baseStart = new Date(); baseStart.setHours(0,0,0,0);
        scheduleState = {
          days: [],
          dayData: [],
          timeRows: [],
          locale: getLocale(),
          selectedDate: null,
          guardMessage: null,
        };
        if (mobileTimeList) mobileTimeList.innerHTML = '';
        if (mobileEmpty) mobileEmpty.style.display = 'none';
        if (mobileDateInput){
          mobileDateInput.value = '';
          mobileDateInput.disabled = true;
        }

        const trigger = triggerEl instanceof HTMLElement ? triggerEl : (document.activeElement instanceof HTMLElement ? document.activeElement : null);
        openModalElement(modal, {
          trigger,
          initialFocusSelector:'#bookTitle',
          onRequestClose:(opts)=>closeModal(opts)
        });
        loadMastersAndRender();
      }
      function closeModal(arg){
        let options = {};
        if(arg && typeof arg === 'object'){
          if(typeof arg.preventDefault === 'function'){
            arg.preventDefault();
          }else{
            options = arg;
          }
        }
        closeModalElement(modal, options);
      }

      // ===== availability by day/master =====
      async function fetchAvailability(dayISO, masterId){
        const params = new URLSearchParams({ service: current.serviceId, date: dayISO });
        const normalizedMasterId = (() => {
          if (masterId === 0) return "0";
          if (masterId === null || masterId === undefined) return "";
          if (typeof masterId === "number" && Number.isFinite(masterId)) {
            return String(masterId);
          }
          const str = String(masterId).trim();
          return str;
        })();
        if (normalizedMasterId) {
          params.set('master', normalizedMasterId);
        }
        const r = await fetch(`${apiAvail}?${params.toString()}`, {credentials:'same-origin'});
        if(!r.ok) throw new Error(translate('services.modal.errorLoad'));
        const data = await r.json();

        // API responds with `masters` when no master filter is provided and `slots` when a master is specified.
        const masterList = Array.isArray(data.masters) ? data.masters : [];
        let slots = [];
        if (normalizedMasterId) {
          if (Array.isArray(data.slots) && data.slots.length) {
            slots = data.slots;
          } else {
            const match = masterList.find((entry) => String(entry.id) === normalizedMasterId);
            if (match && Array.isArray(match.slots)) {
              slots = match.slots;
            }
          }
        }
        if (!normalizedMasterId) {
          const preferred = masterList.find((entry) => Array.isArray(entry.slots) && entry.slots.length);
          const fallback = preferred || masterList[0];
          if (fallback && Array.isArray(fallback.slots)) {
            slots = fallback.slots;
          }
        }
        if (!slots.length && Array.isArray(data.slots)) {
          slots = data.slots;
        }

        const set = new Set(); const map = new Map();
        slots.forEach(iso=>{
          const d=parseISO(iso); if(!d) return;
          const key=`${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
          set.add(key); if(!map.has(key)) map.set(key, iso);
        });
        return {set, map, raw:data};
      }

      async function ensureRangeLoaded(startDate, daysCount){
        const masterValue = getActiveMasterValue();
        if (masterValue === null || masterValue === undefined){
          return;
        }
        const tasks=[];
        for(let i=0;i<daysCount;i++){
          const d=new Date(startDate); d.setDate(d.getDate()+i);
          const ds=ymd(d);
          if(!availabilityCache.has(ds)){
            tasks.push((async()=>{
              availabilityCache.set(ds, {loading:true});
              const res=await fetchAvailability(ds, masterValue);
              availabilityCache.set(ds,{set:res.set, iso:res.map});
            })());
          }
        }
        if (tasks.length) await Promise.allSettled(tasks);
      }

      function buildTimeRows(extraSets){
        const out=[];
        for(let h=START_HOUR;h<=END_HOUR;h++){
          for(let m=0;m<60;m+=STEP_MIN){
            out.push(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`);
          }
        }
        (extraSets||[]).forEach(s=>s && s.forEach(t=>{ if(!out.includes(t)) out.push(t); }));
        return out.sort();
      }

      function applySelection(day, iso, locale){
        if (!iso || !day) return;
        const normalizedMaster = normalizeMasterValue(elMaster ? elMaster.value : current.masterId);
        if (normalizedMaster !== null && normalizedMaster !== undefined){
          current.masterId = normalizedMaster;
        }
        current.slot = iso;
        const masterOption = elMaster && elMaster.selectedOptions && elMaster.selectedOptions.length ? elMaster.selectedOptions[0] : null;
        const masterText = masterOption ? masterOption.text : '';
        const timeText = fmtHM(new Date(iso));
        const dateText = day.toLocaleDateString(locale);
        const summaryVars = { master: masterText, time: timeText, date: dateText };
        summaryState = { key: 'services.modal.summarySelected', vars: summaryVars };
        setTextKey(elSummary, 'services.modal.summarySelected', summaryVars, `Master: ${masterText}. Time: ${timeText}, ${dateText}.`);
        btnSubmit.disabled = false;
      }

      function resetSelection(){
        current.slot = null;
        summaryState = { key: 'services.modal.summaryPlaceholder', vars: null };
        setTextKey(elSummary, 'services.modal.summaryPlaceholder');
        btnSubmit.disabled = true;
      }

      function selectSlot(day, iso, locale){
        if (!iso || !day) return;
        scheduleState.selectedDate = ymd(day);
        applySelection(day, iso, locale);
        renderDesktopSchedule(locale);
        renderMobileSchedule(locale);
      }

      function syncMasterHint(){
        if (!elMasterHint) return;
        const masters = Array.isArray(current && current.mastersData) ? current.mastersData : [];
        if (!masters.length){
          showMasterHint('services.modal.masterHintUnavailable', { service: current.serviceName || '' }, 'No masters are available for this service yet.');
          return;
        }
        const masterKey = getSelectedMasterKey();
        if (!masterKey){
          showMasterHint('services.modal.masterHintSelect', { service: current.serviceName || '' }, 'Pick a master to see who is available for this service.');
          return;
        }
        const match = masters.find((entry)=>String(entry.id) === masterKey);
        const masterName = match && match.name
          ? match.name
          : translate('services.modal.masterFallbackName', null, 'selected master');
        showMasterHint('services.modal.masterHintActive', { master: masterName }, `Showing availability for ${masterName}.`);
      }

      async function loadMastersAndRender(){
        elError.style.display='none';
        resetSelection();
        try{
          if (elMaster){
            elMaster.innerHTML='';
          }
          hideMasterHint();
          const first = await fetchAvailability(ymd(baseStart), null);
          const masters = (first.raw && first.raw.masters) || [];
          current.mastersData = masters;

          if(masters.length===0){
            const opt=document.createElement('option');
            opt.value='';
            opt.textContent = translate('services.modal.noMasters', null, 'No masters available');
            elMaster.appendChild(opt);
            showMasterHint('services.modal.masterHintUnavailable', { service: current.serviceName || '' }, 'No masters are available for this service yet.');
            olGrid.innerHTML=`<div class="p-4 text-sm text-center">${translate('services.modal.noAvailability', null, 'No availability')}</div>`;
            if (mobileTimeList) mobileTimeList.innerHTML='';
            if (mobileEmpty){
              mobileEmpty.style.display='block';
              setTextKey(mobileEmpty, 'services.modal.noAvailability', null, 'No availability yet.');
            }
            if (mobileDateInput){
              mobileDateInput.value='';
              mobileDateInput.disabled=true;
            }
            btnSubmit.disabled = true;
            return;
          }
          const requireManualSelection = masters.length > 1;
          if (requireManualSelection){
            const placeholder=document.createElement('option');
            placeholder.value='';
            placeholder.textContent = translate('services.modal.masterPlaceholder', null, 'Select a master');
            placeholder.dataset.placeholder='true';
            elMaster.appendChild(placeholder);
          }
          masters.forEach(m=>{
            const opt=document.createElement('option');
            opt.value=m.id;
            opt.textContent=m.name;
            elMaster.appendChild(opt);
          });
          if (requireManualSelection){
            elMaster.value='';
            current.masterId=null;
            syncMasterHint();
          }else{
            const withSlots=masters.find(m=>(m.slots||[]).length);
            const defaultMasterId = withSlots ? withSlots.id : masters[0].id;
            elMaster.value=String(defaultMasterId);
            current.masterId=normalizeMasterValue(defaultMasterId);
            syncMasterHint();
          }

          availabilityCache.clear();
          await renderWindow();
        }catch(err){
          const fallback = err && err.message;
          const defaultMsg = translate('services.modal.errorLoad');
          elError.style.display='block';
          showMasterHint('services.modal.masterHintError', null, 'Unable to load masters. Please try again.');
          if(fallback && fallback !== defaultMsg){
            clearTextKey(elError);
            elError.textContent=fallback;
          }else{
            setTextKey(elError, 'services.modal.errorLoad');
          }
        }
      }

      async function renderWindow(){
        const locale = getLocale();
        const masterKey = getSelectedMasterKey();

        if (!masterKey){
          scheduleState = {
            days: [],
            dayData: [],
            timeRows: [],
            locale,
            selectedDate: null,
            guardMessage: Object.assign({}, MASTER_REQUIRED_GUARD),
          };
          if (mobileDateInput){
            mobileDateInput.value = '';
            mobileDateInput.disabled = true;
            mobileDateInput.min = '';
            mobileDateInput.max = '';
          }
          renderDesktopSchedule(locale);
          renderMobileSchedule(locale);
          return;
        }

        scheduleState.guardMessage = null;
        await ensureRangeLoaded(baseStart, WINDOW_DAYS);

        const days = Array.from({length:WINDOW_DAYS}, (_,i)=>{ const d=new Date(baseStart); d.setDate(d.getDate()+i); return d;});
        const dayStrs=days.map(ymd);
        const dayData = dayStrs.map(ds => availabilityCache.get(ds));
        const timeRows = buildTimeRows(dayData.map((x)=> (x ? x.set : null)));

        scheduleState.days = days;
        scheduleState.dayData = dayData;
        scheduleState.timeRows = timeRows;
        scheduleState.locale = locale;

        const firstDate = days[0] ? ymd(days[0]) : null;
        const lastDate = days[days.length-1] ? ymd(days[days.length-1]) : null;

        if (mobileDateInput){
          mobileDateInput.disabled = !days.length;
          mobileDateInput.min = firstDate || '';
          mobileDateInput.max = lastDate || '';
        }

        let slotStillValid = false;
        if (current.slot){
          for (const data of dayData){
            if (data && data.iso){
              for (const value of data.iso.values()){
                if (value === current.slot){
                  slotStillValid = true;
                  break;
                }
              }
            }
            if (slotStillValid) break;
          }
        }
        if (!slotStillValid){
          resetSelection();
        }

        if (!scheduleState.selectedDate || (firstDate && scheduleState.selectedDate < firstDate) || (lastDate && scheduleState.selectedDate > lastDate)){
          scheduleState.selectedDate = null;
        }

        if (!scheduleState.selectedDate){
          const firstAvailable = dayData.findIndex(data => data && data.set && data.set.size);
          if (firstAvailable !== -1){
            scheduleState.selectedDate = ymd(days[firstAvailable]);
          } else if (firstDate){
            scheduleState.selectedDate = firstDate;
          }
        }

        if (mobileDateInput && scheduleState.selectedDate){
          mobileDateInput.value = scheduleState.selectedDate;
        }

        renderDesktopSchedule(locale);
        renderMobileSchedule(locale);
      }

      function resolveGuardMessage(record){
        if (!record) return null;
        const key = record.key || null;
        const fallback = record.fallback || '';
        const vars = record.vars || null;
        if (key){
          return translate(key, vars, fallback);
        }
        return fallback;
      }

      function renderDesktopSchedule(locale = scheduleState.locale || getLocale()){
        if (!olGrid) return;
        const guardText = resolveGuardMessage(scheduleState.guardMessage);
        if (guardText){
          olGrid.innerHTML = `<div class="p-4 text-sm text-center">${guardText}</div>`;
          if (olRange) olRange.textContent = '—';
          btnSubmit.disabled = true;
          return;
        }
        const days = scheduleState.days;
        const dayData = scheduleState.dayData;
        const timeRows = scheduleState.timeRows;

        if (!days.length){
          olGrid.innerHTML = '';
          if (olRange) olRange.textContent = '—';
          btnSubmit.disabled = true;
          return;
        }

        const from = days[0].toLocaleDateString(locale, {month:'short', day:'numeric'});
        const to   = days[days.length-1].toLocaleDateString(locale, {month:'short', day:'numeric'});
        if (olRange) olRange.textContent = `${from} – ${to}`;
        olGrid.style.setProperty('--days', String(WINDOW_DAYS));
        olGrid.innerHTML='';

        const headTime = document.createElement('div');
        headTime.className='outlook__cell outlook__head time';
        olGrid.appendChild(headTime);

        const todayStr = (new Date()).toDateString();
        const selectedDateStr = scheduleState.selectedDate;

        days.forEach(d=>{
          const header=document.createElement('div');
          header.className='outlook__cell outlook__head';
          if (todayStr === d.toDateString()) header.classList.add('day--today');
          if (selectedDateStr && selectedDateStr === ymd(d)) header.classList.add('day--selected');
          header.innerHTML = `<div class="day-head">
            <div class="day-title">${d.toLocaleDateString(locale, {weekday:'long'})}</div>
            <div class="day-sub">${d.toLocaleDateString(locale, {month:'short', day:'numeric'})}</div>
          </div>`;
          olGrid.appendChild(header);
        });

        timeRows.forEach(t=>{
          const [hh,mm]=t.split(':').map(n=>parseInt(n,10));
          const fake=new Date(); fake.setHours(hh,mm,0,0);
          const tcell=document.createElement('div'); tcell.className='outlook__cell time'; tcell.textContent=fmtHM(fake);
          olGrid.appendChild(tcell);

          days.forEach((d,idx)=>{
            const cell=document.createElement('div');
            cell.className='outlook__cell';
            const data = dayData[idx];
            const setRef = data && data.set ? data.set : null;
            const isFree = Boolean(setRef && setRef.has(t));
            const chip=document.createElement('button');
            chip.type='button';
            const displayLabel = fmtHM(fake);
            chip.textContent=displayLabel;
            const isoMap = data && data.iso ? data.iso : null;
            const iso = isFree && isoMap ? isoMap.get(t) : null;
            const masterKey = getSelectedMasterKey();
            const reservedByCart = isFree && iso ? slotIsInCart(masterKey, iso) : false;

            if (isFree && !reservedByCart){
              chip.className='slot-chip slot-free';
              chip.disabled = false;
              if (iso === current.slot){
                chip.classList.add('slot-selected');
              }
              chip.addEventListener('click', ()=>{
                selectSlot(d, iso, locale);
              });
            }else{
              chip.className='slot-chip slot-busy';
              chip.disabled = true;
              if (reservedByCart){
                chip.classList.add('slot-cart');
                const reason = translate('services.modal.slotInCart', null, 'Already in your cart');
                chip.dataset.slotState = 'cart';
                chip.setAttribute('aria-label', `${displayLabel} — ${reason}`);
                chip.setAttribute('title', reason);
              }
            }
            cell.appendChild(chip);
            olGrid.appendChild(cell);
          });
        });

        if (olWrap){
          const selected = olGrid.querySelector('.slot-selected');
          if (selected){
            selected.scrollIntoView({ block:'nearest', inline:'center' });
          }else{
            const todayIdx = days.findIndex(x=>x.toDateString()===todayStr);
            if (todayIdx>0){
              const colWidth = 160;
              olWrap.scrollLeft = Math.max(todayIdx * colWidth - colWidth, 0);
            } else {
              olWrap.scrollLeft = 0;
            }
          }
        }
      }

      function renderMobileSchedule(locale = scheduleState.locale || getLocale()){
        if (!mobileScheduleContainer || !mobileTimeList) return;
        const days = scheduleState.days;
        const dayData = scheduleState.dayData;
        const guardRecord = scheduleState.guardMessage;
        const guardText = resolveGuardMessage(guardRecord);

        mobileTimeList.innerHTML = '';

        if (guardText){
          if (mobileEmpty){
            mobileEmpty.style.display = 'block';
            if (guardRecord && guardRecord.key){
              setTextKey(mobileEmpty, guardRecord.key, guardRecord.vars || null, guardRecord.fallback || guardText);
            }else{
              clearTextKey(mobileEmpty);
              mobileEmpty.textContent = guardText;
            }
          }
          btnSubmit.disabled = true;
          if (mobileDateInput){
            mobileDateInput.value = '';
            mobileDateInput.disabled = true;
            mobileDateInput.min = '';
            mobileDateInput.max = '';
          }
          return;
        }

        if (!days.length){
          if (mobileEmpty){
            mobileEmpty.style.display = 'block';
            setTextKey(mobileEmpty, 'services.modal.noAvailability', null, 'No availability yet.');
          }
          return;
        }

        if (mobileEmpty){
          mobileEmpty.style.display = 'none';
        }

        const selectedDateStr = scheduleState.selectedDate;
        const selectedDayIndex = days.findIndex(d => ymd(d) === selectedDateStr);
        const fallbackIndex = days.findIndex((_, idx) => dayData[idx] && dayData[idx].set && dayData[idx].set.size);
        const useIndex = selectedDayIndex !== -1 ? selectedDayIndex : (fallbackIndex !== -1 ? fallbackIndex : 0);
        const day = days[useIndex];
        const dayKey = day ? ymd(day) : null;
        if (dayKey && scheduleState.selectedDate !== dayKey){
          scheduleState.selectedDate = dayKey;
          if (mobileDateInput) mobileDateInput.value = dayKey;
        }

        if (mobileDateInput && scheduleState.selectedDate){
          mobileDateInput.value = scheduleState.selectedDate;
        }

        const data = day ? dayData[useIndex] : null;
        if (!data || !data.set || !data.set.size){
          if (mobileEmpty){
            mobileEmpty.style.display = 'block';
            setTextKey(mobileEmpty, 'services.modal.noAvailabilityDay', null, 'No available times on this date.');
          }
          btnSubmit.disabled = true;
          return;
        }

        if (mobileEmpty){
          mobileEmpty.style.display = 'none';
        }

        const times = Array.from(data.set).sort();
        const masterKey = getSelectedMasterKey();
        times.forEach(timeKey => {
          const iso = data.iso.get(timeKey);
          if (!iso) return;
          const btn=document.createElement('button');
          btn.type='button';
          btn.className='book-mobile__time';
          const displayTime = fmtHM(new Date(iso));
          const reserved = slotIsInCart(masterKey, iso);
          if (reserved){
            btn.classList.add('is-in-cart');
            const badge = translate('services.modal.inCartShort', null, 'In cart');
            const reason = translate('services.modal.slotInCart', null, 'Already in your cart');
            btn.textContent = `${displayTime} · ${badge}`;
            btn.disabled = true;
            btn.dataset.slotState = 'cart';
            btn.setAttribute('aria-label', `${displayTime} — ${reason}`);
            btn.setAttribute('title', reason);
          }else{
            btn.textContent = displayTime;
            if (iso === current.slot){
              btn.classList.add('is-selected');
            }
            btn.addEventListener('click', ()=>{
              selectSlot(day, iso, locale);
            });
          }
          mobileTimeList.appendChild(btn);
        });

        if (!times.length){
          if (mobileEmpty){
            mobileEmpty.style.display = 'block';
            setTextKey(mobileEmpty, 'services.modal.noAvailabilityDay', null, 'No available times on this date.');
          }
          btnSubmit.disabled = true;
        } else if (!current.slot){
          btnSubmit.disabled = true;
        }
      }

      if (mobileDateInput){
        mobileDateInput.addEventListener('change', ()=>{
          const value = mobileDateInput.value;
          scheduleState.selectedDate = value || null;
          resetSelection();
          renderDesktopSchedule(scheduleState.locale || getLocale());
          renderMobileSchedule(scheduleState.locale || getLocale());
        });
      }

      async function shiftWindow(deltaDays){
        baseStart = new Date(baseStart); baseStart.setDate(baseStart.getDate() + deltaDays);
        scheduleState.selectedDate = null;
        resetSelection();
        await renderWindow();
      }
      bind(olPrev,'click', ()=>shiftWindow(-WINDOW_DAYS));
      bind(olNext,'click', ()=>shiftWindow(WINDOW_DAYS));
      bind(olToday,'click', async ()=>{ baseStart = new Date(); baseStart.setHours(0,0,0,0); await renderWindow(); });

      bind(elMaster,'change', async ()=>{
        current.masterId = normalizeMasterValue(elMaster.value);
        current.slot = null; btnSubmit.disabled = true;
        summaryState = { key: 'services.modal.summaryPlaceholder', vars: null };
        setTextKey(elSummary, 'services.modal.summaryPlaceholder');
        syncMasterHint();
        availabilityCache.clear();
        scheduleState.selectedDate = null;
        scheduleState.days = [];
        scheduleState.dayData = [];
        scheduleState.timeRows = [];
        scheduleState.guardMessage = null;
        await renderWindow();
      });

      // ===== add to cart =====
      async function addToCart(){
        if(!current.serviceId || current.masterId === null || current.masterId === undefined || !current.slot) return;
        btnSubmit.disabled=true; elError.style.display='none'; elSuccess.style.display='none';
        clearTextKey(elError); clearTextKey(elSuccess);
        try{
          const resp=await fetch(apiCartAdd,{
            method:'POST',
            headers:{'Content-Type':'application/json','X-CSRFToken':getCookie('csrftoken')},
            credentials:'same-origin',
            body:JSON.stringify({ service:current.serviceId, master:current.masterId, start_time:current.slot })
          });
          const data=await resp.json().catch(()=>({}));
          if(!resp.ok){
            const msg=(data&&(data.error||data.detail))?(data.error||data.detail):translate('services.modal.errorAdd');
            throw new Error(msg);
          }
          setTextKey(elSuccess, 'services.modal.success');
          elSuccess.style.display='block';
          await refreshCart(true);
          setTimeout(()=>{ closeModal(); }, 600);
        }catch(err){
          const fallback = err && err.message;
          const defaultMsg = translate('services.modal.errorAdd');
          elError.style.display='block';
          if(fallback && fallback !== defaultMsg){
            clearTextKey(elError);
            elError.textContent = fallback;
          }else{
            setTextKey(elError, 'services.modal.errorAdd');
          }
        }finally{
          btnSubmit.disabled=false;
        }
      }

      // ===== wire up =====
      bind(btnClose,'click',closeModal);
      bind(btnCancel,'click',closeModal);
      bind(modal,'click',(e)=>{ if(e.target===modal) closeModal(); });
      bind(btnSubmit,'click',addToCart);
      if(detailClose){ detailClose.addEventListener('click', closeServiceDetail); }
      if(detailDismiss){ detailDismiss.addEventListener('click', closeServiceDetail); }
      if(detailModal){ detailModal.addEventListener('click',(event)=>{ if(event.target===detailModal) closeServiceDetail(); }); }
      if(detailBook){
        detailBook.addEventListener('click', ()=>{
          if(!activeServiceDetail || !activeServiceDetail.payload) return;
          const ctx = activeServiceDetail;
          closeServiceDetail();
          window.setTimeout(()=>{
            openModal(
              ctx.payload.id,
              ctx.payload.translated_name || ctx.payload.name || translate('common.service', null, 'Service'),
              ctx.trigger || detailBook
            );
          }, 150);
        });
      }

      if(cartBtn){
        cartBtn.addEventListener('click', openCartModal);
      }
      if(floatingCartBtn){ floatingCartBtn.addEventListener('click', openCartModal); }
      if(cartClose){ cartClose.addEventListener('click', closeCartModal); }
      if(cartModal){ cartModal.addEventListener('click',(e)=>{ if(e.target===cartModal) closeCartModal(); }); }
      if(cartItems){
        cartItems.addEventListener('click',(e)=>{
          const btn=e.target.closest('.cart-remove');
          if(btn){
            const id=btn.dataset.removeId;
            btn.disabled=true;
            removeCartItem(id).finally(()=>{ btn.disabled=false; });
          }
        });
      }
      if (paymentTitle) paymentTitle.textContent = PAYMENT_COPY.title;
      if (paymentSummary) paymentSummary.textContent = PAYMENT_COPY.summary('CA$0.00');
      if (paymentSummaryAmount) paymentSummaryAmount.textContent = 'CA$0.00';
      if (paymentSummaryTime) paymentSummaryTime.textContent = '—';
      if (paymentSummaryItems) {
        paymentSummaryItems.innerHTML = '<div class="payment-panel__meta">Service details will appear here once confirmed.</div>';
      }

      if(paymentOptionGroup){
        paymentOptionGroup.addEventListener('change',(event)=>{
          const target = event.target;
          if (!(target instanceof HTMLInputElement)) return;
          const value = Number(target.value);
          const result = handlePrepaymentSelection(value);
          if (result && typeof result.catch === 'function'){
            result.catch(()=>{});
          }
        });
      }

      if(cartCheckout){ cartCheckout.addEventListener('click', checkoutCart); }
      if(paymentClose){ paymentClose.addEventListener('click', closePaymentModal); }
      if(paymentModal){ paymentModal.addEventListener('click',(e)=>{ if(e.target===paymentModal) closePaymentModal(); }); }
      if(paymentConfirm){ paymentConfirm.addEventListener('click', confirmPayment); }

      const paymentInputs = [
        inputName,
        inputEmail,
        inputAddress1,
        inputAddress2,
        inputCity,
        inputState,
        inputPostal,
        inputCountry,
      ].filter(Boolean);
      paymentInputs.forEach((input) => {
        const handler = () => {
          if (input === inputPostal) {
            input.value = normalizePostal(input.value);
          }
          checkPaymentForm();
        };
        input.addEventListener('input', handler);
        input.addEventListener('blur', handler);
      });

      if (paymentTitle) paymentTitle.textContent = PAYMENT_COPY.title;
      if (paymentConfirm) paymentConfirm.textContent = 'Pay now';
      if (paymentCardLabel) paymentCardLabel.textContent = 'Card details';
      if (paymentSummary) paymentSummary.textContent = PAYMENT_COPY.summary('$0');

      // UX: Shift+wheel for horizontal scroll
      if (olWrap){
        olWrap.addEventListener('wheel', (e)=>{
          if (e.shiftKey && Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
            e.preventDefault(); olWrap.scrollLeft += e.deltaY;
          }
        }, { passive:false });
      }

      if(isAuth){
        refreshCart(true);
      } else {
        if(cartCount) cartCount.textContent='0';
        if(floatingCartCount) floatingCartCount.textContent='0';
        if(floatingCartBtn){
          floatingCartBtn.classList.remove('floating-cart--visible');
          floatingCartBtn.setAttribute('aria-hidden','true');
          floatingCartBtn.tabIndex = -1;
        }
      }

      /* ===== Live search ===== */
      const searchForm = document.querySelector('form.filters');
      const qInput = document.querySelector('input[name="q"]');
      const catSel = document.querySelector('select[name="cat"]');
      const resetLink = document.querySelector('[data-reset-link]');
      const liveTitle = document.getElementById('liveTitle');
      const liveGrid  = document.getElementById('liveGrid');
      const serverContent = serverContentNode;
      (() => {
        const ensureLiveGrid = () => liveGrid || document.getElementById('liveGrid');
        document.addEventListener('live:render', () => {
          attachServiceCardBindings(ensureLiveGrid());
        });
        const grid = ensureLiveGrid();
        if (grid && 'MutationObserver' in window) {
          const mo = new MutationObserver(() => {
            const current = ensureLiveGrid();
            if (!current) return;
            requestAnimationFrame(() => attachServiceCardBindings(current));
          });
          mo.observe(grid, { childList: true, subtree: true });
        }
      })();

      const SEARCH_DELAY = 250;
      let searchTimer = null;
      let aborter = null;

      function escapeHtml(s){ return (s||'').replace(/[&<>"']/g, m=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[m])); }
      function truncateWords(text, limit=10){
        if (text == null) return '';
        const normalized = String(text).trim();
        if (!normalized) return '';
        const words = normalized.split(/\s+/);
        if (words.length <= limit) return normalized;
        return words.slice(0, limit).join(' ') + '...';
      }
      function showLive(){ if(liveTitle) liveTitle.style.display='block'; if(liveGrid) liveGrid.style.display='grid'; if(serverContent) serverContent.style.display='none'; }
      function hideLive(){ if(liveTitle) liveTitle.style.display='none'; if(liveGrid) liveGrid.style.display='none'; if(serverContent) serverContent.style.display='block'; }
      function skeleton(n=8){
        return Array.from({length:n}).map(()=>`
          <article class="service-card">
            <div class="service-card__img service-card__img--empty skeleton" aria-hidden="true"></div>
            <div class="service-card__body">
              <div class="skeleton" style="height:20px;width:70%;border-radius:.75rem;"></div>
              <div class="skeleton" style="height:14px;width:90%;border-radius:.75rem;margin-top:.5rem;"></div>
              <div class="skeleton" style="height:36px;width:140px;border-radius:999px;margin-top:1rem;"></div>
            </div>
          </article>`).join('');
      }
      function toggleReset(q, cat){
        if (!resetLink) return;
        const shouldShow = Boolean(q) || Boolean(cat);
        if (shouldShow){
          resetLink.style.display = '';
          resetLink.removeAttribute('aria-hidden');
        } else {
          resetLink.style.display = 'none';
          resetLink.setAttribute('aria-hidden', 'true');
        }
      }
      function updateLocation(q, cat){
        if (!window.history || typeof window.history.replaceState !== 'function') return;
        const nextUrl = new URL(window.location.href);
        if (q) nextUrl.searchParams.set('q', q); else nextUrl.searchParams.delete('q');
        if (cat) nextUrl.searchParams.set('cat', cat); else nextUrl.searchParams.delete('cat');
        window.history.replaceState(null, document.title, nextUrl.toString());
      }
      function abortActiveRequest(){
        if (aborter){
          aborter.abort();
          aborter = null;
        }
      }
      function cardHTML(s){
        const hasDisc = Number.isFinite(+s.discount_percent) && +s.discount_percent > 0;
        const rawName = s.name || '';
        const lang = getCurrentLang();
        const translatedName = isEnglish(lang)
          ? (translateServiceNameText(rawName) || rawName || translate('common.service', null, 'Service'))
          : (s.translated_name || translateServiceNameText(rawName) || rawName || translate('common.service', null, 'Service'));
        const fallbackImgLabel = translate('services.cards.noImage', null, 'Preview coming soon');
        const imageAlt = s.image_alt || rawName || translate('services.cards.imageAltFallback', null, 'Service preview');
        const imageClasses = ['service-card__img'];
        if (!s.image) imageClasses.push('service-card__img--empty');
        const imageInner = s.image
          ? `<img src=\"${escapeHtml(s.image)}\" alt=\"${escapeHtml(imageAlt)}\" loading=\"lazy\">`
          : `<span>${escapeHtml(fallbackImgLabel)}</span>`;
        const tags = [];
        const categoryLabel = isEnglish(lang)
          ? (s.category || '')
          : (s.translated_category || s.category || '');
        if (s.category) {
          tags.push(`<span class=\"service-card__tag\" data-category-id=\"${escapeHtml(s.category_id || '')}\" data-category-name-original=\"${escapeHtml(s.category)}\">${escapeHtml(categoryLabel)}</span>`);
        }
        if (hasDisc) {
          tags.push(`<span class=\"service-card__tag service-card__tag--accent\">${translate('services.cards.tagPopular', null, 'Popular')}</span>`);
        }
        const tagsBlock = tags.length ? `<div class=\"service-card__tags\">${tags.join('')}</div>` : '';
        const priceBlock = hasDisc
          ? `<span class=\"old\">$${escapeHtml(s.base_price)}</span><strong>$${escapeHtml(s.price)}</strong><span class=\"badge\">-${escapeHtml(String(s.discount_percent))}%</span>`
          : `<strong>$${escapeHtml(s.price || s.base_price)}</strong>`;
        const descSource = isEnglish(lang) ? (s.description || '') : (s.translated_description || s.description || '');
        const descText = truncateWords(descSource, 16);
        const desc = descText ? `<p class=\"service-card__desc\">${escapeHtml(descText)}</p>` : '';
        const durationLabel = escapeHtml(formatMinutes(s.duration_min || 0));
        const ariaLabel = translate('services.detail.openLabel', { name: rawName }, `View details for ${rawName}`);
        const payload = {
          id: String(s.id || ''),
          name: rawName,
          translated_name: s.translated_name || '',
          translated_description: s.translated_description || '',
          translated_category: s.translated_category || '',
          category: s.category || '',
          category_id: s.category_id || '',
          description: (s.description || '').trim(),
          duration_min: Number(s.duration_min || 0),
          extra_time_min: Number(s.extra_time_min || 0),
          base_price: s.base_price || s.price || '',
          price: s.price || s.base_price || '',
          discount_percent: (s.discount_percent === undefined || s.discount_percent === null) ? null : s.discount_percent,
          image: s.image || '',
          image_alt: imageAlt || '',
          forms: Array.isArray(s.forms) ? s.forms.map((form) => ({
            id: form.id || '',
            name: form.name || '',
            slug: form.slug || '',
          })) : [],
        };
        const payloadScript = `<script type=\"application/json\" class=\"service-card__payload\">${serializeServicePayload(payload)}<\/script>`;
        return `
          <article class=\"service-card\" data-service-card role=\"button\" tabindex=\"0\" aria-label=\"${escapeHtml(ariaLabel)}\" data-i18n-attr=\"aria-label:services.detail.openLabel\" data-i18n-vars='${escapeHtml(JSON.stringify({ name: rawName }))}'>
            <div class=\"${imageClasses.join(' ')}\"${s.image ? '' : ' aria-hidden=\"true\"'}>
              ${imageInner}
              ${tagsBlock}
            </div>
            <div class=\"service-card__body\">
              <div class=\"service-card__header\">
                <h3 data-service-name-original=\"${escapeHtml(rawName)}\">${escapeHtml(translatedName)}</h3>
                <span class=\"service-card__duration\">${durationLabel}</span>
              </div>
              ${desc}
              <div class=\"service-card__actions\">
                <div class=\"service-card__price\">${priceBlock}</div>
                <button type=\"button\" class=\"btn btn--ghost service-card__cta\" data-i18n=\"services.cards.viewDetails\">${translate('services.cards.viewDetails')}</button>
              </div>
            </div>
            ${payloadScript}
          </article>`;
      }
      async function fetchServices(q, cat){
        abortActiveRequest();
        const controller = new AbortController();
        aborter = controller;
        const params = new URLSearchParams();
        if (q)   params.set('q', q);
        if (cat) params.set('cat', cat);
        const lang = getCurrentLang();
        if (!isEnglish(lang)) params.set('lang', lang);
        const queryString = params.toString();
        const url = queryString ? `/accounts/api/services/search/?${queryString}` : '/accounts/api/services/search/';
        try{
          const r = await fetch(url, { signal: controller.signal, credentials: 'same-origin' });
          if (!r.ok) throw new Error(translate('services.search.loadFailed'));
          return await r.json();
        }finally{
          if (aborter === controller) {
            aborter = null;
          }
        }
      }
      async function executeSearch({ q, cat } = {}){
        searchTimer = null;
        if (!q && !cat){
          abortActiveRequest();
          hideLive();
          return;
        }
        showLive();
        if (liveGrid) liveGrid.innerHTML = skeleton();
        try{
          const data = await fetchServices(q, cat);
          const items = (data && data.results) || [];
          if (items.length === 0){
            if (liveGrid) liveGrid.innerHTML = `<div class="stub" data-i18n="services.search.noResults">${translate('services.search.noResults')}</div>`;
            queueRefresh();
            return;
          }
          if (liveGrid) {
            liveGrid.innerHTML = items.map(cardHTML).join('');
            if (typeof window.CustomEvent === 'function') {
              document.dispatchEvent(new CustomEvent('live:render'));
            } else if (document.createEvent) {
              const evt = document.createEvent('Event');
              evt.initEvent('live:render', false, false);
              document.dispatchEvent(evt);
            }
            attachServiceCardBindings(liveGrid);
          }
          if (!isEnglish(getCurrentLang())) {
            refreshTranslations(getCurrentLang());
          }
          queueRefresh();
        }catch(e){
          if (e && e.name === 'AbortError') return;
          if (liveGrid) liveGrid.innerHTML = `<div class="stub" data-i18n="services.search.error">${translate('services.search.error')}</div>`;
          queueRefresh();
        }
      }
      function scheduleSearch(options = {}){
        const { immediate = false, updateUrl = true } = options;
        const state = {
          q: readFieldValue(qInput).trim(),
          cat: catSel && typeof catSel.value === 'string' ? catSel.value : '',
        };
        toggleReset(state.q, state.cat);
        if (updateUrl) updateLocation(state.q, state.cat);
        if (searchTimer){
          clearTimeout(searchTimer);
          searchTimer = null;
        }
        const payload = { q: state.q, cat: state.cat };
        if (!payload.q && !payload.cat){
          executeSearch(payload);
          return;
        }
        if (immediate){
          executeSearch(payload);
        }else{
          searchTimer = window.setTimeout(()=>executeSearch(payload), SEARCH_DELAY);
        }
      }

      toggleReset(readFieldValue(qInput).trim(), catSel && typeof catSel.value === 'string' ? catSel.value : '');

      if (qInput) qInput.addEventListener('input', ()=>scheduleSearch());
      if (catSel) catSel.addEventListener('change', ()=>scheduleSearch({ immediate:true }));
      if (searchForm){
        searchForm.addEventListener('submit', (e)=>{
          e.preventDefault();
          scheduleSearch({ immediate:true });
        });
      }
      if (resetLink){
        resetLink.addEventListener('click', (e)=>{
          e.preventDefault();
          if (qInput) qInput.value = '';
          if (catSel) catSel.value = '';
          scheduleSearch({ immediate:true });
          const servicesSection = document.getElementById('services');
          if (servicesSection && typeof servicesSection.scrollIntoView === 'function') {
            servicesSection.scrollIntoView({behavior:'smooth', block:'start'});
          }
        });
      }
      refreshTranslations(getCurrentLang());
      if (I18N && typeof I18N.onChange === 'function') {
        I18N.onChange((lang) => {
          refreshTranslations(lang);
        });
      } else {
        document.addEventListener('malva:lang-change', (event) => {
          const lang = event && event.detail && event.detail.lang;
          refreshTranslations(lang);
        });
      }
      window.DEBUG_checkoutCart = checkoutCart;
    } catch (err) {
      console.error('[services] Failed to initialize booking UI', err);
    }
      };
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMainmenuInteractions, { once: true });
      } else {
        initMainmenuInteractions();
      }
    })();
