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
        hero: {
          title: 'सिर्फ 2 क्लिक में अपॉइंटमेंट बुक करें',
          subtitle: 'सेवा, विशेषज्ञ और समय चुनें — बाकी हम सम्भालेंगे।',
          cta: 'सेवाएँ देखें ↓'
        },
        nav: {
          cart: 'कार्ट',
          clientProfile: 'क्लाइंट प्रोफ़ाइल',
          login: 'लॉग इन'
        },
        section: {
          title: 'सेवाएँ'
        },
        filters: {
          searchPlaceholder: 'सेवा खोजें…',
          allCategories: 'सभी श्रेणियाँ',
          submit: 'खोजें',
          reset: 'रीसेट'
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
          addToCart: 'कार्ट में जोड़ें'
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
          success: 'सेवा कार्ट में जोड़ दी गई है।',
          errorAdd: 'सेवा को कार्ट में जोड़ नहीं सके',
          errorGeneric: 'कार्ट में जोड़ने में त्रुटि'
        },
        cart: {
          title: 'कार्ट',
          empty: 'आपका कार्ट खाली है।',
          summary: 'कुल: {{total}} · {{duration}}',
          checkout: 'चेकआउट',
          loadFailed: 'कार्ट लोड नहीं हो सका',
          removeSuccess: 'आइटम कार्ट से हटाया गया।',
          removeFailed: 'आइटम हटाया नहीं जा सका',
          checkoutFailed: 'चेकआउट असफल रहा',
          checkoutSuccess: 'अपॉइंटमेंट बन गया! रीडायरेक्ट किया जा रहा है…',
          remove: 'आइटम हटाएँ'
        },
        dynamic: {
          names: {
            'service-one': 'सेवा 1',
            'service-two': 'सेवा 2',
            'consultation': 'परामर्श'
          }
        },
        footer: {
          copy: '© 2025 Malva Booking'
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
          signOut: 'साइन आउट'
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
          amount: 'राशि'
        },
        myTitle: 'मेरी अपॉइंटमेंट्स',
        myEmpty: 'अपॉइंटमेंट नहीं हैं।',
        book: '+ बुक करें',
        appointment: {
          cancel: 'रद्द करें',
          reschedule: 'पुनर्निर्धारित करें',
          completed: 'पूरा हुआ'
        },
        filesTitle: 'फ़ाइलें',
        notificationsTitle: 'सूचनाएँ',
        comingSoon: 'जल्द उपलब्ध होगा।',
        profileTitle: 'प्रोफ़ाइल',
        form: {
          firstName: 'पहला नाम',
          lastName: 'अंतिम नाम',
          phone: 'फ़ोन',
          email: 'ई-मेल',
          birthDate: 'जन्म तारीख',
          save: 'परिवर्तन सहेजें'
        },
        reschedule: {
          title: 'अपॉइंटमेंट पुनर्निर्धारित करें',
          masterLabel: 'मास्टर',
          chooseTime: 'समय चुनें',
          hint: 'क्षैतिज रूप से स्क्रोल करें। लाल स्लॉट व्यस्त हैं।',
          prev: '← पिछला',
          today: 'आज',
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
          cancelError: 'रद्द करने में त्रुटि: {{detail}}'
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
        hero: {
          title: 'Запишіться за 2 кліки',
          subtitle: 'Обирайте послугу, майстра та час — решту зробимо ми.',
          cta: 'Переглянути послуги ↓'
        },
        nav: {
          cart: 'Кошик',
          clientProfile: 'Кабінет клієнта',
          login: 'Увійти'
        },
        section: {
          title: 'Послуги'
        },
        filters: {
          searchPlaceholder: 'Знайти послугу…',
          allCategories: 'Усі категорії',
          submit: 'Знайти',
          reset: 'Скинути'
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
          addToCart: 'До кошика'
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
          success: 'Послугу додано до кошика.',
          errorAdd: 'Не вдалося додати послугу до кошика',
          errorGeneric: 'Помилка додавання до кошика'
        },
        cart: {
          title: 'Кошик',
          empty: 'Ваш кошик порожній.',
          summary: 'Разом: {{total}} · {{duration}}',
          checkout: 'Оформити',
          loadFailed: 'Не вдалося завантажити кошик',
          removeSuccess: 'Послугу видалено з кошика.',
          removeFailed: 'Не вдалося видалити послугу',
          checkoutFailed: 'Не вдалося оформити запис',
          checkoutSuccess: 'Запис створено! Перенаправляємо…',
          remove: 'Видалити'
        },
        dynamic: {
          names: {
            'service-one': 'Послуга 1',
            'service-two': 'Послуга 2',
            'consultation': 'Консультація'
          }
        },
        footer: {
          copy: '© 2025 Malva Booking'
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
          signOut: 'Вийти'
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
          amount: 'Сума'
        },
        myTitle: 'Мої записи',
        myEmpty: 'Записів немає.',
        book: '+ Записатися',
        appointment: {
          cancel: 'Скасувати',
          reschedule: 'Перенести',
          completed: 'Завершено'
        },
        filesTitle: 'Файли',
        notificationsTitle: 'Сповіщення',
        comingSoon: 'Скоро з’явиться.',
        profileTitle: 'Профіль',
        form: {
          firstName: 'Ім’я',
          lastName: 'Прізвище',
          phone: 'Телефон',
          email: 'E-mail',
          birthDate: 'Дата народження',
          save: 'Зберегти зміни'
        },
        reschedule: {
          title: 'Перенести запис',
          masterLabel: 'Майстер',
          chooseTime: 'Виберіть час',
          hint: 'Прокручуйте горизонтально. Червоні слоти зайняті.',
          prev: '← Назад',
          today: 'Сьогодні',
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
          cancelError: 'Помилка скасування: {{detail}}'
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
          title: 'Réservez votre rendez-vous en 2 clics',
          subtitle: 'Choisissez une prestation, un expert et un horaire — nous nous occupons du reste.',
          cta: 'Voir les services ↓'
        },
        nav: {
          cart: 'Panier',
          clientProfile: 'Espace client',
          login: 'Connexion'
        },
        section: {
          title: 'Services'
        },
        filters: {
          searchPlaceholder: 'Rechercher un service…',
          allCategories: 'Toutes les catégories',
          submit: 'Rechercher',
          reset: 'Réinitialiser'
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
          addToCart: 'Ajouter au panier'
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
          success: 'Service ajouté au panier.',
          errorAdd: 'Impossible d’ajouter le service au panier',
          errorGeneric: 'Erreur lors de l’ajout au panier'
        },
        cart: {
          title: 'Panier',
          empty: 'Votre panier est vide.',
          summary: 'Total : {{total}} · {{duration}}',
          checkout: 'Valider',
          loadFailed: 'Impossible de charger le panier',
          removeSuccess: 'Élément retiré du panier.',
          removeFailed: 'Impossible de retirer l’élément',
          checkoutFailed: 'Impossible de finaliser la réservation',
          checkoutSuccess: 'Rendez-vous créé ! Redirection…',
          remove: 'Retirer l’élément'
        },
        dynamic: {
          names: {
            'service-one': 'Service 1',
            'service-two': 'Service 2',
            'consultation': 'Consultation'
          }
        },
        footer: {
          copy: '© 2025 Malva Booking'
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
          signOut: 'Déconnexion'
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
          amount: 'Montant'
        },
        myTitle: 'Mes rendez-vous',
        myEmpty: 'Aucun rendez-vous.',
        book: '+ Réserver',
        appointment: {
          cancel: 'Annuler',
          reschedule: 'Reprogrammer',
          completed: 'Terminé'
        },
        filesTitle: 'Fichiers',
        notificationsTitle: 'Notifications',
        comingSoon: 'Bientôt disponible.',
        profileTitle: 'Profil',
        form: {
          firstName: 'Prénom',
          lastName: 'Nom',
          phone: 'Téléphone',
          email: 'E-mail',
          birthDate: 'Date de naissance',
          save: 'Enregistrer les modifications'
        },
        reschedule: {
          title: 'Reprogrammer le rendez-vous',
          masterLabel: 'Praticien',
          chooseTime: 'Choisir un horaire',
          hint: 'Faites défiler horizontalement. Les créneaux rouges sont indisponibles.',
          prev: '← Précédent',
          today: 'Aujourd’hui',
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
          cancelError: 'Erreur d’annulation : {{detail}}'
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
        hero: {
          title: 'احجز موعدك خلال خطوتين',
          subtitle: 'اختر الخدمة، الخبير، والوقت — ونحن سنتولى الباقي.',
          cta: 'استعراض الخدمات ↓'
        },
        nav: {
          cart: 'السلة',
          clientProfile: 'حساب العميل',
          login: 'تسجيل الدخول'
        },
        section: {
          title: 'الخدمات'
        },
        filters: {
          searchPlaceholder: 'ابحث عن خدمة…',
          allCategories: 'كل الفئات',
          submit: 'بحث',
          reset: 'إعادة التعيين'
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
          addToCart: 'أضف إلى السلة'
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
          success: 'تمت إضافة الخدمة إلى السلة.',
          errorAdd: 'تعذر إضافة الخدمة إلى السلة',
          errorGeneric: 'خطأ أثناء الإضافة إلى السلة'
        },
        cart: {
          title: 'السلة',
          empty: 'سلتك فارغة.',
          summary: 'الإجمالي: {{total}} · {{duration}}',
          checkout: 'إتمام الحجز',
          loadFailed: 'تعذر تحميل السلة',
          removeSuccess: 'تمت إزالة العنصر من السلة.',
          removeFailed: 'تعذر إزالة العنصر',
          checkoutFailed: 'تعذر إتمام الحجز',
          checkoutSuccess: 'تم إنشاء الموعد! سيتم تحويلك…',
          remove: 'إزالة العنصر'
        },
        dynamic: {
          names: {
            'service-one': 'الخدمة 1',
            'service-two': 'الخدمة 2',
            'consultation': 'استشارة'
          }
        },
        footer: {
          copy: '© 2025 Malva Booking'
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
          signOut: 'تسجيل الخروج'
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
          amount: 'المبلغ'
        },
        myTitle: 'مواعيدي',
        myEmpty: 'لا توجد مواعيد.',
        book: '+ حجز',
        appointment: {
          cancel: 'إلغاء',
          reschedule: 'إعادة الجدولة',
          completed: 'مكتمل'
        },
        filesTitle: 'الملفات',
        notificationsTitle: 'الإشعارات',
        comingSoon: 'قريباً.',
        profileTitle: 'الملف الشخصي',
        form: {
          firstName: 'الاسم الأول',
          lastName: 'اسم العائلة',
          phone: 'الهاتف',
          email: 'البريد الإلكتروني',
          birthDate: 'تاريخ الميلاد',
          save: 'حفظ التغييرات'
        },
        reschedule: {
          title: 'إعادة جدولة الموعد',
          masterLabel: 'الخبير',
          chooseTime: 'اختر الوقت',
          hint: 'مرّر أفقياً. المربعات الحمراء مشغولة.',
          prev: '← السابق',
          today: 'اليوم',
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
          cancelError: 'خطأ أثناء الإلغاء: {{detail}}'
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
