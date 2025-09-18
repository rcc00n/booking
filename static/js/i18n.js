(function (window, document) {
  const STORAGE_KEY = 'malva:lang';
  const FALLBACK_LANG = 'en';
  const LANG_DIRECTIONS = {
    ar: 'rtl'
  };
  const LANG_LOCALES = {
    en: 'en-US',
    ru: 'ru-RU',
    uk: 'uk-UA',
    fr: 'fr-FR',
    ar: 'ar',
    hi: 'hi-IN'
  };

  const translations = {
    en: {
      languages: {
        en: 'English',
        ru: 'Russian',
        uk: 'Ukrainian',
        fr: 'French',
        ar: 'Arabic',
        hi: 'Hindi'
      },
      common: {
        brand: 'Malva Booking',
        language: 'Language',
        close: 'Close',
        cancel: 'Cancel',
        save: 'Save',
        saveChanges: 'Save changes',
        signOut: 'Sign out',
        backHome: 'Back to Home',
        clientProfile: 'Client Profile',
        login: 'Login',
        cart: 'Cart',
        checkout: 'Checkout',
        addToCart: 'Add to cart',
        free: 'free',
        busy: 'busy',
        service: 'Service',
        noTime: 'No time'
      },
      services: {
        meta: {
          title: 'Malva Booking — Services'
        },
        hero: {
          title: 'Book your appointment in 2 clicks',
          subtitle: 'Pick a service, a specialist, and a time — we’ll handle the rest.',
          cta: 'Browse services ↓'
        },
        nav: {
          cart: 'Cart',
          clientProfile: 'Client Profile',
          login: 'Login'
        },
        section: {
          title: 'Services'
        },
        filters: {
          searchPlaceholder: 'Search a service…',
          allCategories: 'All categories',
          submit: 'Search',
          reset: 'Reset'
        },
        search: {
          liveTitle: 'Search results',
          resultsTitle: 'Search results',
          noServerResults: 'No results for “{{query}}”.',
          noCategory: 'No services in this category yet.',
          uncategorized: 'Uncategorized',
          emptyCatalogue: 'The catalog will be available soon 👍',
          noResults: 'No services found.',
          error: 'Could not load results. Please try again.',
          loadFailed: 'Failed to load'
        },
        cards: {
          addToCart: 'Add to cart'
        },
        units: {
          minutes: '{{value}} min'
        },
        modal: {
          title: 'Add service:',
          masterLabel: 'Master',
          chooseTime: 'Choose time',
          prev: '← Prev',
          today: 'Today',
          next: 'Next →',
          legendFree: 'free',
          legendBusy: 'busy',
          legendHint: 'Scroll horizontally. Red slots are busy and not clickable.',
          summaryLabel: 'Summary',
          summaryPlaceholder: 'Pick a master and time.',
          summarySelected: 'Master: {{master}}. Time: {{time}}, {{date}}.',
          errorLoad: 'Unable to fetch availability',
          noMasters: 'No masters available',
          noAvailability: 'No availability',
          success: 'Service added to cart.',
          errorAdd: 'Could not add service to cart',
          errorGeneric: 'Add to cart error'
        },
        cart: {
          title: 'Cart',
          empty: 'Your cart is empty.',
          summary: 'Total: {{total}} · {{duration}}',
          checkout: 'Checkout',
          loadFailed: 'Could not load cart',
          removeSuccess: 'Item removed from cart.',
          removeFailed: 'Failed to remove item',
          checkoutFailed: 'Checkout failed',
          checkoutSuccess: 'Appointment created! Redirecting…',
          remove: 'Remove item'
        },
        dynamic: {
          names: {
            'service-one': 'Service One',
            'service-two': 'Service Two',
            'consultation': 'Consultation'
          }
        },
        footer: {
          copy: '© 2025 Malva Booking'
        }
      },
      dashboard: {
        meta: {
          title: 'Client Portal | Malva Booking'
        },
        nav: {
          overview: 'Overview',
          appointments: 'Appointments',
          files: 'Files',
          notifications: 'Notifications',
          profile: 'Profile',
          back: 'Back to Home',
          signOut: 'Sign out'
        },
        greetingNamed: 'Hello, {{name}}!',
        greetingAnon: 'Hello, {{username}}!',
        upcomingTitle: 'Upcoming appointments',
        upcomingEmpty: 'No upcoming appointments.',
        statsTitle: 'Stats',
        chartLabel: 'Appointments',
        recentTitle: 'Recent appointments',
        recentEmpty: 'No completed appointments yet.',
        table: {
          date: 'Date',
          service: 'Service',
          master: 'Master',
          status: 'Status',
          amount: 'Amount'
        },
        myTitle: 'My appointments',
        myEmpty: 'No appointments.',
        book: '+ Book',
        appointment: {
          cancel: 'Cancel',
          reschedule: 'Reschedule',
          completed: 'Completed'
        },
        filesTitle: 'Files',
        notificationsTitle: 'Notifications',
        comingSoon: 'Coming soon.',
        profileTitle: 'Profile',
        form: {
          firstName: 'First name',
          lastName: 'Last name',
          phone: 'Phone',
          email: 'E-mail',
          birthDate: 'Birth date',
          save: 'Save changes'
        },
        reschedule: {
          title: 'Reschedule appointment',
          masterLabel: 'Master',
          chooseTime: 'Choose time',
          hint: 'Scroll horizontally. Red slots are busy.',
          prev: '← Prev',
          today: 'Today',
          next: 'Next →',
          cancel: 'Cancel',
          save: 'Save',
          noMasters: 'No masters available',
          noAvailability: 'No availability',
          success: 'Rescheduled to {{datetime}}',
          failed: 'Reschedule failed',
          loadFailed: 'Failed to load slots',
          errorLoad: 'Unable to fetch availability',
          confirmCancel: 'Cancel this appointment?',
          cancelError: 'Cancel error: {{detail}}'
        }
      }
    },
    ru: {
      languages: {
        en: 'Английский',
        ru: 'Русский',
        uk: 'Украинский',
        fr: 'Французский',
        ar: 'Арабский',
        hi: 'Хинди'
      },
      common: {
        brand: 'Malva Booking',
        language: 'Язык',
        close: 'Закрыть',
        cancel: 'Отмена',
        save: 'Сохранить',
        saveChanges: 'Сохранить изменения',
        signOut: 'Выйти',
        backHome: 'Назад на главную',
        clientProfile: 'Личный кабинет',
        login: 'Войти',
        cart: 'Корзина',
        checkout: 'Оформить',
        addToCart: 'В корзину',
        free: 'свободно',
        busy: 'занято',
        service: 'Услуга',
        noTime: 'Нет времени'
      },
      services: {
        meta: {
          title: 'Malva Booking — Услуги'
        },
        hero: {
          title: 'Запишитесь за 2 клика',
          subtitle: 'Выберите услугу, мастера и время — остальное сделаем мы.',
          cta: 'Смотреть услуги ↓'
        },
        nav: {
          cart: 'Корзина',
          clientProfile: 'Личный кабинет',
          login: 'Войти'
        },
        section: {
          title: 'Услуги'
        },
        filters: {
          searchPlaceholder: 'Найти услугу…',
          allCategories: 'Все категории',
          submit: 'Найти',
          reset: 'Сбросить'
        },
        search: {
          liveTitle: 'Результаты поиска',
          resultsTitle: 'Результаты поиска',
          noServerResults: 'Результатов для «{{query}}» не найдено.',
          noCategory: 'В этой категории пока нет услуг.',
          uncategorized: 'Без категории',
          emptyCatalogue: 'Каталог скоро появится 👍',
          noResults: 'Услуги не найдены.',
          error: 'Не удалось загрузить результаты. Попробуйте снова.',
          loadFailed: 'Не удалось загрузить'
        },
        cards: {
          addToCart: 'В корзину'
        },
        units: {
          minutes: '{{value}} мин'
        },
        modal: {
          title: 'Добавить услугу:',
          masterLabel: 'Мастер',
          chooseTime: 'Выбор времени',
          prev: '← Назад',
          today: 'Сегодня',
          next: 'Далее →',
          legendFree: 'свободно',
          legendBusy: 'занято',
          legendHint: 'Прокручивайте горизонтально. Красные слоты заняты и недоступны.',
          summaryLabel: 'Итого',
          summaryPlaceholder: 'Выберите мастера и время.',
          summarySelected: 'Мастер: {{master}}. Время: {{time}}, {{date}}.',
          errorLoad: 'Не удалось получить доступные слоты',
          noMasters: 'Нет доступных мастеров',
          noAvailability: 'Слоты недоступны',
          success: 'Услуга добавлена в корзину.',
          errorAdd: 'Не удалось добавить услугу в корзину',
          errorGeneric: 'Ошибка добавления в корзину'
        },
        cart: {
          title: 'Корзина',
          empty: 'Ваша корзина пуста.',
          summary: 'Итого: {{total}} · {{duration}}',
          checkout: 'Оформить',
          loadFailed: 'Не удалось загрузить корзину',
          removeSuccess: 'Запись удалена из корзины.',
          removeFailed: 'Не удалось удалить запись',
          checkoutFailed: 'Не удалось оформить запись',
          checkoutSuccess: 'Запись создана! Перенаправляем…',
          remove: 'Удалить'
        },
        dynamic: {
          names: {
            'service-one': 'Услуга 1',
            'service-two': 'Услуга 2',
            'consultation': 'Консультация'
          }
        },
        footer: {
          copy: '© 2025 Malva Booking'
        }
      },
      dashboard: {
        meta: {
          title: 'Личный кабинет | Malva Booking'
        },
        nav: {
          overview: 'Обзор',
          appointments: 'Записи',
          files: 'Файлы',
          notifications: 'Уведомления',
          profile: 'Профиль',
          back: 'Назад на сайт',
          signOut: 'Выйти'
        },
        greetingNamed: 'Привет, {{name}}!',
        greetingAnon: 'Привет, {{username}}!',
        upcomingTitle: 'Ближайшие записи',
        upcomingEmpty: 'Нет запланированных записей.',
        statsTitle: 'Статистика',
        chartLabel: 'Записи',
        recentTitle: 'Последние записи',
        recentEmpty: 'Пока нет завершённых записей.',
        table: {
          date: 'Дата',
          service: 'Услуга',
          master: 'Мастер',
          status: 'Статус',
          amount: 'Сумма'
        },
        myTitle: 'Мои записи',
        myEmpty: 'Записей нет.',
        book: '+ Записаться',
        appointment: {
          cancel: 'Отменить',
          reschedule: 'Перенести',
          completed: 'Завершено'
        },
        filesTitle: 'Файлы',
        notificationsTitle: 'Уведомления',
        comingSoon: 'Скоро появится.',
        profileTitle: 'Профиль',
        form: {
          firstName: 'Имя',
          lastName: 'Фамилия',
          phone: 'Телефон',
          email: 'E-mail',
          birthDate: 'Дата рождения',
          save: 'Сохранить изменения'
        },
        reschedule: {
          title: 'Перенести запись',
          masterLabel: 'Мастер',
          chooseTime: 'Выбор времени',
          hint: 'Прокручивайте горизонтально. Красные слоты заняты.',
          prev: '← Назад',
          today: 'Сегодня',
          next: 'Далее →',
          cancel: 'Отмена',
          save: 'Сохранить',
          noMasters: 'Нет доступных мастеров',
          noAvailability: 'Нет доступных слотов',
          success: 'Перенесено на {{datetime}}',
          failed: 'Не удалось перенести',
          loadFailed: 'Не удалось загрузить слоты',
          errorLoad: 'Не удалось получить доступные слоты',
          confirmCancel: 'Отменить эту запись?',
          cancelError: 'Ошибка отмены: {{detail}}'
        }
      }
    }
  };

  function slugifyKey(str) {
    if (!str) return '';
    return str
      .toString()
      .trim()
      .toLowerCase()
      .normalize('NFD')
      .replace(/[^\p{Letter}\p{Number}]+/gu, '-')
      .replace(/^-+|-+$/g, '');
  }

  function getLocaleFromLang(lang) {
    const code = SUPPORTED_LANGS.includes(lang) ? lang : FALLBACK_LANG;
    return LANG_LOCALES[code] || LANG_LOCALES[FALLBACK_LANG] || code || 'en';
  }

  function getLanguageLabelFor(lang, targetLang) {
    const dict = getDict(targetLang || currentLang || FALLBACK_LANG);
    if (dict && dict.languages && dict.languages[lang]) {
      return dict.languages[lang];
    }
    const fallbackDict = getDict(FALLBACK_LANG);
    if (fallbackDict && fallbackDict.languages && fallbackDict.languages[lang]) {
      return fallbackDict.languages[lang];
    }
    return lang;
  }

  const SUPPORTED_LANGS = Object.keys(translations);
  let currentLang = null;
  const listeners = new Set();

  function getDict(lang) {
    return translations[SUPPORTED_LANGS.includes(lang) ? lang : FALLBACK_LANG];
  }

  function resolve(dict, key) {
    if (!key) return undefined;
    return key.split('.').reduce(function (acc, part) {
      if (acc && Object.prototype.hasOwnProperty.call(acc, part)) {
        return acc[part];
      }
      return undefined;
    }, dict);
  }

  function formatText(template, vars) {
    if (!vars) return template;
    return template.replace(/{{\s*([\w.-]+)\s*}}/g, function (_, name) {
      return Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : '';
    });
  }

  function translate(lang, key, vars) {
    if (!key) return '';
    const dict = getDict(lang);
    let value = resolve(dict, key);
    if (value === undefined) {
      value = resolve(getDict(FALLBACK_LANG), key);
    }
    if (typeof value === 'function') {
      return value(vars || {}, { lang });
    }
    if (typeof value === 'string') {
      return vars ? formatText(value, vars) : value;
    }
    return value !== undefined ? value : key;
  }

  function translateServiceName(name, lang) {
    if (!name) return '';
    const slug = slugifyKey(name);
    if (!slug) return name;
    const target = SUPPORTED_LANGS.includes(lang) ? lang : (lang || currentLang || FALLBACK_LANG);
    const dict = resolve(getDict(target), 'services.dynamic.names') || {};
    if (dict && Object.prototype.hasOwnProperty.call(dict, slug)) {
      return dict[slug];
    }
    const fallbackDict = resolve(getDict(FALLBACK_LANG), 'services.dynamic.names') || {};
    if (fallbackDict && Object.prototype.hasOwnProperty.call(fallbackDict, slug)) {
      return fallbackDict[slug];
    }
    return name;
  }

  function parseVars(el) {
    const raw = el.getAttribute('data-i18n-vars');
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (err) {
      const pairs = raw.split(';');
      const out = {};
      pairs.forEach(function (pair) {
        if (!pair) return;
        const idx = pair.indexOf('=');
        if (idx === -1) return;
        const key = pair.slice(0, idx).trim();
        const value = pair.slice(idx + 1).trim();
        if (key) out[key] = value;
      });
      return out;
    }
  }

  function parseAttrSpec(spec) {
    if (!spec) return [];
    try {
      const parsed = JSON.parse(spec);
      if (parsed && typeof parsed === 'object') {
        return Object.keys(parsed).map(function (attr) {
          return { attr: attr, key: parsed[attr] };
        });
      }
    } catch (err) {
      /* ignore */
    }
    return spec.split(',').map(function (item) {
      const idx = item.indexOf(':');
      if (idx === -1) return null;
      const attr = item.slice(0, idx).trim();
      const key = item.slice(idx + 1).trim();
      if (!attr) return null;
      return { attr: attr, key: key };
    }).filter(Boolean);
  }

  function setElementText(el, text) {
    if (el.hasAttribute('data-i18n-html')) {
      el.innerHTML = text;
    } else {
      el.textContent = text;
    }
  }

  function apply(lang, options) {
    const opts = options || {};
    const targetLang = SUPPORTED_LANGS.includes(lang) ? lang : FALLBACK_LANG;
    if (!opts.skipMeta) {
      document.documentElement.lang = targetLang;
      document.documentElement.dir = LANG_DIRECTIONS[targetLang] || 'ltr';
      document.documentElement.setAttribute('data-lang', targetLang);
      document.documentElement.setAttribute('data-locale', getLocaleFromLang(targetLang));
    }

    const elements = document.querySelectorAll('[data-i18n]');
    elements.forEach(function (el) {
      const key = el.getAttribute('data-i18n');
      if (!key) return;
      const vars = parseVars(el);
      const translation = translate(targetLang, key, vars);
      if (translation !== undefined && translation !== null) {
        setElementText(el, translation);
      }
    });

    const attrElements = document.querySelectorAll('[data-i18n-attr]');
    attrElements.forEach(function (el) {
      const spec = parseAttrSpec(el.getAttribute('data-i18n-attr'));
      if (!spec.length) return;
      spec.forEach(function (item) {
        if (!item || !item.attr) return;
        const value = translate(targetLang, item.key);
        if (value !== undefined && value !== null) {
          el.setAttribute(item.attr, value);
        }
      });
    });

    if (!opts.skipSync) {
      syncSwitchers(targetLang);
    }

    if (!opts.silent) {
      listeners.forEach(function (listener) {
        try { listener(targetLang); } catch (err) { /* noop */ }
      });
      document.dispatchEvent(new CustomEvent('malva:lang-change', { detail: { lang: targetLang } }));
    }
  }

  function syncSwitchers(lang) {
    const target = lang || currentLang || FALLBACK_LANG;
    document.querySelectorAll('[data-lang-switch]').forEach(function (el) {
      if (el.tagName === 'SELECT') {
        Array.from(el.options).forEach(function (opt) {
          opt.textContent = getLanguageLabelFor(opt.value, target);
        });
        if (el.value !== target) {
          el.value = target;
        }
      } else {
        const value = el.getAttribute('data-lang-switch');
        const isActive = value === target;
        el.classList.toggle('is-active', isActive);
        if (el.hasAttribute('aria-pressed')) {
          el.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        }
      }
    });
  }

  function setLanguage(lang, options) {
    const opts = options || {};
    const target = SUPPORTED_LANGS.includes(lang) ? lang : FALLBACK_LANG;
    if (currentLang === target && !opts.force) {
      return;
    }
    currentLang = target;
    apply(currentLang, { skipSync: false, silent: false, skipMeta: false });
    if (!opts.skipSave) {
      try {
        localStorage.setItem(STORAGE_KEY, currentLang);
      } catch (err) {
        /* ignore */
      }
    }
  }

  function refresh(options) {
    if (!currentLang) return;
    const opts = options || {};
    apply(currentLang, {
      skipMeta: true,
      skipSync: opts.skipSync !== undefined ? opts.skipSync : true,
      silent: opts.silent !== undefined ? opts.silent : true
    });
  }

  function bindSwitcher(el) {
    if (el._malvaI18nBound) return;
    el._malvaI18nBound = true;
    if (el.tagName === 'SELECT') {
      if (!el.options.length) {
        SUPPORTED_LANGS.forEach(function (code) {
          const opt = document.createElement('option');
          opt.value = code;
          opt.textContent = getLanguageLabelFor(code, currentLang || FALLBACK_LANG);
          el.appendChild(opt);
        });
      }
      el.addEventListener('change', function (event) {
        setLanguage(event.target.value);
      });
    } else {
      el.setAttribute('role', el.getAttribute('role') || 'button');
      el.setAttribute('aria-pressed', 'false');
      el.addEventListener('click', function (event) {
        event.preventDefault();
        const value = el.getAttribute('data-lang-switch');
        if (value) {
          setLanguage(value);
        }
      });
    }
  }

  function registerSwitchers() {
    document.querySelectorAll('[data-lang-switch]').forEach(bindSwitcher);
    syncSwitchers(currentLang);
  }

  function init() {
    registerSwitchers();
    let initial = FALLBACK_LANG;
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && SUPPORTED_LANGS.includes(stored)) {
        initial = stored;
      } else {
        const navLangs = navigator.languages || [navigator.language || navigator.userLanguage];
        const match = (navLangs || []).map(function (code) {
          return code ? code.split('-')[0] : null;
        }).find(function (code) {
          return code && SUPPORTED_LANGS.includes(code);
        });
        if (match) {
          initial = match;
        }
      }
    } catch (err) {
      /* ignore */
    }
    setLanguage(initial, { skipSave: true, force: true });
  }

  window.MalvaI18n = {
    setLanguage: setLanguage,
    getCurrent: function () { return currentLang || FALLBACK_LANG; },
    t: function (key, vars, lang) {
      const target = lang || currentLang || FALLBACK_LANG;
      return translate(target, key, vars);
    },
    getLocale: function () { return getLocaleFromLang(currentLang || FALLBACK_LANG); },
    translateServiceName: function (name, lang) {
      return translateServiceName(name, lang);
    },
    onChange: function (callback) {
      if (typeof callback !== 'function') return function () {};
      listeners.add(callback);
      if (currentLang) {
        try { callback(currentLang); } catch (err) { /* noop */ }
      }
      return function () {
        listeners.delete(callback);
      };
    },
    refresh: refresh,
    languages: SUPPORTED_LANGS.slice(),
    registerSwitchers: registerSwitchers
  };

  document.addEventListener('DOMContentLoaded', init);
})(window, document);
