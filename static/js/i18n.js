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
  const ATTR_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_.:-]*$/;

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
        header: {
          tagline: 'Beauty & Wellness Studio',
          sendGift: 'Send a gift card',
          listBusiness: 'List your business',
          openMenu: 'Open menu',
          closeMenu: 'Close menu',
          closeMenuText: 'Close menu',
          menuLabel: 'Main menu',
          calendar: 'Open calendar shortcuts',
          notifications: 'Notifications',
          openCart: 'Open cart'
        },
        hero: {
          badge: 'Luxury wellness',
          title: 'Our Services',
          subtitle: 'Book your appointment in 2 clicks',
          description: 'Pick a service, a specialist, and a time — we’ll handle the rest.',
          cta: 'Browse services ↓',
          ctaPrimary: 'Book now',
          ctaSecondary: 'Explore categories',
          stats: {
            clients: {
              value: '3.2K+',
              label: 'Happy clients this month'
            },
            specialists: {
              value: '42',
              label: 'Verified specialists online'
            },
            speed: {
              value: '2 clicks',
              label: 'Average booking time'
            }
          }
        },
        nav: {
          cart: 'Cart',
          clientProfile: 'Client Profile',
          login: 'Login',
          register: 'Create account'
        },
        section: {
          title: 'Services'
        },
        filters: {
          searchLabel: 'Search service',
          categoryLabel: 'Category',
          searchPlaceholder: 'Search a service…',
          allCategories: 'All categories',
          submit: 'Search',
          reset: 'Reset'
        },
        categories: {
          title: 'Popular Services',
          subtitle: 'Discover trending treatments curated by Malva.',
          all: 'All Services'
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
          addToCart: 'Add to cart',
          viewDetails: 'View details',
          tagPopular: 'Popular',
          noImage: 'Preview coming soon',
          imageAltFallback: 'Service preview'
        },
        detail: {
          badgeFeatured: 'Signature',
          imageEmpty: 'Preview coming soon',
          unknownCategory: 'Uncategorized',
          descriptionFallback: 'We will publish the description soon.',
          durationLabel: 'Duration',
          categoryLabel: 'Category',
          priceLabel: 'Investment',
          discountLabel: '{{value}}% off today',
          formsLabel: 'Required forms',
          formsEmpty: 'No forms required before the visit.',
          formsSingular: '{{count}} form to complete before arrival.',
          formsPlural: '{{count}} forms to complete before arrival.',
          highlightsTitle: 'What to expect',
          highlightCare: 'Personal concierge care from our front-desk team.',
          highlightProducts: 'Sterile tools and lab-tested professional formulas.',
          highlightPlan: 'Personalized at-home plan after your visit.',
          ctaPrimary: 'Book this service',
          ctaSecondary: 'Back to catalog',
          metaExtraTime: '+{{value}} min prep time',
          imageAlt: 'Preview for {{name}}',
          openLabel: 'View details for {{name}}'
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
          mobileEmpty: 'No availability yet.',
          mobileDate: 'Date',
          cartPreviewLabel: 'In your cart',
          cartPreviewEmpty: 'Add services to your cart to see them here.',
          cartPreviewUnknownMaster: 'Any master',
          cartPreviewMeta: '{{master}} · {{time}} · {{duration}}',
          cartPreviewTotals: 'Total: {{total}} • {{duration}}',
          cartPreviewFee: '{{fee}} card processing fee (3% + $0.50) included.',
          success: 'Service added to cart.',
          errorAdd: 'Could not add service to cart',
          errorGeneric: 'Add to cart error',
          inCartShort: 'In cart',
          slotInCart: 'Already in your cart'
        },
        cart: {
          title: 'Cart',
          empty: 'Your cart is empty.',
          summary: 'Total: {{total}} · {{duration}}',
          processingFeeNotice: '{{fee}} card processing fee (3% + $0.50) is included in the total.',
          discount: 'Discount',
          checkout: 'Checkout',
          open: 'Open cart',
          loadFailed: 'Could not load cart',
          removeSuccess: 'Item removed from cart.',
          removeFailed: 'Failed to remove item',
          checkoutFailed: 'Checkout failed',
          finalizeFailed: 'Failed to finalize booking.',
          checkoutSuccess: 'Appointment created! Redirecting…',
          freeSuccess: 'Appointment booked. No payment required.',
          remove: 'Remove item'
        },
        payment: {
          amountDueLabel: 'Amount due',
          feeLabel: 'Card processing fee',
          optionLabel: 'Payment option',
          payInFullLabel: 'Pay in full ({{percent}}%)',
          payInFullHint: 'The entire balance will be charged today.',
          payPartialLabel: 'Pay {{percent}}% now',
          payPartialHint: 'Remaining {{remaining}} will be due later.',
          partialNote: 'Remaining balance will be due in person or later.',
          confirmButton: 'Confirm booking'
        },
        userMenu: {
          open: 'Open user menu',
          greeting: 'Welcome back',
          tier: 'Malva Member',
          profile: 'Profile',
          appointments: 'Appointments',
          wallet: 'Wallet',
          favorites: 'Favorites',
          giftCard: 'Send a gift card',
          forms: 'Forms',
          orders: 'Product orders',
          settings: 'Settings',
          language: 'Languages',
          logout: 'Log out',
          download: 'Download the app',
          help: 'Help & support',
          business: 'For businesses'
        },
        dynamic: {
          names: {
            "service-one": 'Service One',
            "service-two": 'Service Two',
            consultation: 'Consultation'
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
          signOut: 'Sign out',
          accountMenu: 'Account menu',
          overviewHint: 'Insights & quick actions',
          appointmentsHint: 'Upcoming & history',
          billing: 'Billing & payments',
          billingHint: 'Wallet & saved details',
          setup: 'Setup',
          formsHint: 'Intake & updates',
          settingsHint: 'Preferences & privacy',
          support: 'Support',
          supportHint: 'Help & resources'
        },
        mobile: {
          portalLabel: 'Client Portal'
        },
        overview: {
          viewAll: 'View all'
        },
        greetingNamed: 'Hello, {{name}}!',
        greetingAnon: 'Hello, {{username}}!',
        upcomingTitle: 'Upcoming appointments',
        upcomingEmpty: 'No upcoming appointments.',
        statsTitle: 'Stats',
        stats: {
          range: 'Last 6 months'
        },
        chartLabel: 'Appointments',
        recentTitle: 'Recent appointments',
        recentEmpty: 'No completed appointments yet.',
        table: {
          date: 'Date',
          service: 'Service',
          master: 'Master',
          status: 'Status',
          payment: 'Payment status',
          receipt: 'Receipt',
          receiptCta: 'View receipt',
          noReceipt: 'Not available yet'
        },
        myTitle: 'My appointments',
        myEmpty: 'No appointments.',
        book: '+ Book',
        appointments: {
          scheduleLabel: 'Schedule'
        },
        appointment: {
          cancel: 'Cancel',
          reschedule: 'Reschedule',
          completed: 'Completed',
          paymentStatusLabel: 'Payment status:',
          pending: 'Pending',
          actionsUnavailable: 'Actions unavailable',
          noItems: 'No services recorded.',
          noMonth: 'No appointments this month.'
        },
        filesTitle: 'Files',
        notificationsTitle: 'Notifications',
        comingSoon: 'Coming soon.',
        profileTitle: 'Profile',
        profile: {
          subtitle: 'Update your personal details to keep bookings seamless.'
        },
        forms: {
          pending: 'Forms outstanding',
          actionNeeded: 'Action needed: we still need your intake form.',
          complete: 'Complete {{count}} form(s) before your next visit.',
          completeCta: 'Complete now',
          upToDate: 'All required forms are on file.',
          review: 'Need to make changes? Update your answers anytime.',
          reviewCta: 'Review forms'
        },
        form: {
          firstName: 'First name',
          lastName: 'Last name',
          phone: 'Phone',
          email: 'E-mail',
          birthDate: 'Birth date',
          save: 'Save changes',
          name: 'Name',
          postalCode: 'Postal code',
          address: 'Address',
          firstNamePlaceholder: 'Jane',
          lastNamePlaceholder: 'Doe',
          postalPlaceholder: 'T2X1A1',
          addressPlaceholder: '123 Main St'
        },
        billing: {
          sectionLabel: 'Wallet',
          title: 'Balance & billing',
          subtitle: 'Store your payment details for lightning-fast checkout.',
          cardTitle: 'Billing details saved to your account',
          cardSubtitle: 'We reuse these fields across invoices and checkout on every device.',
          fields: {
            name: 'Billing name',
            city: 'City',
            state: 'Province / State',
            country: 'Country'
          },
          updated: 'Updated {{date}}',
          notUpdated: 'Not updated yet.',
          syncDevice: 'Sync this device to account',
          clearDevice: 'Clear account copy'
        },
        formsTab: {
          title: 'Forms & questionnaires',
          subtitle: 'We use these forms to tailor every appointment. Update them anytime to keep your preferences fresh.',
          pending: 'Pending',
          submitted: 'Submitted',
          open: 'Open forms'
        },
        settings: {
          accountTitle: 'Account profile (server copy)',
          accountSubtitle: 'These details live securely in your Malva account.',
          howHeard: 'How heard',
          marketingConsent: 'Marketing consent',
          marketingSubscribed: 'Subscribed',
          marketingUnsubscribed: 'Not subscribed',
          syncProfile: 'Sync profile to this device',
          clearProfile: 'Clear device copy',
          languageTitle: 'Language & alerts',
          languageSubtitle: 'Keep every touchpoint consistent by picking a preferred language.',
          languageNote: 'Changes apply instantly and sync across all of your signed-in sessions.'
        },
        device: {
          title: 'Device autofill',
          subtitle: 'Saved form data never leaves this browser. Clear it if you are on a shared computer.',
          empty: 'No autofill data stored on this device yet.',
          clear: 'Clear all device data'
        },
        support: {
          conciergeTitle: 'Concierge support',
          conciergeSubtitle: 'Message our team for scheduling help, account changes, or product guidance.',
          email: 'Email:',
          phone: 'Phone:',
          hours: 'Hours:',
          hoursValue: 'Monday–Friday, 9am–6pm',
          bookAgain: 'Book another visit',
          updateForms: 'Update forms',
          resourcesTitle: 'Resources & downloads',
          resourcesSubtitle: 'Keep Malva close with our app and quick-reference guides.',
          resources: {
            walkthroughs: 'Step-by-step account walkthroughs',
            aftercare: 'Aftercare recommendations from your master',
            receipts: 'Printable receipts and booking confirmations'
          },
          helpCenter: 'Visit help center',
          policiesTitle: 'Policies & privacy',
          policiesSubtitle: 'Full transparency on how we handle consent, marketing emails, and stored data.',
          docs: {
            updated: 'Updated {{date}}',
            viewDetails: 'View details',
            emptyIntro: 'We\'re preparing updated documentation.',
            emptyPrompt: 'Email',
            emptyOutro: 'if you need anything right away.'
          }
        },
        reschedule: {
          title: 'Reschedule appointment',
          masterLabel: 'Master',
          chooseTime: 'Choose time',
          hint: 'Scroll horizontally. Red slots are busy.',
          prev: '← Prev',
          today: 'Today',
          current: 'Current slot',
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
          cancelError: 'Cancel error: {{detail}}',
          mobileEmpty: 'No available times on this day.',
          mobileHint: 'Tap a date to see available times.'
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
        header: {
          tagline: 'Beauty & Wellness Studio',
          sendGift: 'Send a gift card',
          listBusiness: 'List your business',
          openMenu: 'Open menu',
          closeMenu: 'Close menu',
          closeMenuText: 'Close menu',
          menuLabel: 'Main menu',
          calendar: 'Open calendar shortcuts',
          notifications: 'Notifications',
          openCart: 'Open cart'
        },
        hero: {
          badge: 'Luxury wellness',
          title: 'Запишитесь за 2 клика',
          subtitle: 'Выберите услугу, мастера и время — остальное сделаем мы.',
          description: 'Pick a service, a specialist, and a time — we’ll handle the rest.',
          cta: 'Смотреть услуги ↓',
          ctaPrimary: 'Book now',
          ctaSecondary: 'Explore categories',
          stats: {
            clients: {
              value: '3.2K+',
              label: 'Happy clients this month'
            },
            specialists: {
              value: '42',
              label: 'Verified specialists online'
            },
            speed: {
              value: '2 clicks',
              label: 'Average booking time'
            }
          }
        },
        nav: {
          cart: 'Корзина',
          clientProfile: 'Личный кабинет',
          login: 'Войти',
          register: 'Create account'
        },
        section: {
          title: 'Услуги'
        },
        filters: {
          searchLabel: 'Search service',
          categoryLabel: 'Category',
          searchPlaceholder: 'Найти услугу…',
          allCategories: 'Все категории',
          submit: 'Найти',
          reset: 'Сбросить'
        },
        categories: {
          title: 'Popular Services',
          subtitle: 'Discover trending treatments curated by Malva.',
          all: 'All Services'
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
          addToCart: 'В корзину',
          viewDetails: 'View details',
          tagPopular: 'Popular',
          noImage: 'Preview coming soon',
          imageAltFallback: 'Service preview'
        },
        detail: {
          badgeFeatured: 'Signature',
          imageEmpty: 'Preview coming soon',
          unknownCategory: 'Uncategorized',
          descriptionFallback: 'We will publish the description soon.',
          durationLabel: 'Duration',
          categoryLabel: 'Category',
          priceLabel: 'Investment',
          discountLabel: '{{value}}% off today',
          formsLabel: 'Required forms',
          formsEmpty: 'No forms required before the visit.',
          formsSingular: '{{count}} form to complete before arrival.',
          formsPlural: '{{count}} forms to complete before arrival.',
          highlightsTitle: 'What to expect',
          highlightCare: 'Personal concierge care from our front-desk team.',
          highlightProducts: 'Sterile tools and lab-tested professional formulas.',
          highlightPlan: 'Personalized at-home plan after your visit.',
          ctaPrimary: 'Book this service',
          ctaSecondary: 'Back to catalog',
          metaExtraTime: '+{{value}} min prep time',
          imageAlt: 'Preview for {{name}}',
          openLabel: 'View details for {{name}}'
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
          mobileEmpty: 'No availability yet.',
          mobileDate: 'Date',
          cartPreviewLabel: 'In your cart',
          cartPreviewEmpty: 'Add services to your cart to see them here.',
          cartPreviewUnknownMaster: 'Any master',
          cartPreviewMeta: '{{master}} · {{time}} · {{duration}}',
          cartPreviewTotals: 'Total: {{total}} • {{duration}}',
          cartPreviewFee: '{{fee}} card processing fee (3% + $0.50) included.',
          success: 'Услуга добавлена в корзину.',
          errorAdd: 'Не удалось добавить услугу в корзину',
          errorGeneric: 'Ошибка добавления в корзину',
          inCartShort: 'In cart',
          slotInCart: 'Already in your cart'
        },
        cart: {
          title: 'Корзина',
          empty: 'Ваша корзина пуста.',
          summary: 'Итого: {{total}} · {{duration}}',
          processingFeeNotice: '{{fee}} card processing fee (3% + $0.50) is included in the total.',
          discount: 'Discount',
          checkout: 'Оформить',
          open: 'Open cart',
          loadFailed: 'Не удалось загрузить корзину',
          removeSuccess: 'Запись удалена из корзины.',
          removeFailed: 'Не удалось удалить запись',
          checkoutFailed: 'Не удалось оформить запись',
          finalizeFailed: 'Failed to finalize booking.',
          checkoutSuccess: 'Запись создана! Перенаправляем…',
          freeSuccess: 'Appointment booked. No payment required.',
          remove: 'Удалить'
        },
        userMenu: {
          open: 'Open user menu',
          greeting: 'Welcome back',
          tier: 'Malva Member',
          profile: 'Profile',
          appointments: 'Appointments',
          wallet: 'Wallet',
          favorites: 'Favorites',
          giftCard: 'Send a gift card',
          forms: 'Forms',
          orders: 'Product orders',
          settings: 'Settings',
          language: 'Languages',
          logout: 'Log out',
          download: 'Download the app',
          help: 'Help & support',
          business: 'For businesses'
        },
        dynamic: {
          names: {
            "service-one": 'Услуга 1',
            "service-two": 'Услуга 2',
            consultation: 'Консультация'
          }
        },
        footer: {
          copy: '© 2025 Malva Booking'
        },
        payment: {
          amountDueLabel: 'Сумма к оплате',
          feeLabel: 'Комиссия за обработку карты',
          optionLabel: 'Вариант оплаты',
          payInFullLabel: 'Оплатить полную сумму ({{percent}}%)',
          payInFullHint: 'Весь баланс будет снят сегодня.',
          payPartialLabel: 'Заплатите {{percent}}% сейчас',
          payPartialHint: 'Оставшуюся сумму {{remaining}} нужно будет оплатить позже.',
          partialNote: 'Остаток суммы будет оплачен лично или позже.',
          confirmButton: 'Подтвердить бронирование'
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
          signOut: 'Выйти',
          accountMenu: 'Меню аккаунта',
          overviewHint: 'Аналитика и быстрые действия',
          appointmentsHint: 'Предстоящие и история',
          billing: 'Выставление счетов и платежи',
          billingHint: 'Кошелек и сохраненные данные',
          setup: 'Настраивать',
          formsHint: 'Прием и обновления',
          settingsHint: 'Настройки и конфиденциальность',
          support: 'Поддерживать',
          supportHint: 'Помощь и ресурсы'
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
          payment: 'Статус оплаты',
          receipt: 'Receipt',
          receiptCta: 'View receipt',
          noReceipt: 'Not available yet'
        },
        myTitle: 'Мои записи',
        myEmpty: 'Записей нет.',
        book: '+ Записаться',
        appointment: {
          cancel: 'Отменить',
          reschedule: 'Перенести',
          completed: 'Завершено',
          paymentStatusLabel: 'Статус платежа:',
          pending: 'В ожидании',
          actionsUnavailable: 'Действия недоступны',
          noItems: 'Никаких услуг не зарегистрировано.',
          noMonth: 'В этом месяце встреч нет.'
        },
        filesTitle: 'Файлы',
        notificationsTitle: 'Уведомления',
        comingSoon: 'Скоро появится.',
        profileTitle: 'Профиль',
        forms: {
          pending: 'Forms outstanding',
          actionNeeded: 'Action needed: we still need your intake form.',
          complete: 'Complete {{count}} form(s) before your next visit.',
          completeCta: 'Complete now',
          upToDate: 'All required forms are on file.',
          review: 'Need to make changes? Update your answers anytime.',
          reviewCta: 'Review forms'
        },
        form: {
          firstName: 'Имя',
          lastName: 'Фамилия',
          phone: 'Телефон',
          email: 'E-mail',
          birthDate: 'Дата рождения',
          save: 'Сохранить изменения',
          name: 'Имя',
          postalCode: 'Почтовый индекс',
          address: 'Адрес',
          firstNamePlaceholder: 'Джейн',
          lastNamePlaceholder: 'Доу',
          postalPlaceholder: 'Т2Х1А1',
          addressPlaceholder: '123 Мейн-стрит'
        },
        reschedule: {
          title: 'Перенести запись',
          masterLabel: 'Мастер',
          chooseTime: 'Выбор времени',
          hint: 'Прокручивайте горизонтально. Красные слоты заняты.',
          prev: '← Назад',
          today: 'Сегодня',
          current: 'Текущая запись',
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
          cancelError: 'Ошибка отмены: {{detail}}',
          mobileEmpty: 'В этот день свободного времени нет.',
          mobileHint: 'Нажмите дату, чтобы увидеть доступное время.'
        },
        mobile: {
          portalLabel: 'Клиентский портал'
        },
        overview: {
          viewAll: 'Посмотреть все'
        },
        stats: {
          range: 'Последние 6 месяцев'
        },
        appointments: {
          scheduleLabel: 'Расписание'
        },
        profile: {
          subtitle: 'Обновите свои личные данные, чтобы бронирование было беспрепятственным.'
        },
        billing: {
          sectionLabel: 'Кошелек',
          title: 'Баланс и выставление счетов',
          subtitle: 'Сохраните свои платежные данные для молниеносной оплаты.',
          cardTitle: 'Платежные данные сохранены в вашем аккаунте.',
          cardSubtitle: 'Мы повторно используем эти поля в счетах и ​​при оформлении заказа на каждом устройстве.',
          fields: {
            name: 'Имя для выставления счета',
            city: 'Город',
            state: 'Провинция/штат',
            country: 'Страна'
          },
          updated: 'Обновлен {{date}}',
          notUpdated: 'Еще не обновлено.',
          syncDevice: 'Синхронизировать это устройство с аккаунтом',
          clearDevice: 'Очистить копию аккаунта'
        },
        formsTab: {
          title: 'Формы и анкеты',
          subtitle: 'Мы используем эти формы, чтобы адаптировать каждую встречу. Обновляйте их в любое время, чтобы ваши предпочтения оставались актуальными.',
          pending: 'В ожидании',
          submitted: 'Поданный',
          open: 'Открытые формы'
        },
        settings: {
          accountTitle: 'Профиль учетной записи (серверная копия)',
          accountSubtitle: 'Эти данные надежно хранятся в вашей учетной записи Malva.',
          howHeard: 'Как услышал',
          marketingConsent: 'Маркетинговое согласие',
          marketingSubscribed: 'Подписан',
          marketingUnsubscribed: 'Не подписан',
          syncProfile: 'Синхронизировать профиль с этим устройством',
          clearProfile: 'Очистить копию устройства',
          languageTitle: 'Язык и оповещения',
          languageSubtitle: 'Обеспечьте единообразие каждой точки взаимодействия, выбрав предпочтительный язык.',
          languageNote: 'Изменения применяются мгновенно и синхронизируются во всех ваших сеансах входа в систему.'
        },
        device: {
          title: 'Автозаполнение устройства',
          subtitle: 'Сохраненные данные формы никогда не покидают этот браузер. Снимите флажок, если вы находитесь на общем компьютере.',
          empty: 'На этом устройстве пока нет данных автозаполнения.',
          clear: 'Очистить все данные устройства'
        },
        support: {
          conciergeTitle: 'Консьерж-поддержка',
          conciergeSubtitle: 'Напишите нашей команде, чтобы получить помощь по планированию, изменениям в учетной записи или рекомендациям по продукту.',
          email: 'Электронная почта:',
          phone: 'Телефон:',
          hours: 'Часы:',
          hoursValue: 'Понедельник–пятница, 9:00–18:00.',
          bookAgain: 'Забронируйте еще один визит',
          updateForms: 'Обновить формы',
          resourcesTitle: 'Ресурсы и загрузки',
          resourcesSubtitle: 'Держите Malva рядом с нашим приложением и краткими руководствами.',
          resources: {
            walkthroughs: 'Пошаговое руководство по работе с учетной записью',
            aftercare: 'Рекомендации по уходу от вашего мастера',
            receipts: 'Печатные квитанции и подтверждения бронирования'
          },
          helpCenter: 'Посетите справочный центр',
          policiesTitle: 'Политика и конфиденциальность',
          policiesSubtitle: 'Полная прозрачность в отношении того, как мы обрабатываем согласие, маркетинговые электронные письма и хранимые данные.',
          docs: {
            updated: 'Обновлен {{date}}',
            viewDetails: 'Посмотреть детали',
            emptyIntro: 'Мы готовим обновленную документацию.',
            emptyPrompt: 'Электронная почта',
            emptyOutro: 'если вам что-то нужно прямо сейчас.'
          }
        }
      }
    },
    hi: {
      languages: {
        en: 'अंग्रेज़ी',
        ru: 'रूसी',
        uk: 'यूक्रेनी',
        fr: 'फ़्रेंच',
        ar: 'अरबी',
        hi: 'हिन्दी'
      },
      common: {
        brand: 'Malva Booking',
        language: 'भाषा',
        close: 'बंद करें',
        cancel: 'रद्द करें',
        save: 'सहेजें',
        saveChanges: 'परिवर्तन सहेजें',
        signOut: 'साइन आउट',
        backHome: 'मुख्य पृष्ठ पर लौटें',
        clientProfile: 'क्लाइंट प्रोफ़ाइल',
        login: 'लॉग इन',
        cart: 'कार्ट',
        checkout: 'चेकआउट',
        addToCart: 'कार्ट में जोड़ें',
        free: 'खाली',
        busy: 'व्यस्त',
        service: 'सेवा',
        noTime: 'समय नहीं'
      },
      services: {
        meta: {
          title: 'Malva Booking — सेवाएँ'
        },
        header: {
          tagline: 'Beauty & Wellness Studio',
          sendGift: 'Send a gift card',
          listBusiness: 'List your business',
          openMenu: 'Open menu',
          closeMenu: 'Close menu',
          closeMenuText: 'Close menu',
          menuLabel: 'Main menu',
          calendar: 'Open calendar shortcuts',
          notifications: 'Notifications',
          openCart: 'Open cart'
        },
        hero: {
          badge: 'Luxury wellness',
          title: 'सिर्फ 2 क्लिक में अपॉइंटमेंट बुक करें',
          subtitle: 'सेवा, विशेषज्ञ और समय चुनें — बाकी हम सम्भालेंगे।',
          description: 'Pick a service, a specialist, and a time — we’ll handle the rest.',
          cta: 'सेवाएँ देखें ↓',
          ctaPrimary: 'Book now',
          ctaSecondary: 'Explore categories',
          stats: {
            clients: {
              value: '3.2K+',
              label: 'Happy clients this month'
            },
            specialists: {
              value: '42',
              label: 'Verified specialists online'
            },
            speed: {
              value: '2 clicks',
              label: 'Average booking time'
            }
          }
        },
        nav: {
          cart: 'कार्ट',
          clientProfile: 'क्लाइंट प्रोफ़ाइल',
          login: 'लॉग इन',
          register: 'Create account'
        },
        section: {
          title: 'सेवाएँ'
        },
        filters: {
          searchLabel: 'Search service',
          categoryLabel: 'Category',
          searchPlaceholder: 'सेवा खोजें…',
          allCategories: 'सभी श्रेणियाँ',
          submit: 'खोजें',
          reset: 'रीसेट'
        },
        categories: {
          title: 'Popular Services',
          subtitle: 'Discover trending treatments curated by Malva.',
          all: 'All Services'
        },
        search: {
          liveTitle: 'खोज परिणाम',
          resultsTitle: 'खोज परिणाम',
          noServerResults: '“{{query}}” के लिए कोई परिणाम नहीं मिला।',
          noCategory: 'इस श्रेणी में अभी कोई सेवा नहीं है।',
          uncategorized: 'बिना श्रेणी',
          emptyCatalogue: 'कैटलॉग जल्द उपलब्ध होगा 👍',
          noResults: 'कोई सेवाएँ नहीं मिलीं।',
          error: 'परिणाम लोड नहीं हो सके। कृपया दोबारा प्रयास करें।',
          loadFailed: 'लोड विफल रहा'
        },
        cards: {
          addToCart: 'कार्ट में जोड़ें',
          viewDetails: 'View details',
          tagPopular: 'Popular',
          noImage: 'Preview coming soon',
          imageAltFallback: 'Service preview'
        },
        detail: {
          badgeFeatured: 'Signature',
          imageEmpty: 'Preview coming soon',
          unknownCategory: 'Uncategorized',
          descriptionFallback: 'We will publish the description soon.',
          durationLabel: 'Duration',
          categoryLabel: 'Category',
          priceLabel: 'Investment',
          discountLabel: '{{value}}% off today',
          formsLabel: 'Required forms',
          formsEmpty: 'No forms required before the visit.',
          formsSingular: '{{count}} form to complete before arrival.',
          formsPlural: '{{count}} forms to complete before arrival.',
          highlightsTitle: 'What to expect',
          highlightCare: 'Personal concierge care from our front-desk team.',
          highlightProducts: 'Sterile tools and lab-tested professional formulas.',
          highlightPlan: 'Personalized at-home plan after your visit.',
          ctaPrimary: 'Book this service',
          ctaSecondary: 'Back to catalog',
          metaExtraTime: '+{{value}} min prep time',
          imageAlt: 'Preview for {{name}}',
          openLabel: 'View details for {{name}}'
        },
        units: {
          minutes: '{{value}} मिनट'
        },
        modal: {
          title: 'सेवा जोड़ें:',
          masterLabel: 'मास्टर',
          chooseTime: 'समय चुनें',
          prev: '← पिछला',
          today: 'आज',
          next: 'अगला →',
          legendFree: 'खाली',
          legendBusy: 'व्यस्त',
          legendHint: 'क्षैतिज रूप से स्क्रोल करें। लाल स्लॉट व्यस्त हैं और क्लिक नहीं किए जा सकते।',
          summaryLabel: 'सारांश',
          summaryPlaceholder: 'मास्टर और समय चुनें।',
          summarySelected: 'मास्टर: {{master}}. समय: {{time}}, {{date}}.',
          errorLoad: 'उपलब्ध स्लॉट लाने में असमर्थ',
          noMasters: 'कोई मास्टर उपलब्ध नहीं है',
          noAvailability: 'स्लॉट उपलब्ध नहीं हैं',
          mobileEmpty: 'No availability yet.',
          mobileDate: 'Date',
          cartPreviewLabel: 'In your cart',
          cartPreviewEmpty: 'Add services to your cart to see them here.',
          cartPreviewUnknownMaster: 'Any master',
          cartPreviewMeta: '{{master}} · {{time}} · {{duration}}',
          cartPreviewTotals: 'Total: {{total}} • {{duration}}',
          cartPreviewFee: '{{fee}} card processing fee (3% + $0.50) included.',
          success: 'सेवा कार्ट में जोड़ दी गई है।',
          errorAdd: 'सेवा को कार्ट में जोड़ नहीं सके',
          errorGeneric: 'कार्ट में जोड़ने में त्रुटि',
          inCartShort: 'In cart',
          slotInCart: 'Already in your cart'
        },
        cart: {
          title: 'कार्ट',
          empty: 'आपका कार्ट खाली है।',
          summary: 'कुल: {{total}} · {{duration}}',
          processingFeeNotice: '{{fee}} card processing fee (3% + $0.50) is included in the total.',
          discount: 'Discount',
          checkout: 'चेकआउट',
          open: 'Open cart',
          loadFailed: 'कार्ट लोड नहीं हो सका',
          removeSuccess: 'आइटम कार्ट से हटाया गया।',
          removeFailed: 'आइटम हटाया नहीं जा सका',
          checkoutFailed: 'चेकआउट असफल रहा',
          finalizeFailed: 'Failed to finalize booking.',
          checkoutSuccess: 'अपॉइंटमेंट बन गया! रीडायरेक्ट किया जा रहा है…',
          freeSuccess: 'Appointment booked. No payment required.',
          remove: 'आइटम हटाएँ'
        },
        userMenu: {
          open: 'Open user menu',
          greeting: 'Welcome back',
          tier: 'Malva Member',
          profile: 'Profile',
          appointments: 'Appointments',
          wallet: 'Wallet',
          favorites: 'Favorites',
          giftCard: 'Send a gift card',
          forms: 'Forms',
          orders: 'Product orders',
          settings: 'Settings',
          language: 'Languages',
          logout: 'Log out',
          download: 'Download the app',
          help: 'Help & support',
          business: 'For businesses'
        },
        dynamic: {
          names: {
            "service-one": 'सेवा 1',
            "service-two": 'सेवा 2',
            consultation: 'परामर्श'
          }
        },
        footer: {
          copy: '© 2025 Malva Booking'
        },
        payment: {
          amountDueLabel: 'देय राशि',
          feeLabel: 'कार्ड प्रोसेसिंग शुल्क',
          optionLabel: 'भुगतान विकल्प',
          payInFullLabel: 'पूरा भुगतान करें ({{percent}}%)',
          payInFullHint: 'पूरा बकाया आज वसूला जाएगा.',
          payPartialLabel: 'अभी {{percent}}% का भुगतान करें',
          payPartialHint: 'शेष {{remaining}} बाद में देय होगा।',
          partialNote: 'शेष राशि व्यक्तिगत रूप से या बाद में देय होगी।',
          confirmButton: 'बुकिंग की पुष्टि करें'
        }
      },
      dashboard: {
        meta: {
          title: 'क्लाइंट पोर्टल | Malva Booking'
        },
        nav: {
          overview: 'सारांश',
          appointments: 'अपॉइंटमेंट्स',
          files: 'फ़ाइलें',
          notifications: 'सूचनाएँ',
          profile: 'प्रोफ़ाइल',
          back: 'होम पर वापस',
          signOut: 'साइन आउट',
          accountMenu: 'खाता मेनू',
          overviewHint: 'अंतर्दृष्टि और त्वरित कार्रवाई',
          appointmentsHint: 'आगामी एवं इतिहास',
          billing: 'बिलिंग एवं भुगतान',
          billingHint: 'वॉलेट और सहेजे गए विवरण',
          setup: 'स्थापित करना',
          formsHint: 'सेवन और अद्यतन',
          settingsHint: 'प्राथमिकताएँ और गोपनीयता',
          support: 'सहायता',
          supportHint: 'सहायता एवं संसाधन'
        },
        greetingNamed: 'नमस्ते, {{name}}!',
        greetingAnon: 'नमस्ते, {{username}}!',
        upcomingTitle: 'आगामी अपॉइंटमेंट्स',
        upcomingEmpty: 'कोई आगामी अपॉइंटमेंट नहीं।',
        statsTitle: 'आँकड़े',
        chartLabel: 'अपॉइंटमेंट्स',
        recentTitle: 'हाल की अपॉइंटमेंट्स',
        recentEmpty: 'अभी तक कोई पूर्ण अपॉइंटमेंट नहीं।',
        table: {
          date: 'तारीख',
          service: 'सेवा',
          master: 'मास्टर',
          status: 'स्थिति',
          payment: 'भुगतान स्थिति',
          receipt: 'Receipt',
          receiptCta: 'View receipt',
          noReceipt: 'Not available yet'
        },
        myTitle: 'मेरी अपॉइंटमेंट्स',
        myEmpty: 'अपॉइंटमेंट नहीं हैं।',
        book: '+ बुक करें',
        appointment: {
          cancel: 'रद्द करें',
          reschedule: 'पुनर्निर्धारित करें',
          completed: 'पूरा हुआ',
          paymentStatusLabel: 'भुगतान की स्थिति:',
          pending: 'लंबित',
          actionsUnavailable: 'क्रियाएँ अनुपलब्ध',
          noItems: 'कोई सेवाएँ दर्ज नहीं की गईं.',
          noMonth: 'इस महीने कोई नियुक्ति नहीं.'
        },
        filesTitle: 'फ़ाइलें',
        notificationsTitle: 'सूचनाएँ',
        comingSoon: 'जल्द उपलब्ध होगा।',
        profileTitle: 'प्रोफ़ाइल',
        forms: {
          pending: 'Forms outstanding',
          actionNeeded: 'Action needed: we still need your intake form.',
          complete: 'Complete {{count}} form(s) before your next visit.',
          completeCta: 'Complete now',
          upToDate: 'All required forms are on file.',
          review: 'Need to make changes? Update your answers anytime.',
          reviewCta: 'Review forms'
        },
        form: {
          firstName: 'पहला नाम',
          lastName: 'अंतिम नाम',
          phone: 'फ़ोन',
          email: 'ई-मेल',
          birthDate: 'जन्म तारीख',
          save: 'परिवर्तन सहेजें',
          name: 'नाम',
          postalCode: 'डाक कोड',
          address: 'पता',
          firstNamePlaceholder: 'जेन',
          lastNamePlaceholder: 'हरिणी',
          postalPlaceholder: 'T2X1A1',
          addressPlaceholder: '123 मुख्य सेंट'
        },
        reschedule: {
          title: 'अपॉइंटमेंट पुनर्निर्धारित करें',
          masterLabel: 'मास्टर',
          chooseTime: 'समय चुनें',
          hint: 'क्षैतिज रूप से स्क्रोल करें। लाल स्लॉट व्यस्त हैं।',
          prev: '← पिछला',
          today: 'आज',
          current: 'वर्तमान स्लॉट',
          next: 'अगला →',
          cancel: 'रद्द करें',
          save: 'सहेजें',
          noMasters: 'कोई मास्टर उपलब्ध नहीं है',
          noAvailability: 'स्लॉट उपलब्ध नहीं हैं',
          success: '{{datetime}} पर पुनर्निर्धारित किया गया',
          failed: 'पुनर्निर्धारण असफल रहा',
          loadFailed: 'स्लॉट लोड नहीं हो सके',
          errorLoad: 'उपलब्ध स्लॉट लाने में असमर्थ',
          confirmCancel: 'क्या आप इस अपॉइंटमेंट को रद्द करना चाहते हैं?',
          cancelError: 'रद्द करने में त्रुटि: {{detail}}',
          mobileEmpty: 'इस दिन कोई उपलब्ध समय नहीं है.',
          mobileHint: 'उपलब्ध समय देखने के लिए किसी दिनांक पर टैप करें।'
        },
        mobile: {
          portalLabel: 'ग्राहक पोर्टल'
        },
        overview: {
          viewAll: 'सभी को देखें'
        },
        stats: {
          range: 'पिछले 6 महीने'
        },
        appointments: {
          scheduleLabel: 'अनुसूची'
        },
        profile: {
          subtitle: 'बुकिंग को निर्बाध बनाए रखने के लिए अपने व्यक्तिगत विवरण अपडेट करें।'
        },
        billing: {
          sectionLabel: 'बटुआ',
          title: 'संतुलन एवं बिलिंग',
          subtitle: 'बिजली की तेजी से चेकआउट के लिए अपना भुगतान विवरण संग्रहीत करें।',
          cardTitle: 'बिलिंग विवरण आपके खाते में सहेजा गया',
          cardSubtitle: 'हम प्रत्येक डिवाइस पर इनवॉइस और चेकआउट में इन फ़ील्ड का पुन: उपयोग करते हैं।',
          fields: {
            name: 'बिलिंग नाम',
            city: 'शहर',
            state: 'प्रांत/राज्य',
            country: 'देश'
          },
          updated: 'अपडेट किया गया {{date}}',
          notUpdated: 'अभी तक अपडेट नहीं किया गया है.',
          syncDevice: 'इस डिवाइस को खाते से सिंक करें',
          clearDevice: 'खाता प्रतिलिपि साफ़ करें'
        },
        formsTab: {
          title: 'फॉर्म और प्रश्नावली',
          subtitle: 'हम प्रत्येक नियुक्ति को तैयार करने के लिए इन प्रपत्रों का उपयोग करते हैं। अपनी प्राथमिकताओं को ताज़ा रखने के लिए उन्हें कभी भी अपडेट करें।',
          pending: 'लंबित',
          submitted: 'प्रस्तुत किया गया',
          open: 'प्रपत्र खोलें'
        },
        settings: {
          accountTitle: 'खाता प्रोफ़ाइल (सर्वर प्रतिलिपि)',
          accountSubtitle: 'ये विवरण आपके Malva खाते में सुरक्षित रूप से रहते हैं।',
          howHeard: 'कैसे सुना',
          marketingConsent: 'विपणन सहमति',
          marketingSubscribed: 'सदस्यता लिया',
          marketingUnsubscribed: 'सदस्यता नहीं ली गई',
          syncProfile: 'प्रोफ़ाइल को इस डिवाइस से सिंक करें',
          clearProfile: 'डिवाइस कॉपी साफ़ करें',
          languageTitle: 'भाषा और अलर्ट',
          languageSubtitle: 'पसंदीदा भाषा चुनकर प्रत्येक संपर्क बिंदु को सुसंगत रखें।',
          languageNote: 'परिवर्तन तुरंत लागू होते हैं और आपके सभी साइन-इन सत्रों में समन्वयित होते हैं।'
        },
        device: {
          title: 'डिवाइस स्वतः भरण',
          subtitle: 'सहेजा गया फ़ॉर्म डेटा इस ब्राउज़र को कभी नहीं छोड़ता. यदि आप साझा कंप्यूटर पर हैं तो इसे साफ़ करें।',
          empty: 'इस उपकरण पर अभी तक कोई स्वतः भरण डेटा संग्रहीत नहीं है।',
          clear: 'सभी डिवाइस डेटा साफ़ करें'
        },
        support: {
          conciergeTitle: 'दरबान समर्थन',
          conciergeSubtitle: 'शेड्यूलिंग सहायता, खाता परिवर्तन या उत्पाद मार्गदर्शन के लिए हमारी टीम को संदेश भेजें।',
          email: 'ईमेल:',
          phone: 'फ़ोन:',
          hours: 'घंटे:',
          hoursValue: 'सोमवार-शुक्रवार, सुबह 9 बजे से शाम 6 बजे तक',
          bookAgain: 'एक और यात्रा बुक करें',
          updateForms: 'फॉर्म अपडेट करें',
          resourcesTitle: 'संसाधन एवं डाउनलोड',
          resourcesSubtitle: 'हमारे ऐप और त्वरित-संदर्भ मार्गदर्शिकाओं के साथ Malva को करीब रखें।',
          resources: {
            walkthroughs: 'चरण-दर-चरण खाता पूर्वाभ्यास',
            aftercare: 'आपके गुरु की ओर से देखभाल संबंधी सिफ़ारिशें',
            receipts: 'मुद्रण योग्य रसीदें और बुकिंग पुष्टिकरण'
          },
          helpCenter: 'सहायता केंद्र पर जाएँ',
          policiesTitle: 'नीतियां और गोपनीयता',
          policiesSubtitle: 'हम सहमति, मार्केटिंग ईमेल और संग्रहीत डेटा को कैसे संभालते हैं, इस पर पूर्ण पारदर्शिता।',
          docs: {
            updated: 'अपडेट किया गया {{date}}',
            viewDetails: 'विवरण देखें',
            emptyIntro: 'हम अद्यतन दस्तावेज़ तैयार कर रहे हैं.',
            emptyPrompt: 'ईमेल',
            emptyOutro: 'अगर आपको तुरंत किसी चीज़ की ज़रूरत है।'
          }
        }
      }
    },
    uk: {
      languages: {
        en: 'Англійська',
        ru: 'Російська',
        uk: 'Українська',
        fr: 'Французька',
        ar: 'Арабська',
        hi: 'Гінді'
      },
      common: {
        brand: 'Malva Booking',
        language: 'Мова',
        close: 'Закрити',
        cancel: 'Скасувати',
        save: 'Зберегти',
        saveChanges: 'Зберегти зміни',
        signOut: 'Вийти',
        backHome: 'Повернутися на головну',
        clientProfile: 'Кабінет клієнта',
        login: 'Увійти',
        cart: 'Кошик',
        checkout: 'Оформити',
        addToCart: 'До кошика',
        free: 'вільно',
        busy: 'зайнято',
        service: 'Послуга',
        noTime: 'Немає часу'
      },
      services: {
        meta: {
          title: 'Malva Booking — Послуги'
        },
        header: {
          tagline: 'Beauty & Wellness Studio',
          sendGift: 'Send a gift card',
          listBusiness: 'List your business',
          openMenu: 'Open menu',
          closeMenu: 'Close menu',
          closeMenuText: 'Close menu',
          menuLabel: 'Main menu',
          calendar: 'Open calendar shortcuts',
          notifications: 'Notifications',
          openCart: 'Open cart'
        },
        hero: {
          badge: 'Luxury wellness',
          title: 'Запишіться за 2 кліки',
          subtitle: 'Обирайте послугу, майстра та час — решту зробимо ми.',
          description: 'Pick a service, a specialist, and a time — we’ll handle the rest.',
          cta: 'Переглянути послуги ↓',
          ctaPrimary: 'Book now',
          ctaSecondary: 'Explore categories',
          stats: {
            clients: {
              value: '3.2K+',
              label: 'Happy clients this month'
            },
            specialists: {
              value: '42',
              label: 'Verified specialists online'
            },
            speed: {
              value: '2 clicks',
              label: 'Average booking time'
            }
          }
        },
        nav: {
          cart: 'Кошик',
          clientProfile: 'Кабінет клієнта',
          login: 'Увійти',
          register: 'Create account'
        },
        section: {
          title: 'Послуги'
        },
        filters: {
          searchLabel: 'Search service',
          categoryLabel: 'Category',
          searchPlaceholder: 'Знайти послугу…',
          allCategories: 'Усі категорії',
          submit: 'Знайти',
          reset: 'Скинути'
        },
        categories: {
          title: 'Popular Services',
          subtitle: 'Discover trending treatments curated by Malva.',
          all: 'All Services'
        },
        search: {
          liveTitle: 'Результати пошуку',
          resultsTitle: 'Результати пошуку',
          noServerResults: 'За “{{query}}” нічого не знайдено.',
          noCategory: 'У цій категорії поки що немає послуг.',
          uncategorized: 'Без категорії',
          emptyCatalogue: 'Каталог з’явиться незабаром 👍',
          noResults: 'Послуги не знайдено.',
          error: 'Не вдалося завантажити результати. Спробуйте ще раз.',
          loadFailed: 'Не вдалося завантажити'
        },
        cards: {
          addToCart: 'До кошика',
          viewDetails: 'View details',
          tagPopular: 'Popular',
          noImage: 'Preview coming soon',
          imageAltFallback: 'Service preview'
        },
        detail: {
          badgeFeatured: 'Signature',
          imageEmpty: 'Preview coming soon',
          unknownCategory: 'Uncategorized',
          descriptionFallback: 'We will publish the description soon.',
          durationLabel: 'Duration',
          categoryLabel: 'Category',
          priceLabel: 'Investment',
          discountLabel: '{{value}}% off today',
          formsLabel: 'Required forms',
          formsEmpty: 'No forms required before the visit.',
          formsSingular: '{{count}} form to complete before arrival.',
          formsPlural: '{{count}} forms to complete before arrival.',
          highlightsTitle: 'What to expect',
          highlightCare: 'Personal concierge care from our front-desk team.',
          highlightProducts: 'Sterile tools and lab-tested professional formulas.',
          highlightPlan: 'Personalized at-home plan after your visit.',
          ctaPrimary: 'Book this service',
          ctaSecondary: 'Back to catalog',
          metaExtraTime: '+{{value}} min prep time',
          imageAlt: 'Preview for {{name}}',
          openLabel: 'View details for {{name}}'
        },
        units: {
          minutes: '{{value}} хв'
        },
        modal: {
          title: 'Додати послугу:',
          masterLabel: 'Майстер',
          chooseTime: 'Виберіть час',
          prev: '← Назад',
          today: 'Сьогодні',
          next: 'Далі →',
          legendFree: 'вільно',
          legendBusy: 'зайнято',
          legendHint: 'Прокручуйте горизонтально. Червоні слоти зайняті й недоступні.',
          summaryLabel: 'Підсумок',
          summaryPlaceholder: 'Виберіть майстра та час.',
          summarySelected: 'Майстер: {{master}}. Час: {{time}}, {{date}}.',
          errorLoad: 'Не вдалося отримати доступні слоти',
          noMasters: 'Немає доступних майстрів',
          noAvailability: 'Немає доступних слотів',
          mobileEmpty: 'No availability yet.',
          mobileDate: 'Date',
          cartPreviewLabel: 'In your cart',
          cartPreviewEmpty: 'Add services to your cart to see them here.',
          cartPreviewUnknownMaster: 'Any master',
          cartPreviewMeta: '{{master}} · {{time}} · {{duration}}',
          cartPreviewTotals: 'Total: {{total}} • {{duration}}',
          cartPreviewFee: '{{fee}} card processing fee (3% + $0.50) included.',
          success: 'Послугу додано до кошика.',
          errorAdd: 'Не вдалося додати послугу до кошика',
          errorGeneric: 'Помилка додавання до кошика',
          inCartShort: 'In cart',
          slotInCart: 'Already in your cart'
        },
        cart: {
          title: 'Кошик',
          empty: 'Ваш кошик порожній.',
          summary: 'Разом: {{total}} · {{duration}}',
          processingFeeNotice: '{{fee}} card processing fee (3% + $0.50) is included in the total.',
          discount: 'Discount',
          checkout: 'Оформити',
          open: 'Open cart',
          loadFailed: 'Не вдалося завантажити кошик',
          removeSuccess: 'Послугу видалено з кошика.',
          removeFailed: 'Не вдалося видалити послугу',
          checkoutFailed: 'Не вдалося оформити запис',
          finalizeFailed: 'Failed to finalize booking.',
          checkoutSuccess: 'Запис створено! Перенаправляємо…',
          freeSuccess: 'Appointment booked. No payment required.',
          remove: 'Видалити'
        },
        userMenu: {
          open: 'Open user menu',
          greeting: 'Welcome back',
          tier: 'Malva Member',
          profile: 'Profile',
          appointments: 'Appointments',
          wallet: 'Wallet',
          favorites: 'Favorites',
          giftCard: 'Send a gift card',
          forms: 'Forms',
          orders: 'Product orders',
          settings: 'Settings',
          language: 'Languages',
          logout: 'Log out',
          download: 'Download the app',
          help: 'Help & support',
          business: 'For businesses'
        },
        dynamic: {
          names: {
            "service-one": 'Послуга 1',
            "service-two": 'Послуга 2',
            consultation: 'Консультація'
          }
        },
        footer: {
          copy: '© 2025 Malva Booking'
        },
        payment: {
          amountDueLabel: 'Сума до сплати',
          feeLabel: 'Плата за обробку картки',
          optionLabel: 'Варіант оплати',
          payInFullLabel: 'Сплатити повністю ({{percent}}%)',
          payInFullHint: 'Увесь баланс буде стягнено сьогодні.',
          payPartialLabel: 'Сплатіть {{percent}}% зараз',
          payPartialHint: 'Решта {{remaining}} буде надано пізніше.',
          partialNote: 'Залишок необхідно сплатити особисто або пізніше.',
          confirmButton: 'Підтвердити бронювання'
        }
      },
      dashboard: {
        meta: {
          title: 'Кабінет клієнта | Malva Booking'
        },
        nav: {
          overview: 'Огляд',
          appointments: 'Записи',
          files: 'Файли',
          notifications: 'Сповіщення',
          profile: 'Профіль',
          back: 'Назад на сайт',
          signOut: 'Вийти',
          accountMenu: 'Меню облікового запису',
          overviewHint: 'Статистика та швидкі дії',
          appointmentsHint: 'Майбутнє та історія',
          billing: 'Рахунки та платежі',
          billingHint: 'Гаманець і збережені дані',
          setup: 'Налаштування',
          formsHint: 'Надходження та оновлення',
          settingsHint: 'Налаштування та конфіденційність',
          support: 'Підтримка',
          supportHint: 'Довідка та ресурси'
        },
        greetingNamed: 'Привіт, {{name}}!',
        greetingAnon: 'Привіт, {{username}}!',
        upcomingTitle: 'Найближчі записи',
        upcomingEmpty: 'Немає запланованих записів.',
        statsTitle: 'Статистика',
        chartLabel: 'Записи',
        recentTitle: 'Останні записи',
        recentEmpty: 'Поки немає завершених записів.',
        table: {
          date: 'Дата',
          service: 'Послуга',
          master: 'Майстер',
          status: 'Статус',
          payment: 'Статус оплати',
          receipt: 'Receipt',
          receiptCta: 'View receipt',
          noReceipt: 'Not available yet'
        },
        myTitle: 'Мої записи',
        myEmpty: 'Записів немає.',
        book: '+ Записатися',
        appointment: {
          cancel: 'Скасувати',
          reschedule: 'Перенести',
          completed: 'Завершено',
          paymentStatusLabel: 'Статус платежу:',
          pending: 'В очікуванні',
          actionsUnavailable: 'Дії недоступні',
          noItems: 'Служби не зареєстровані.',
          noMonth: 'Немає зустрічей цього місяця.'
        },
        filesTitle: 'Файли',
        notificationsTitle: 'Сповіщення',
        comingSoon: 'Скоро з’явиться.',
        profileTitle: 'Профіль',
        forms: {
          pending: 'Forms outstanding',
          actionNeeded: 'Action needed: we still need your intake form.',
          complete: 'Complete {{count}} form(s) before your next visit.',
          completeCta: 'Complete now',
          upToDate: 'All required forms are on file.',
          review: 'Need to make changes? Update your answers anytime.',
          reviewCta: 'Review forms'
        },
        form: {
          firstName: 'Ім’я',
          lastName: 'Прізвище',
          phone: 'Телефон',
          email: 'E-mail',
          birthDate: 'Дата народження',
          save: 'Зберегти зміни',
          name: 'Ім\'я',
          postalCode: 'Поштовий індекс',
          address: 'Адреса',
          firstNamePlaceholder: 'Джейн',
          lastNamePlaceholder: 'лань',
          postalPlaceholder: 'T2X1A1',
          addressPlaceholder: 'вул. Головна, 123'
        },
        reschedule: {
          title: 'Перенести запис',
          masterLabel: 'Майстер',
          chooseTime: 'Виберіть час',
          hint: 'Прокручуйте горизонтально. Червоні слоти зайняті.',
          prev: '← Назад',
          today: 'Сьогодні',
          current: 'Поточний запис',
          next: 'Далі →',
          cancel: 'Скасувати',
          save: 'Зберегти',
          noMasters: 'Немає доступних майстрів',
          noAvailability: 'Немає доступних слотів',
          success: 'Перенесено на {{datetime}}',
          failed: 'Не вдалося перенести',
          loadFailed: 'Не вдалося завантажити слоти',
          errorLoad: 'Не вдалося отримати доступні слоти',
          confirmCancel: 'Скасувати цей запис?',
          cancelError: 'Помилка скасування: {{detail}}',
          mobileEmpty: 'У цей день немає доступних годин.',
          mobileHint: 'Торкніться дати, щоб побачити доступний час.'
        },
        mobile: {
          portalLabel: 'Клієнтський портал'
        },
        overview: {
          viewAll: 'Переглянути всі'
        },
        stats: {
          range: 'Останні 6 місяців'
        },
        appointments: {
          scheduleLabel: 'розклад'
        },
        profile: {
          subtitle: 'Оновіть свої особисті дані, щоб бронювати без проблем.'
        },
        billing: {
          sectionLabel: 'Гаманець',
          title: 'Баланс і виставлення рахунків',
          subtitle: 'Зберігайте свої платіжні дані для блискавичної оплати.',
          cardTitle: 'Платіжні дані збережено у вашому обліковому записі',
          cardSubtitle: 'Ми повторно використовуємо ці поля в рахунках-фактурах і на кожному пристрої.',
          fields: {
            name: 'Платіжна назва',
            city: 'Місто',
            state: 'Провінція / Штат',
            country: 'Країна'
          },
          updated: 'Оновлено {{date}}',
          notUpdated: 'Ще не оновлено.',
          syncDevice: 'Синхронізувати цей пристрій з обліковим записом',
          clearDevice: 'Очистити копію облікового запису'
        },
        formsTab: {
          title: 'Форми та анкети',
          subtitle: 'Ми використовуємо ці форми, щоб адаптувати кожну зустріч. Оновлюйте їх у будь-який час, щоб ваші налаштування залишалися актуальними.',
          pending: 'В очікуванні',
          submitted: 'Надіслано',
          open: 'Відкриті форми'
        },
        settings: {
          accountTitle: 'Профіль облікового запису (серверна копія)',
          accountSubtitle: 'Ці дані надійно зберігаються у вашому обліковому записі Malva.',
          howHeard: 'Як чули',
          marketingConsent: 'Маркетинговий дозвіл',
          marketingSubscribed: 'Підписався',
          marketingUnsubscribed: 'Не підписаний',
          syncProfile: 'Синхронізувати профіль із цим пристроєм',
          clearProfile: 'Очистити копію пристрою',
          languageTitle: 'Мова та сповіщення',
          languageSubtitle: 'Зберігайте кожну точку взаємодії узгодженою, вибравши потрібну мову.',
          languageNote: 'Зміни застосовуються миттєво та синхронізуються з усіма сеансами, під час яких ви ввійшли в систему.'
        },
        device: {
          title: 'Автозаповнення пристрою',
          subtitle: 'Збережені дані форми ніколи не залишають цей браузер. Зніміть його, якщо ви перебуваєте на спільному комп’ютері.',
          empty: 'На цьому пристрої ще немає даних автозаповнення.',
          clear: 'Очистити всі дані пристрою'
        },
        support: {
          conciergeTitle: 'Консьєрж-підтримка',
          conciergeSubtitle: 'Надішліть повідомлення нашій команді, щоб отримати допомогу щодо планування, зміни облікового запису або отримання вказівок щодо продукту.',
          email: 'Електронна пошта:',
          phone: 'телефон:',
          hours: 'Час роботи:',
          hoursValue: 'Понеділок–п’ятниця, 9:00–18:00',
          bookAgain: 'Замовте ще один візит',
          updateForms: 'Оновлення форм',
          resourcesTitle: 'Ресурси та завантаження',
          resourcesSubtitle: 'Тримайте Malva поруч із нашим додатком і короткими довідниками.',
          resources: {
            walkthroughs: 'Покрокові інструкції з облікового запису',
            aftercare: 'Рекомендації по догляду від майстра',
            receipts: 'Квитанції та підтвердження бронювання для друку'
          },
          helpCenter: 'Відвідайте довідковий центр',
          policiesTitle: 'Політика та конфіденційність',
          policiesSubtitle: 'Повна прозорість щодо того, як ми обробляємо згоду, маркетингові електронні листи та збережені дані.',
          docs: {
            updated: 'Оновлено {{date}}',
            viewDetails: 'Переглянути деталі',
            emptyIntro: 'Готуємо оновлену документацію.',
            emptyPrompt: 'Електронна пошта',
            emptyOutro: 'якщо вам щось потрібно негайно.'
          }
        }
      }
    },
    fr: {
      languages: {
        en: 'Anglais',
        ru: 'Russe',
        uk: 'Ukrainien',
        fr: 'Français',
        ar: 'Arabe',
        hi: 'Hindi'
      },
      common: {
        brand: 'Malva Booking',
        language: 'Langue',
        close: 'Fermer',
        cancel: 'Annuler',
        save: 'Enregistrer',
        saveChanges: 'Enregistrer les modifications',
        signOut: 'Déconnexion',
        backHome: 'Retour à l’accueil',
        clientProfile: 'Espace client',
        login: 'Connexion',
        cart: 'Panier',
        checkout: 'Valider',
        addToCart: 'Ajouter au panier',
        free: 'disponible',
        busy: 'occupé',
        service: 'Service',
        noTime: 'Pas d’horaire'
      },
      services: {
        meta: {
          title: 'Malva Booking — Services'
        },
        hero: {
          badge: 'Luxury wellness',
          title: 'Réservez votre rendez-vous en 2 clics',
          subtitle: 'Choisissez une prestation, un expert et un horaire — nous nous occupons du reste.',
          description: 'Pick a service, a specialist, and a time — we’ll handle the rest.',
          cta: 'Voir les services ↓',
          ctaPrimary: 'Book now',
          ctaSecondary: 'Explore categories',
          stats: {
            clients: {
              value: '3.2K+',
              label: 'Happy clients this month'
            },
            specialists: {
              value: '42',
              label: 'Verified specialists online'
            },
            speed: {
              value: '2 clicks',
              label: 'Average booking time'
            }
          }
        },
        nav: {
          cart: 'Panier',
          clientProfile: 'Espace client',
          login: 'Connexion',
          register: 'Create account'
        },
        section: {
          title: 'Services'
        },
        filters: {
          searchLabel: 'Search service',
          categoryLabel: 'Category',
          searchPlaceholder: 'Rechercher un service…',
          allCategories: 'Toutes les catégories',
          submit: 'Rechercher',
          reset: 'Réinitialiser'
        },
        categories: {
          title: 'Popular Services',
          subtitle: 'Discover trending treatments curated by Malva.',
          all: 'All Services'
        },
        search: {
          liveTitle: 'Résultats de recherche',
          resultsTitle: 'Résultats de recherche',
          noServerResults: 'Aucun résultat pour “{{query}}”.',
          noCategory: 'Aucun service dans cette catégorie pour le moment.',
          uncategorized: 'Sans catégorie',
          emptyCatalogue: 'Le catalogue sera disponible bientôt 👍',
          noResults: 'Aucun service trouvé.',
          error: 'Impossible de charger les résultats. Veuillez réessayer.',
          loadFailed: 'Chargement impossible'
        },
        cards: {
          addToCart: 'Ajouter au panier',
          viewDetails: 'View details',
          tagPopular: 'Popular',
          noImage: 'Preview coming soon',
          imageAltFallback: 'Service preview'
        },
        detail: {
          badgeFeatured: 'Signature',
          imageEmpty: 'Preview coming soon',
          unknownCategory: 'Uncategorized',
          descriptionFallback: 'We will publish the description soon.',
          durationLabel: 'Duration',
          categoryLabel: 'Category',
          priceLabel: 'Investment',
          discountLabel: '{{value}}% off today',
          formsLabel: 'Required forms',
          formsEmpty: 'No forms required before the visit.',
          formsSingular: '{{count}} form to complete before arrival.',
          formsPlural: '{{count}} forms to complete before arrival.',
          highlightsTitle: 'What to expect',
          highlightCare: 'Personal concierge care from our front-desk team.',
          highlightProducts: 'Sterile tools and lab-tested professional formulas.',
          highlightPlan: 'Personalized at-home plan after your visit.',
          ctaPrimary: 'Book this service',
          ctaSecondary: 'Back to catalog',
          metaExtraTime: '+{{value}} min prep time',
          imageAlt: 'Preview for {{name}}',
          openLabel: 'View details for {{name}}'
        },
        units: {
          minutes: '{{value}} min'
        },
        modal: {
          title: 'Ajouter un service :',
          masterLabel: 'Praticien',
          chooseTime: 'Choisir un horaire',
          prev: '← Précédent',
          today: 'Aujourd’hui',
          next: 'Suivant →',
          legendFree: 'disponible',
          legendBusy: 'occupé',
          legendHint: 'Faites défiler horizontalement. Les créneaux rouges sont indisponibles.',
          summaryLabel: 'Résumé',
          summaryPlaceholder: 'Choisissez un praticien et un horaire.',
          summarySelected: 'Praticien : {{master}}. Horaire : {{time}}, {{date}}.',
          errorLoad: 'Impossible de récupérer les disponibilités',
          noMasters: 'Aucun praticien disponible',
          noAvailability: 'Aucune disponibilité',
          mobileEmpty: 'No availability yet.',
          mobileDate: 'Date',
          cartPreviewLabel: 'In your cart',
          cartPreviewEmpty: 'Add services to your cart to see them here.',
          cartPreviewUnknownMaster: 'Any master',
          cartPreviewMeta: '{{master}} · {{time}} · {{duration}}',
          cartPreviewTotals: 'Total: {{total}} • {{duration}}',
          cartPreviewFee: '{{fee}} card processing fee (3% + $0.50) included.',
          success: 'Service ajouté au panier.',
          errorAdd: 'Impossible d’ajouter le service au panier',
          errorGeneric: 'Erreur lors de l’ajout au panier',
          inCartShort: 'In cart',
          slotInCart: 'Already in your cart'
        },
        cart: {
          title: 'Panier',
          empty: 'Votre panier est vide.',
          summary: 'Total : {{total}} · {{duration}}',
          processingFeeNotice: '{{fee}} card processing fee (3% + $0.50) is included in the total.',
          discount: 'Discount',
          checkout: 'Valider',
          open: 'Open cart',
          loadFailed: 'Impossible de charger le panier',
          removeSuccess: 'Élément retiré du panier.',
          removeFailed: 'Impossible de retirer l’élément',
          checkoutFailed: 'Impossible de finaliser la réservation',
          finalizeFailed: 'Failed to finalize booking.',
          checkoutSuccess: 'Rendez-vous créé ! Redirection…',
          freeSuccess: 'Appointment booked. No payment required.',
          remove: 'Retirer l’élément'
        },
        userMenu: {
          open: 'Open user menu',
          greeting: 'Welcome back',
          tier: 'Malva Member',
          profile: 'Profile',
          appointments: 'Appointments',
          wallet: 'Wallet',
          favorites: 'Favorites',
          giftCard: 'Send a gift card',
          forms: 'Forms',
          orders: 'Product orders',
          settings: 'Settings',
          language: 'Languages',
          logout: 'Log out',
          download: 'Download the app',
          help: 'Help & support',
          business: 'For businesses'
        },
        dynamic: {
          names: {
            "service-one": 'Service 1',
            "service-two": 'Service 2',
            consultation: 'Consultation'
          }
        },
        footer: {
          copy: '© 2025 Malva Booking'
        },
        header: {
          tagline: 'Studio de beauté et de bien-être',
          sendGift: 'Envoyer une carte cadeau',
          listBusiness: 'Inscrivez votre entreprise',
          openMenu: 'Ouvrir le menu',
          closeMenu: 'Fermer le menu',
          closeMenuText: 'Fermer le menu',
          menuLabel: 'Menu principal',
          calendar: 'Ouvrir les raccourcis du calendrier',
          notifications: 'Notifications',
          openCart: 'Ouvrir le panier'
        },
        payment: {
          amountDueLabel: 'Montant dû',
          feeLabel: 'Frais de traitement de carte',
          optionLabel: 'Option de paiement',
          payInFullLabel: 'Payer intégralement ({{percent}}%)',
          payInFullHint: 'La totalité du solde sera facturée aujourd’hui.',
          payPartialLabel: 'Payez {{percent}} % maintenant',
          payPartialHint: 'Les {{remaining}} restants seront dus plus tard.',
          partialNote: 'Le solde restant sera dû en personne ou plus tard.',
          confirmButton: 'Confirmer la réservation'
        }
      },
      dashboard: {
        meta: {
          title: 'Espace client | Malva Booking'
        },
        nav: {
          overview: 'Tableau de bord',
          appointments: 'Rendez-vous',
          files: 'Fichiers',
          notifications: 'Notifications',
          profile: 'Profil',
          back: 'Retour au site',
          signOut: 'Déconnexion',
          accountMenu: 'Menu du compte',
          overviewHint: 'Informations et actions rapides',
          appointmentsHint: 'À venir et historique',
          billing: 'Facturation et paiements',
          billingHint: 'Portefeuille et détails enregistrés',
          setup: 'Installation',
          formsHint: 'Admission et mises à jour',
          settingsHint: 'Préférences et confidentialité',
          support: 'Soutien',
          supportHint: 'Aide et ressources'
        },
        greetingNamed: 'Bonjour, {{name}} !',
        greetingAnon: 'Bonjour, {{username}} !',
        upcomingTitle: 'Rendez-vous à venir',
        upcomingEmpty: 'Aucun rendez-vous à venir.',
        statsTitle: 'Statistiques',
        chartLabel: 'Rendez-vous',
        recentTitle: 'Derniers rendez-vous',
        recentEmpty: 'Aucun rendez-vous terminé.',
        table: {
          date: 'Date',
          service: 'Service',
          master: 'Praticien',
          status: 'Statut',
          payment: 'Statut de paiement',
          receipt: 'Receipt',
          receiptCta: 'View receipt',
          noReceipt: 'Not available yet'
        },
        myTitle: 'Mes rendez-vous',
        myEmpty: 'Aucun rendez-vous.',
        book: '+ Réserver',
        appointment: {
          cancel: 'Annuler',
          reschedule: 'Reprogrammer',
          completed: 'Terminé',
          paymentStatusLabel: 'Statut de paiement :',
          pending: 'En attente',
          actionsUnavailable: 'Actions indisponibles',
          noItems: 'Aucun service enregistré.',
          noMonth: 'Pas de rendez-vous ce mois-ci.'
        },
        filesTitle: 'Fichiers',
        notificationsTitle: 'Notifications',
        comingSoon: 'Bientôt disponible.',
        profileTitle: 'Profil',
        forms: {
          pending: 'Forms outstanding',
          actionNeeded: 'Action needed: we still need your intake form.',
          complete: 'Complete {{count}} form(s) before your next visit.',
          completeCta: 'Complete now',
          upToDate: 'All required forms are on file.',
          review: 'Need to make changes? Update your answers anytime.',
          reviewCta: 'Review forms'
        },
        form: {
          firstName: 'Prénom',
          lastName: 'Nom',
          phone: 'Téléphone',
          email: 'E-mail',
          birthDate: 'Date de naissance',
          save: 'Enregistrer les modifications',
          name: 'Nom',
          postalCode: 'Code Postal',
          address: 'Adresse',
          firstNamePlaceholder: 'Jeanne',
          lastNamePlaceholder: 'Biche',
          postalPlaceholder: 'T2X1A1',
          addressPlaceholder: '123, rue Principale'
        },
        reschedule: {
          title: 'Reprogrammer le rendez-vous',
          masterLabel: 'Praticien',
          chooseTime: 'Choisir un horaire',
          hint: 'Faites défiler horizontalement. Les créneaux rouges sont indisponibles.',
          prev: '← Précédent',
          today: 'Aujourd’hui',
          current: 'Créneau actuel',
          next: 'Suivant →',
          cancel: 'Annuler',
          save: 'Enregistrer',
          noMasters: 'Aucun praticien disponible',
          noAvailability: 'Aucune disponibilité',
          success: 'Reprogrammé au {{datetime}}',
          failed: 'Échec de la reprogrammation',
          loadFailed: 'Impossible de charger les créneaux',
          errorLoad: 'Impossible de récupérer les disponibilités',
          confirmCancel: 'Annuler ce rendez-vous ?',
          cancelError: 'Erreur d’annulation : {{detail}}',
          mobileEmpty: 'Pas d\'horaires disponibles ce jour là.',
          mobileHint: 'Appuyez sur une date pour voir les heures disponibles.'
        },
        mobile: {
          portalLabel: 'Portail client'
        },
        overview: {
          viewAll: 'Voir tout'
        },
        stats: {
          range: '6 derniers mois'
        },
        appointments: {
          scheduleLabel: 'Calendrier'
        },
        profile: {
          subtitle: 'Mettez à jour vos informations personnelles pour assurer la fluidité des réservations.'
        },
        billing: {
          sectionLabel: 'Portefeuille',
          title: 'Solde et facturation',
          subtitle: 'Stockez vos informations de paiement pour un paiement ultra-rapide.',
          cardTitle: 'Détails de facturation enregistrés sur votre compte',
          cardSubtitle: 'Nous réutilisons ces champs dans les factures et lors du paiement sur chaque appareil.',
          fields: {
            name: 'Nom de facturation',
            city: 'Ville',
            state: 'Province/État',
            country: 'Pays'
          },
          updated: '{{date}} mis à jour',
          notUpdated: 'Pas encore mis à jour.',
          syncDevice: 'Synchroniser cet appareil avec le compte',
          clearDevice: 'Effacer la copie du compte'
        },
        formsTab: {
          title: 'Formulaires et questionnaires',
          subtitle: 'Nous utilisons ces formulaires pour adapter chaque rendez-vous. Mettez-les à jour à tout moment pour garder vos préférences à jour.',
          pending: 'En attente',
          submitted: 'Soumis',
          open: 'Formulaires ouverts'
        },
        settings: {
          accountTitle: 'Profil de compte (copie du serveur)',
          accountSubtitle: 'Ces informations sont conservées en toute sécurité dans votre compte Malva.',
          howHeard: 'Comment entendu',
          marketingConsent: 'Consentement marketing',
          marketingSubscribed: 'Abonné',
          marketingUnsubscribed: 'Non abonné',
          syncProfile: 'Synchroniser le profil avec cet appareil',
          clearProfile: 'Effacer la copie de l\'appareil',
          languageTitle: 'Langue et alertes',
          languageSubtitle: 'Gardez chaque point de contact cohérent en choisissant une langue préférée.',
          languageNote: 'Les modifications s\'appliquent instantanément et se synchronisent sur toutes vos sessions connectées.'
        },
        device: {
          title: 'Remplissage automatique de l\'appareil',
          subtitle: 'Les données de formulaire enregistrées ne quittent jamais ce navigateur. Effacez-le si vous êtes sur un ordinateur partagé.',
          empty: 'Aucune donnée de saisie automatique n\'est encore stockée sur cet appareil.',
          clear: 'Effacer toutes les données de l\'appareil'
        },
        support: {
          conciergeTitle: 'Service de conciergerie',
          conciergeSubtitle: 'Envoyez un message à notre équipe pour obtenir de l\'aide sur la planification, des modifications de compte ou des conseils sur les produits.',
          email: 'E-mail:',
          phone: 'Téléphone:',
          hours: 'Heures:',
          hoursValue: 'Du lundi au vendredi, de 9h à 18h',
          bookAgain: 'Réservez une autre visite',
          updateForms: 'Mettre à jour les formulaires',
          resourcesTitle: 'Ressources et téléchargements',
          resourcesSubtitle: 'Gardez Malva à proximité grâce à notre application et à nos guides de référence rapide.',
          resources: {
            walkthroughs: 'Présentation du compte étape par étape',
            aftercare: 'Recommandations de suivi de votre maître',
            receipts: 'Reçus imprimables et confirmations de réservation'
          },
          helpCenter: 'Visitez le centre d\'aide',
          policiesTitle: 'Politiques et confidentialité',
          policiesSubtitle: 'Transparence totale sur la façon dont nous traitons le consentement, les e-mails marketing et les données stockées.',
          docs: {
            updated: '{{date}} mis à jour',
            viewDetails: 'Afficher les détails',
            emptyIntro: 'Nous préparons une documentation mise à jour.',
            emptyPrompt: 'E-mail',
            emptyOutro: 'si vous avez besoin de quelque chose immédiatement.'
          }
        }
      }
    },
    ar: {
      languages: {
        en: 'الإنجليزية',
        ru: 'الروسية',
        uk: 'الأوكرانية',
        fr: 'الفرنسية',
        ar: 'العربية',
        hi: 'الهندية'
      },
      common: {
        brand: 'Malva Booking',
        language: 'اللغة',
        close: 'إغلاق',
        cancel: 'إلغاء',
        save: 'حفظ',
        saveChanges: 'حفظ التغييرات',
        signOut: 'تسجيل الخروج',
        backHome: 'العودة إلى الرئيسية',
        clientProfile: 'حساب العميل',
        login: 'تسجيل الدخول',
        cart: 'السلة',
        checkout: 'إتمام الحجز',
        addToCart: 'أضف إلى السلة',
        free: 'متاح',
        busy: 'مشغول',
        service: 'الخدمة',
        noTime: 'لا يوجد وقت'
      },
      services: {
        meta: {
          title: 'Malva Booking — الخدمات'
        },
        header: {
          tagline: 'Beauty & Wellness Studio',
          sendGift: 'Send a gift card',
          listBusiness: 'List your business',
          openMenu: 'Open menu',
          closeMenu: 'Close menu',
          closeMenuText: 'Close menu',
          menuLabel: 'Main menu',
          calendar: 'Open calendar shortcuts',
          notifications: 'Notifications',
          openCart: 'Open cart'
        },
        hero: {
          badge: 'Luxury wellness',
          title: 'احجز موعدك خلال خطوتين',
          subtitle: 'اختر الخدمة، الخبير، والوقت — ونحن سنتولى الباقي.',
          description: 'Pick a service, a specialist, and a time — we’ll handle the rest.',
          cta: 'استعراض الخدمات ↓',
          ctaPrimary: 'Book now',
          ctaSecondary: 'Explore categories',
          stats: {
            clients: {
              value: '3.2K+',
              label: 'Happy clients this month'
            },
            specialists: {
              value: '42',
              label: 'Verified specialists online'
            },
            speed: {
              value: '2 clicks',
              label: 'Average booking time'
            }
          }
        },
        nav: {
          cart: 'السلة',
          clientProfile: 'حساب العميل',
          login: 'تسجيل الدخول',
          register: 'Create account'
        },
        section: {
          title: 'الخدمات'
        },
        filters: {
          searchLabel: 'Search service',
          categoryLabel: 'Category',
          searchPlaceholder: 'ابحث عن خدمة…',
          allCategories: 'كل الفئات',
          submit: 'بحث',
          reset: 'إعادة التعيين'
        },
        categories: {
          title: 'Popular Services',
          subtitle: 'Discover trending treatments curated by Malva.',
          all: 'All Services'
        },
        search: {
          liveTitle: 'نتائج البحث',
          resultsTitle: 'نتائج البحث',
          noServerResults: 'لا توجد نتائج لـ “{{query}}”.',
          noCategory: 'لا توجد خدمات في هذه الفئة حتى الآن.',
          uncategorized: 'غير مصنف',
          emptyCatalogue: 'سيكون الدليل متاحاً قريباً 👍',
          noResults: 'لم يتم العثور على خدمات.',
          error: 'تعذر تحميل النتائج. حاول مرة أخرى.',
          loadFailed: 'فشل التحميل'
        },
        cards: {
          addToCart: 'أضف إلى السلة',
          viewDetails: 'View details',
          tagPopular: 'Popular',
          noImage: 'Preview coming soon',
          imageAltFallback: 'Service preview'
        },
        detail: {
          badgeFeatured: 'Signature',
          imageEmpty: 'Preview coming soon',
          unknownCategory: 'Uncategorized',
          descriptionFallback: 'We will publish the description soon.',
          durationLabel: 'Duration',
          categoryLabel: 'Category',
          priceLabel: 'Investment',
          discountLabel: '{{value}}% off today',
          formsLabel: 'Required forms',
          formsEmpty: 'No forms required before the visit.',
          formsSingular: '{{count}} form to complete before arrival.',
          formsPlural: '{{count}} forms to complete before arrival.',
          highlightsTitle: 'What to expect',
          highlightCare: 'Personal concierge care from our front-desk team.',
          highlightProducts: 'Sterile tools and lab-tested professional formulas.',
          highlightPlan: 'Personalized at-home plan after your visit.',
          ctaPrimary: 'Book this service',
          ctaSecondary: 'Back to catalog',
          metaExtraTime: '+{{value}} min prep time',
          imageAlt: 'Preview for {{name}}',
          openLabel: 'View details for {{name}}'
        },
        units: {
          minutes: '{{value}} دقيقة'
        },
        modal: {
          title: 'إضافة خدمة:',
          masterLabel: 'الخبير',
          chooseTime: 'اختر الوقت',
          prev: '← السابق',
          today: 'اليوم',
          next: 'التالي →',
          legendFree: 'متاح',
          legendBusy: 'مشغول',
          legendHint: 'مرّر أفقياً. المربعات الحمراء مشغولة وغير قابلة للنقر.',
          summaryLabel: 'الملخص',
          summaryPlaceholder: 'اختر خبيراً ووقتاً.',
          summarySelected: 'الخبير: {{master}}. الوقت: {{time}}، {{date}}.',
          errorLoad: 'تعذر جلب المواعيد المتاحة',
          noMasters: 'لا يوجد خبراء متاحون',
          noAvailability: 'لا توجد مواعيد متاحة',
          mobileEmpty: 'No availability yet.',
          mobileDate: 'Date',
          cartPreviewLabel: 'In your cart',
          cartPreviewEmpty: 'Add services to your cart to see them here.',
          cartPreviewUnknownMaster: 'Any master',
          cartPreviewMeta: '{{master}} · {{time}} · {{duration}}',
          cartPreviewTotals: 'Total: {{total}} • {{duration}}',
          cartPreviewFee: '{{fee}} card processing fee (3% + $0.50) included.',
          success: 'تمت إضافة الخدمة إلى السلة.',
          errorAdd: 'تعذر إضافة الخدمة إلى السلة',
          errorGeneric: 'خطأ أثناء الإضافة إلى السلة',
          inCartShort: 'In cart',
          slotInCart: 'Already in your cart'
        },
        cart: {
          title: 'السلة',
          empty: 'سلتك فارغة.',
          summary: 'الإجمالي: {{total}} · {{duration}}',
          processingFeeNotice: '{{fee}} card processing fee (3% + $0.50) is included in the total.',
          discount: 'Discount',
          checkout: 'إتمام الحجز',
          open: 'Open cart',
          loadFailed: 'تعذر تحميل السلة',
          removeSuccess: 'تمت إزالة العنصر من السلة.',
          removeFailed: 'تعذر إزالة العنصر',
          checkoutFailed: 'تعذر إتمام الحجز',
          finalizeFailed: 'Failed to finalize booking.',
          checkoutSuccess: 'تم إنشاء الموعد! سيتم تحويلك…',
          freeSuccess: 'Appointment booked. No payment required.',
          remove: 'إزالة العنصر'
        },
        userMenu: {
          open: 'Open user menu',
          greeting: 'Welcome back',
          tier: 'Malva Member',
          profile: 'Profile',
          appointments: 'Appointments',
          wallet: 'Wallet',
          favorites: 'Favorites',
          giftCard: 'Send a gift card',
          forms: 'Forms',
          orders: 'Product orders',
          settings: 'Settings',
          language: 'Languages',
          logout: 'Log out',
          download: 'Download the app',
          help: 'Help & support',
          business: 'For businesses'
        },
        dynamic: {
          names: {
            "service-one": 'الخدمة 1',
            "service-two": 'الخدمة 2',
            consultation: 'استشارة'
          }
        },
        footer: {
          copy: '© 2025 Malva Booking'
        },
        payment: {
          amountDueLabel: 'المبلغ المستحق',
          feeLabel: 'رسوم معالجة البطاقة',
          optionLabel: 'خيار الدفع',
          payInFullLabel: 'الدفع بالكامل ({{percent}}%)',
          payInFullHint: 'سيتم شحن الرصيد بالكامل اليوم.',
          payPartialLabel: 'ادفع {{percent}}% الآن',
          payPartialHint: 'سيتم تسليم {{remaining}} المتبقي لاحقًا.',
          partialNote: 'سيتم سداد الرصيد المتبقي شخصيًا أو لاحقًا.',
          confirmButton: 'تأكيد الحجز'
        }
      },
      dashboard: {
        meta: {
          title: 'منصة العميل | Malva Booking'
        },
        nav: {
          overview: 'نظرة عامة',
          appointments: 'المواعيد',
          files: 'الملفات',
          notifications: 'الإشعارات',
          profile: 'الملف الشخصي',
          back: 'العودة إلى الموقع',
          signOut: 'تسجيل الخروج',
          accountMenu: 'قائمة الحساب',
          overviewHint: 'رؤى وإجراءات سريعة',
          appointmentsHint: 'القادمة والتاريخ',
          billing: 'الفواتير والمدفوعات',
          billingHint: 'المحفظة والتفاصيل المحفوظة',
          setup: 'يثبت',
          formsHint: 'المدخول والتحديثات',
          settingsHint: 'التفضيلات والخصوصية',
          support: 'يدعم',
          supportHint: 'المساعدة والموارد'
        },
        greetingNamed: 'مرحباً، {{name}}!',
        greetingAnon: 'مرحباً، {{username}}!',
        upcomingTitle: 'المواعيد القادمة',
        upcomingEmpty: 'لا توجد مواعيد قادمة.',
        statsTitle: 'الإحصائيات',
        chartLabel: 'المواعيد',
        recentTitle: 'آخر المواعيد',
        recentEmpty: 'لا توجد مواعيد مكتملة بعد.',
        table: {
          date: 'التاريخ',
          service: 'الخدمة',
          master: 'الخبير',
          status: 'الحالة',
          payment: 'حالة الدفع',
          receipt: 'Receipt',
          receiptCta: 'View receipt',
          noReceipt: 'Not available yet'
        },
        myTitle: 'مواعيدي',
        myEmpty: 'لا توجد مواعيد.',
        book: '+ حجز',
        appointment: {
          cancel: 'إلغاء',
          reschedule: 'إعادة الجدولة',
          completed: 'مكتمل',
          paymentStatusLabel: 'حالة الدفع:',
          pending: 'قيد الانتظار',
          actionsUnavailable: 'الإجراءات غير متاحة',
          noItems: 'لم يتم تسجيل أي خدمات.',
          noMonth: 'لا يوجد مواعيد هذا الشهر.'
        },
        filesTitle: 'الملفات',
        notificationsTitle: 'الإشعارات',
        comingSoon: 'قريباً.',
        profileTitle: 'الملف الشخصي',
        forms: {
          pending: 'Forms outstanding',
          actionNeeded: 'Action needed: we still need your intake form.',
          complete: 'Complete {{count}} form(s) before your next visit.',
          completeCta: 'Complete now',
          upToDate: 'All required forms are on file.',
          review: 'Need to make changes? Update your answers anytime.',
          reviewCta: 'Review forms'
        },
        form: {
          firstName: 'الاسم الأول',
          lastName: 'اسم العائلة',
          phone: 'الهاتف',
          email: 'البريد الإلكتروني',
          birthDate: 'تاريخ الميلاد',
          save: 'حفظ التغييرات',
          name: 'اسم',
          postalCode: 'رمز بريدي',
          address: 'عنوان',
          firstNamePlaceholder: 'جين',
          lastNamePlaceholder: 'ظبية',
          postalPlaceholder: 'T2X1A1',
          addressPlaceholder: '123 ش الرئيسي'
        },
        reschedule: {
          title: 'إعادة جدولة الموعد',
          masterLabel: 'الخبير',
          chooseTime: 'اختر الوقت',
          hint: 'مرّر أفقياً. المربعات الحمراء مشغولة.',
          prev: '← السابق',
          today: 'اليوم',
          current: 'الموعد الحالي',
          next: 'التالي →',
          cancel: 'إلغاء',
          save: 'حفظ',
          noMasters: 'لا يوجد خبراء متاحون',
          noAvailability: 'لا توجد مواعيد متاحة',
          success: 'تمت إعادة الجدولة إلى {{datetime}}',
          failed: 'فشلت إعادة الجدولة',
          loadFailed: 'تعذر تحميل المواعيد',
          errorLoad: 'تعذر جلب المواعيد المتاحة',
          confirmCancel: 'هل تريد إلغاء هذا الموعد؟',
          cancelError: 'خطأ أثناء الإلغاء: {{detail}}',
          mobileEmpty: 'لا توجد أوقات متاحة في هذا اليوم.',
          mobileHint: 'اضغط على تاريخ لمعرفة الأوقات المتاحة.'
        },
        mobile: {
          portalLabel: 'بوابة العميل'
        },
        overview: {
          viewAll: 'عرض الكل'
        },
        stats: {
          range: 'آخر 6 أشهر'
        },
        appointments: {
          scheduleLabel: 'جدول'
        },
        profile: {
          subtitle: 'قم بتحديث بياناتك الشخصية للحفاظ على سلاسة الحجوزات.'
        },
        billing: {
          sectionLabel: 'محفظة',
          title: 'الرصيد والفواتير',
          subtitle: 'قم بتخزين تفاصيل الدفع الخاصة بك للدفع بسرعة البرق.',
          cardTitle: 'تم حفظ تفاصيل الفواتير في حسابك',
          cardSubtitle: 'نحن نعيد استخدام هذه الحقول عبر الفواتير والخروج على كل جهاز.',
          fields: {
            name: 'اسم الفواتير',
            city: 'مدينة',
            state: 'المقاطعة / الولاية',
            country: 'دولة'
          },
          updated: 'تم التحديث {{date}}',
          notUpdated: 'لم يتم تحديثه بعد.',
          syncDevice: 'مزامنة هذا الجهاز مع الحساب',
          clearDevice: 'مسح نسخة الحساب'
        },
        formsTab: {
          title: 'النماذج والاستبيانات',
          subtitle: 'نحن نستخدم هذه النماذج لتخصيص كل موعد. قم بتحديثها في أي وقت للحفاظ على تفضيلاتك متجددة.',
          pending: 'قيد الانتظار',
          submitted: 'مُقَدَّم',
          open: 'نماذج مفتوحة'
        },
        settings: {
          accountTitle: 'ملف تعريف الحساب (نسخة الخادم)',
          accountSubtitle: 'هذه التفاصيل موجودة بشكل آمن في حساب Malva الخاص بك.',
          howHeard: 'كيف سمعت',
          marketingConsent: 'موافقة التسويق',
          marketingSubscribed: 'مشترك',
          marketingUnsubscribed: 'غير مشترك',
          syncProfile: 'مزامنة الملف الشخصي مع هذا الجهاز',
          clearProfile: 'مسح نسخة الجهاز',
          languageTitle: 'اللغة والتنبيهات',
          languageSubtitle: 'حافظ على اتساق كل نقطة اتصال من خلال اختيار اللغة المفضلة.',
          languageNote: 'يتم تطبيق التغييرات على الفور وتتم مزامنتها عبر جميع جلسات تسجيل الدخول الخاصة بك.'
        },
        device: {
          title: 'الملء التلقائي للجهاز',
          subtitle: 'بيانات النموذج المحفوظة لا تترك هذا المتصفح أبدًا. امسحها إذا كنت تستخدم جهاز كمبيوتر مشتركًا.',
          empty: 'لم يتم تخزين بيانات الملء التلقائي على هذا الجهاز حتى الآن.',
          clear: 'مسح كافة بيانات الجهاز'
        },
        support: {
          conciergeTitle: 'دعم الكونسيرج',
          conciergeSubtitle: 'أرسل رسالة إلى فريقنا للحصول على المساعدة في الجدولة أو تغييرات الحساب أو إرشادات المنتج.',
          email: 'بريد إلكتروني:',
          phone: 'هاتف:',
          hours: 'ساعات:',
          hoursValue: 'الاثنين - الجمعة، 9 صباحًا - 6 مساءً',
          bookAgain: 'احجز زيارة أخرى',
          updateForms: 'تحديث النماذج',
          resourcesTitle: 'الموارد والتنزيلات',
          resourcesSubtitle: 'أبقِ Malva قريبًا من خلال التطبيق والأدلة المرجعية السريعة.',
          resources: {
            walkthroughs: 'خطوات الحساب خطوة بخطوة',
            aftercare: 'توصيات الرعاية اللاحقة من سيدك',
            receipts: 'إيصالات قابلة للطباعة وتأكيدات الحجز'
          },
          helpCenter: 'قم بزيارة مركز المساعدة',
          policiesTitle: 'السياسات والخصوصية',
          policiesSubtitle: 'الشفافية الكاملة حول كيفية تعاملنا مع الموافقة ورسائل البريد الإلكتروني التسويقية والبيانات المخزنة.',
          docs: {
            updated: 'تم التحديث {{date}}',
            viewDetails: 'عرض التفاصيل',
            emptyIntro: 'نحن نقوم بإعداد الوثائق المحدثة.',
            emptyPrompt: 'بريد إلكتروني',
            emptyOutro: 'إذا كنت بحاجة إلى أي شيء على الفور.'
          }
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

  function stripWrapperChars(value) {
    if (!value) return '';
    let result = String(value).trim();
    while (result.length) {
      if (result.charAt(0) === '\\') {
        result = result.slice(1).trim();
        continue;
      }
      if (result.charAt(result.length - 1) === '\\') {
        result = result.slice(0, -1).trim();
        continue;
      }
      const first = result.charAt(0);
      const last = result.charAt(result.length - 1);
      if (
        (first === '"' && last === '"') ||
        (first === "'" && last === "'") ||
        (first === '`' && last === '`')
      ) {
        result = result.slice(1, -1).trim();
        continue;
      }
      break;
    }
    return result;
  }

  function sanitizeAttrName(name) {
    if (!name) return '';
    const cleaned = stripWrapperChars(name);
    return ATTR_NAME_PATTERN.test(cleaned) ? cleaned : '';
  }

  function sanitizeAttrKey(key) {
    if (key === undefined || key === null) return '';
    return stripWrapperChars(key);
  }

  function parseAttrSpec(spec) {
    if (!spec) return [];
    const normalized = stripWrapperChars(spec);
    try {
      const parsed = JSON.parse(normalized);
      if (parsed && typeof parsed === 'object') {
        return Object.keys(parsed).map(function (attr) {
          const attrName = sanitizeAttrName(attr);
          const keyName = sanitizeAttrKey(parsed[attr]);
          if (!attrName || !keyName) return null;
          return { attr: attrName, key: keyName };
        }).filter(Boolean);
      }
    } catch (err) {
      /* ignore */
    }
    return normalized.split(',').map(function (item) {
      const idx = item.indexOf(':');
      if (idx === -1) return null;
      const attr = sanitizeAttrName(item.slice(0, idx));
      const key = sanitizeAttrKey(item.slice(idx + 1));
      if (!attr || !key) return null;
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
