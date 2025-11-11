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
    "en": {
      "languages": {
        "en": "English",
        "ru": "Russian",
        "uk": "Ukrainian",
        "fr": "French",
        "ar": "Arabic",
        "hi": "Hindi"
      },
      "common": {
        "brand": "Malva Booking",
        "language": "Language",
        "close": "Close",
        "cancel": "Cancel",
        "save": "Save",
        "saveChanges": "Save changes",
        "signOut": "Sign out",
        "backHome": "Back to Home",
        "clientProfile": "Client Profile",
        "login": "Login",
        "cart": "Cart",
        "checkout": "Checkout",
        "addToCart": "Add to cart",
        "free": "free",
        "busy": "busy",
        "service": "Service",
        "noTime": "No time"
      },
      "services": {
        "meta": {
          "title": "Malva Booking — Services"
        },
        "header": {
          "tagline": "Beauty & Wellness Studio",
          "sendGift": "Send a gift card",
          "listBusiness": "List your business",
          "openMenu": "Open menu",
          "closeMenu": "Close menu",
          "closeMenuText": "Close menu",
          "menuLabel": "Main menu",
          "calendar": "Open calendar shortcuts",
          "notifications": "Notifications",
          "openCart": "Open cart"
        },
        "hero": {
          "badge": "Luxury wellness",
          "title": "Our Services",
          "subtitle": "Book your appointment in 2 clicks",
          "description": "Pick a service, a specialist, and a time — we’ll handle the rest.",
          "cta": "Browse services ↓",
          "ctaPrimary": "Book now",
          "ctaSecondary": "Explore categories",
          "stats": {
            "clients": {
              "value": "3.2K+",
              "label": "Happy clients this month"
            },
            "specialists": {
              "value": "42",
              "label": "Verified specialists online"
            },
            "speed": {
              "value": "2 clicks",
              "label": "Average booking time"
            }
          }
        },
        "nav": {
          "cart": "Cart",
          "clientProfile": "Client Profile",
          "login": "Login",
          "register": "Create account"
        },
        "section": {
          "title": "Services"
        },
        "filters": {
          "searchLabel": "Search service",
          "categoryLabel": "Category",
          "searchPlaceholder": "Search a service…",
          "allCategories": "All categories",
          "submit": "Search",
          "reset": "Reset"
        },
        "categories": {
          "title": "Popular Services",
          "subtitle": "Discover trending treatments curated by Malva.",
          "all": "All Services"
        },
        "search": {
          "liveTitle": "Search results",
          "resultsTitle": "Search results",
          "noServerResults": "No results for “{{query}}”.",
          "noCategory": "No services in this category yet.",
          "uncategorized": "Uncategorized",
          "emptyCatalogue": "The catalog will be available soon 👍",
          "noResults": "No services found.",
          "error": "Could not load results. Please try again.",
          "loadFailed": "Failed to load"
        },
        "cards": {
          "addToCart": "Add to cart",
          "viewDetails": "View details",
          "tagPopular": "Popular",
          "noImage": "Preview coming soon",
          "imageAltFallback": "Service preview"
        },
        "detail": {
          "badgeFeatured": "Signature",
          "imageEmpty": "Preview coming soon",
          "unknownCategory": "Uncategorized",
          "descriptionFallback": "We will publish the description soon.",
          "durationLabel": "Duration",
          "categoryLabel": "Category",
          "priceLabel": "Investment",
          "discountLabel": "{{value}}% off today",
          "formsLabel": "Required forms",
          "formsEmpty": "No forms required before the visit.",
          "formsSingular": "{{count}} form to complete before arrival.",
          "formsPlural": "{{count}} forms to complete before arrival.",
          "highlightsTitle": "What to expect",
          "highlightCare": "Personal concierge care from our front-desk team.",
          "highlightProducts": "Sterile tools and lab-tested professional formulas.",
          "highlightPlan": "Personalized at-home plan after your visit.",
          "ctaPrimary": "Book this service",
          "ctaSecondary": "Back to catalog",
          "metaExtraTime": "+{{value}} min prep time",
          "imageAlt": "Preview for {{name}}",
          "openLabel": "View details for {{name}}"
        },
        "units": {
          "minutes": "{{value}} min"
        },
        "modal": {
          "title": "Add service:",
          "masterLabel": "Master",
          "chooseTime": "Choose time",
          "prev": "← Prev",
          "today": "Today",
          "next": "Next →",
          "legendFree": "free",
          "legendBusy": "busy",
          "legendHint": "Scroll horizontally. Red slots are busy and not clickable.",
          "summaryLabel": "Summary",
          "summaryPlaceholder": "Pick a master and time.",
          "summarySelected": "Master: {{master}}. Time: {{time}}, {{date}}.",
          "errorLoad": "Unable to fetch availability",
          "noMasters": "No masters available",
          "noAvailability": "No availability",
          "mobileEmpty": "No availability yet.",
          "mobileDate": "Date",
          "cartPreviewLabel": "In your cart",
          "cartPreviewEmpty": "Add services to your cart to see them here.",
          "cartPreviewUnknownMaster": "Any master",
          "cartPreviewMeta": "{{master}} · {{time}} · {{duration}}",
          "cartPreviewTotals": "Total: {{total}} • {{duration}}",
          "cartPreviewFee": "{{fee}} card processing fee (3% + $0.50) included.",
          "success": "Service added to cart.",
          "errorAdd": "Could not add service to cart",
          "errorGeneric": "Add to cart error",
          "inCartShort": "In cart",
          "slotInCart": "Already in your cart"
        },
        "cart": {
          "title": "Cart",
          "empty": "Your cart is empty.",
          "summary": "Total: {{total}} · {{duration}}",
          "processingFeeNotice": "{{fee}} card processing fee (3% + $0.50) is included in the total.",
          "discount": "Discount",
          "checkout": "Checkout",
          "open": "Open cart",
          "loadFailed": "Could not load cart",
          "removeSuccess": "Item removed from cart.",
          "removeFailed": "Failed to remove item",
          "checkoutFailed": "Checkout failed",
          "finalizeFailed": "Failed to finalize booking.",
          "checkoutSuccess": "Appointment created! Redirecting…",
          "freeSuccess": "Appointment booked. No payment required.",
          "remove": "Remove item"
        },
        "payment": {
          "amountDueLabel": "Amount due",
          "feeLabel": "Card processing fee",
          "optionLabel": "Payment option",
          "payInFullLabel": "Pay in full ({{percent}}%)",
          "payInFullHint": "The entire balance will be charged today.",
          "payPartialLabel": "Pay {{percent}}% now",
          "payPartialHint": "Remaining {{remaining}} will be due later.",
          "partialNote": "Remaining balance will be due in person or later.",
          "confirmButton": "Confirm booking"
        },
        "userMenu": {
          "open": "Open user menu",
          "greeting": "Welcome back",
          "tier": "Malva Member",
          "profile": "Profile",
          "appointments": "Appointments",
          "wallet": "Wallet",
          "favorites": "Favorites",
          "giftCard": "Send a gift card",
          "forms": "Forms",
          "orders": "Product orders",
          "settings": "Settings",
          "language": "Languages",
          "logout": "Log out",
          "download": "Download the app",
          "help": "Help & support",
          "business": "For businesses"
        },
        "dynamic": {
          "names": {
            "service-one": "Service One",
            "service-two": "Service Two",
            "consultation": "Consultation"
          }
        },
        "footer": {
          "copy": "© 2025 Malva Booking"
        }
      },
      "dashboard": {
        "meta": {
          "title": "Client Portal | Malva Booking"
        },
        "nav": {
          "overview": "Overview",
          "appointments": "Appointments",
          "files": "Files",
          "notifications": "Notifications",
          "profile": "Profile",
          "back": "Back to Home",
          "signOut": "Sign out"
        },
        "greetingNamed": "Hello, {{name}}!",
        "greetingAnon": "Hello, {{username}}!",
        "upcomingTitle": "Upcoming appointments",
        "upcomingEmpty": "No upcoming appointments.",
        "statsTitle": "Stats",
        "chartLabel": "Appointments",
        "recentTitle": "Recent appointments",
        "recentEmpty": "No completed appointments yet.",
        "table": {
          "date": "Date",
          "service": "Service",
          "master": "Master",
          "status": "Status",
          "payment": "Payment status",
          "receipt": "Receipt",
          "receiptCta": "View receipt",
          "noReceipt": "Not available yet"
        },
        "myTitle": "My appointments",
        "myEmpty": "No appointments.",
        "book": "+ Book",
        "appointment": {
          "cancel": "Cancel",
          "reschedule": "Reschedule",
          "completed": "Completed"
        },
        "filesTitle": "Files",
        "notificationsTitle": "Notifications",
        "comingSoon": "Coming soon.",
        "profileTitle": "Profile",
        "forms": {
          "pending": "Forms outstanding",
          "actionNeeded": "Action needed: we still need your intake form.",
          "complete": "Complete {{count}} form(s) before your next visit.",
          "completeCta": "Complete now",
          "upToDate": "All required forms are on file.",
          "review": "Need to make changes? Update your answers anytime.",
          "reviewCta": "Review forms"
        },
        "form": {
          "firstName": "First name",
          "lastName": "Last name",
          "phone": "Phone",
          "email": "E-mail",
          "birthDate": "Birth date",
          "save": "Save changes"
        },
        "reschedule": {
          "title": "Reschedule appointment",
          "masterLabel": "Master",
          "chooseTime": "Choose time",
          "hint": "Scroll horizontally. Red slots are busy.",
          "prev": "← Prev",
          "today": "Today",
          "current": "Current slot",
          "next": "Next →",
          "cancel": "Cancel",
          "save": "Save",
          "noMasters": "No masters available",
          "noAvailability": "No availability",
          "success": "Rescheduled to {{datetime}}",
          "failed": "Reschedule failed",
          "loadFailed": "Failed to load slots",
          "errorLoad": "Unable to fetch availability",
          "confirmCancel": "Cancel this appointment?",
          "cancelError": "Cancel error: {{detail}}"
        }
      }
    },
    "ru": {
      "languages": {
        "en": "English",
        "ru": "Russian",
        "uk": "Ukrainian",
        "fr": "French",
        "ar": "Arabic",
        "hi": "Hindi"
      },
      "common": {
        "brand": "Malva Booking",
        "language": "Language",
        "close": "Close",
        "cancel": "Cancel",
        "save": "Save",
        "saveChanges": "Save changes",
        "signOut": "Sign out",
        "backHome": "Back to Home",
        "clientProfile": "Client Profile",
        "login": "Login",
        "cart": "Cart",
        "checkout": "Checkout",
        "addToCart": "Add to cart",
        "free": "free",
        "busy": "busy",
        "service": "Service",
        "noTime": "No time"
      },
      "services": {
        "meta": {
          "title": "Malva Booking — Services"
        },
        "header": {
          "tagline": "Beauty & Wellness Studio",
          "sendGift": "Send a gift card",
          "listBusiness": "List your business",
          "openMenu": "Open menu",
          "closeMenu": "Close menu",
          "closeMenuText": "Close menu",
          "menuLabel": "Main menu",
          "calendar": "Open calendar shortcuts",
          "notifications": "Notifications",
          "openCart": "Open cart"
        },
        "hero": {
          "badge": "Luxury wellness",
          "title": "Our Services",
          "subtitle": "Book your appointment in 2 clicks",
          "description": "Pick a service, a specialist, and a time — we’ll handle the rest.",
          "cta": "Browse services ↓",
          "ctaPrimary": "Book now",
          "ctaSecondary": "Explore categories",
          "stats": {
            "clients": {
              "value": "3.2K+",
              "label": "Happy clients this month"
            },
            "specialists": {
              "value": "42",
              "label": "Verified specialists online"
            },
            "speed": {
              "value": "2 clicks",
              "label": "Average booking time"
            }
          }
        },
        "nav": {
          "cart": "Cart",
          "clientProfile": "Client Profile",
          "login": "Login",
          "register": "Create account"
        },
        "section": {
          "title": "Services"
        },
        "filters": {
          "searchLabel": "Search service",
          "categoryLabel": "Category",
          "searchPlaceholder": "Search a service…",
          "allCategories": "All categories",
          "submit": "Search",
          "reset": "Reset"
        },
        "categories": {
          "title": "Popular Services",
          "subtitle": "Discover trending treatments curated by Malva.",
          "all": "All Services"
        },
        "search": {
          "liveTitle": "Search results",
          "resultsTitle": "Search results",
          "noServerResults": "No results for “{{query}}”.",
          "noCategory": "No services in this category yet.",
          "uncategorized": "Uncategorized",
          "emptyCatalogue": "The catalog will be available soon 👍",
          "noResults": "No services found.",
          "error": "Could not load results. Please try again.",
          "loadFailed": "Failed to load"
        },
        "cards": {
          "addToCart": "Add to cart",
          "viewDetails": "View details",
          "tagPopular": "Popular",
          "noImage": "Preview coming soon",
          "imageAltFallback": "Service preview"
        },
        "detail": {
          "badgeFeatured": "Signature",
          "imageEmpty": "Preview coming soon",
          "unknownCategory": "Uncategorized",
          "descriptionFallback": "We will publish the description soon.",
          "durationLabel": "Duration",
          "categoryLabel": "Category",
          "priceLabel": "Investment",
          "discountLabel": "{{value}}% off today",
          "formsLabel": "Required forms",
          "formsEmpty": "No forms required before the visit.",
          "formsSingular": "{{count}} form to complete before arrival.",
          "formsPlural": "{{count}} forms to complete before arrival.",
          "highlightsTitle": "What to expect",
          "highlightCare": "Personal concierge care from our front-desk team.",
          "highlightProducts": "Sterile tools and lab-tested professional formulas.",
          "highlightPlan": "Personalized at-home plan after your visit.",
          "ctaPrimary": "Book this service",
          "ctaSecondary": "Back to catalog",
          "metaExtraTime": "+{{value}} min prep time",
          "imageAlt": "Preview for {{name}}",
          "openLabel": "View details for {{name}}"
        },
        "units": {
          "minutes": "{{value}} min"
        },
        "modal": {
          "title": "Add service:",
          "masterLabel": "Master",
          "chooseTime": "Choose time",
          "prev": "← Prev",
          "today": "Today",
          "next": "Next →",
          "legendFree": "free",
          "legendBusy": "busy",
          "legendHint": "Scroll horizontally. Red slots are busy and not clickable.",
          "summaryLabel": "Summary",
          "summaryPlaceholder": "Pick a master and time.",
          "summarySelected": "Master: {{master}}. Time: {{time}}, {{date}}.",
          "errorLoad": "Unable to fetch availability",
          "noMasters": "No masters available",
          "noAvailability": "No availability",
          "mobileEmpty": "No availability yet.",
          "mobileDate": "Date",
          "cartPreviewLabel": "In your cart",
          "cartPreviewEmpty": "Add services to your cart to see them here.",
          "cartPreviewUnknownMaster": "Any master",
          "cartPreviewMeta": "{{master}} · {{time}} · {{duration}}",
          "cartPreviewTotals": "Total: {{total}} • {{duration}}",
          "cartPreviewFee": "{{fee}} card processing fee (3% + $0.50) included.",
          "success": "Service added to cart.",
          "errorAdd": "Could not add service to cart",
          "errorGeneric": "Add to cart error",
          "inCartShort": "In cart",
          "slotInCart": "Already in your cart"
        },
        "cart": {
          "title": "Cart",
          "empty": "Your cart is empty.",
          "summary": "Total: {{total}} · {{duration}}",
          "processingFeeNotice": "{{fee}} card processing fee (3% + $0.50) is included in the total.",
          "discount": "Discount",
          "checkout": "Checkout",
          "open": "Open cart",
          "loadFailed": "Could not load cart",
          "removeSuccess": "Item removed from cart.",
          "removeFailed": "Failed to remove item",
          "checkoutFailed": "Checkout failed",
          "finalizeFailed": "Failed to finalize booking.",
          "checkoutSuccess": "Appointment created! Redirecting…",
          "freeSuccess": "Appointment booked. No payment required.",
          "remove": "Remove item"
        },
        "payment": {
          "amountDueLabel": "Amount due",
          "feeLabel": "Card processing fee",
          "optionLabel": "Payment option",
          "payInFullLabel": "Pay in full ({{percent}}%)",
          "payInFullHint": "The entire balance will be charged today.",
          "payPartialLabel": "Pay {{percent}}% now",
          "payPartialHint": "Remaining {{remaining}} will be due later.",
          "partialNote": "Remaining balance will be due in person or later.",
          "confirmButton": "Confirm booking"
        },
        "userMenu": {
          "open": "Open user menu",
          "greeting": "Welcome back",
          "tier": "Malva Member",
          "profile": "Profile",
          "appointments": "Appointments",
          "wallet": "Wallet",
          "favorites": "Favorites",
          "giftCard": "Send a gift card",
          "forms": "Forms",
          "orders": "Product orders",
          "settings": "Settings",
          "language": "Languages",
          "logout": "Log out",
          "download": "Download the app",
          "help": "Help & support",
          "business": "For businesses"
        },
        "dynamic": {
          "names": {
            "service-one": "Service One",
            "service-two": "Service Two",
            "consultation": "Consultation"
          }
        },
        "footer": {
          "copy": "© 2025 Malva Booking"
        }
      },
      "dashboard": {
        "meta": {
          "title": "Client Portal | Malva Booking"
        },
        "nav": {
          "overview": "Overview",
          "appointments": "Appointments",
          "files": "Files",
          "notifications": "Notifications",
          "profile": "Profile",
          "back": "Back to Home",
          "signOut": "Sign out"
        },
        "greetingNamed": "Hello, {{name}}!",
        "greetingAnon": "Hello, {{username}}!",
        "upcomingTitle": "Upcoming appointments",
        "upcomingEmpty": "No upcoming appointments.",
        "statsTitle": "Stats",
        "chartLabel": "Appointments",
        "recentTitle": "Recent appointments",
        "recentEmpty": "No completed appointments yet.",
        "table": {
          "date": "Date",
          "service": "Service",
          "master": "Master",
          "status": "Status",
          "payment": "Payment status",
          "receipt": "Receipt",
          "receiptCta": "View receipt",
          "noReceipt": "Not available yet"
        },
        "myTitle": "My appointments",
        "myEmpty": "No appointments.",
        "book": "+ Book",
        "appointment": {
          "cancel": "Cancel",
          "reschedule": "Reschedule",
          "completed": "Completed"
        },
        "filesTitle": "Files",
        "notificationsTitle": "Notifications",
        "comingSoon": "Coming soon.",
        "profileTitle": "Profile",
        "forms": {
          "pending": "Forms outstanding",
          "actionNeeded": "Action needed: we still need your intake form.",
          "complete": "Complete {{count}} form(s) before your next visit.",
          "completeCta": "Complete now",
          "upToDate": "All required forms are on file.",
          "review": "Need to make changes? Update your answers anytime.",
          "reviewCta": "Review forms"
        },
        "form": {
          "firstName": "First name",
          "lastName": "Last name",
          "phone": "Phone",
          "email": "E-mail",
          "birthDate": "Birth date",
          "save": "Save changes"
        },
        "reschedule": {
          "title": "Reschedule appointment",
          "masterLabel": "Master",
          "chooseTime": "Choose time",
          "hint": "Scroll horizontally. Red slots are busy.",
          "prev": "← Prev",
          "today": "Today",
          "current": "Current slot",
          "next": "Next →",
          "cancel": "Cancel",
          "save": "Save",
          "noMasters": "No masters available",
          "noAvailability": "No availability",
          "success": "Rescheduled to {{datetime}}",
          "failed": "Reschedule failed",
          "loadFailed": "Failed to load slots",
          "errorLoad": "Unable to fetch availability",
          "confirmCancel": "Cancel this appointment?",
          "cancelError": "Cancel error: {{detail}}"
        }
      }
    },
    "uk": {
      "languages": {
        "en": "English",
        "ru": "Russian",
        "uk": "Ukrainian",
        "fr": "French",
        "ar": "Arabic",
        "hi": "Hindi"
      },
      "common": {
        "brand": "Malva Booking",
        "language": "Language",
        "close": "Close",
        "cancel": "Cancel",
        "save": "Save",
        "saveChanges": "Save changes",
        "signOut": "Sign out",
        "backHome": "Back to Home",
        "clientProfile": "Client Profile",
        "login": "Login",
        "cart": "Cart",
        "checkout": "Checkout",
        "addToCart": "Add to cart",
        "free": "free",
        "busy": "busy",
        "service": "Service",
        "noTime": "No time"
      },
      "services": {
        "meta": {
          "title": "Malva Booking — Services"
        },
        "header": {
          "tagline": "Beauty & Wellness Studio",
          "sendGift": "Send a gift card",
          "listBusiness": "List your business",
          "openMenu": "Open menu",
          "closeMenu": "Close menu",
          "closeMenuText": "Close menu",
          "menuLabel": "Main menu",
          "calendar": "Open calendar shortcuts",
          "notifications": "Notifications",
          "openCart": "Open cart"
        },
        "hero": {
          "badge": "Luxury wellness",
          "title": "Our Services",
          "subtitle": "Book your appointment in 2 clicks",
          "description": "Pick a service, a specialist, and a time — we’ll handle the rest.",
          "cta": "Browse services ↓",
          "ctaPrimary": "Book now",
          "ctaSecondary": "Explore categories",
          "stats": {
            "clients": {
              "value": "3.2K+",
              "label": "Happy clients this month"
            },
            "specialists": {
              "value": "42",
              "label": "Verified specialists online"
            },
            "speed": {
              "value": "2 clicks",
              "label": "Average booking time"
            }
          }
        },
        "nav": {
          "cart": "Cart",
          "clientProfile": "Client Profile",
          "login": "Login",
          "register": "Create account"
        },
        "section": {
          "title": "Services"
        },
        "filters": {
          "searchLabel": "Search service",
          "categoryLabel": "Category",
          "searchPlaceholder": "Search a service…",
          "allCategories": "All categories",
          "submit": "Search",
          "reset": "Reset"
        },
        "categories": {
          "title": "Popular Services",
          "subtitle": "Discover trending treatments curated by Malva.",
          "all": "All Services"
        },
        "search": {
          "liveTitle": "Search results",
          "resultsTitle": "Search results",
          "noServerResults": "No results for “{{query}}”.",
          "noCategory": "No services in this category yet.",
          "uncategorized": "Uncategorized",
          "emptyCatalogue": "The catalog will be available soon 👍",
          "noResults": "No services found.",
          "error": "Could not load results. Please try again.",
          "loadFailed": "Failed to load"
        },
        "cards": {
          "addToCart": "Add to cart",
          "viewDetails": "View details",
          "tagPopular": "Popular",
          "noImage": "Preview coming soon",
          "imageAltFallback": "Service preview"
        },
        "detail": {
          "badgeFeatured": "Signature",
          "imageEmpty": "Preview coming soon",
          "unknownCategory": "Uncategorized",
          "descriptionFallback": "We will publish the description soon.",
          "durationLabel": "Duration",
          "categoryLabel": "Category",
          "priceLabel": "Investment",
          "discountLabel": "{{value}}% off today",
          "formsLabel": "Required forms",
          "formsEmpty": "No forms required before the visit.",
          "formsSingular": "{{count}} form to complete before arrival.",
          "formsPlural": "{{count}} forms to complete before arrival.",
          "highlightsTitle": "What to expect",
          "highlightCare": "Personal concierge care from our front-desk team.",
          "highlightProducts": "Sterile tools and lab-tested professional formulas.",
          "highlightPlan": "Personalized at-home plan after your visit.",
          "ctaPrimary": "Book this service",
          "ctaSecondary": "Back to catalog",
          "metaExtraTime": "+{{value}} min prep time",
          "imageAlt": "Preview for {{name}}",
          "openLabel": "View details for {{name}}"
        },
        "units": {
          "minutes": "{{value}} min"
        },
        "modal": {
          "title": "Add service:",
          "masterLabel": "Master",
          "chooseTime": "Choose time",
          "prev": "← Prev",
          "today": "Today",
          "next": "Next →",
          "legendFree": "free",
          "legendBusy": "busy",
          "legendHint": "Scroll horizontally. Red slots are busy and not clickable.",
          "summaryLabel": "Summary",
          "summaryPlaceholder": "Pick a master and time.",
          "summarySelected": "Master: {{master}}. Time: {{time}}, {{date}}.",
          "errorLoad": "Unable to fetch availability",
          "noMasters": "No masters available",
          "noAvailability": "No availability",
          "mobileEmpty": "No availability yet.",
          "mobileDate": "Date",
          "cartPreviewLabel": "In your cart",
          "cartPreviewEmpty": "Add services to your cart to see them here.",
          "cartPreviewUnknownMaster": "Any master",
          "cartPreviewMeta": "{{master}} · {{time}} · {{duration}}",
          "cartPreviewTotals": "Total: {{total}} • {{duration}}",
          "cartPreviewFee": "{{fee}} card processing fee (3% + $0.50) included.",
          "success": "Service added to cart.",
          "errorAdd": "Could not add service to cart",
          "errorGeneric": "Add to cart error",
          "inCartShort": "In cart",
          "slotInCart": "Already in your cart"
        },
        "cart": {
          "title": "Cart",
          "empty": "Your cart is empty.",
          "summary": "Total: {{total}} · {{duration}}",
          "processingFeeNotice": "{{fee}} card processing fee (3% + $0.50) is included in the total.",
          "discount": "Discount",
          "checkout": "Checkout",
          "open": "Open cart",
          "loadFailed": "Could not load cart",
          "removeSuccess": "Item removed from cart.",
          "removeFailed": "Failed to remove item",
          "checkoutFailed": "Checkout failed",
          "finalizeFailed": "Failed to finalize booking.",
          "checkoutSuccess": "Appointment created! Redirecting…",
          "freeSuccess": "Appointment booked. No payment required.",
          "remove": "Remove item"
        },
        "payment": {
          "amountDueLabel": "Amount due",
          "feeLabel": "Card processing fee",
          "optionLabel": "Payment option",
          "payInFullLabel": "Pay in full ({{percent}}%)",
          "payInFullHint": "The entire balance will be charged today.",
          "payPartialLabel": "Pay {{percent}}% now",
          "payPartialHint": "Remaining {{remaining}} will be due later.",
          "partialNote": "Remaining balance will be due in person or later.",
          "confirmButton": "Confirm booking"
        },
        "userMenu": {
          "open": "Open user menu",
          "greeting": "Welcome back",
          "tier": "Malva Member",
          "profile": "Profile",
          "appointments": "Appointments",
          "wallet": "Wallet",
          "favorites": "Favorites",
          "giftCard": "Send a gift card",
          "forms": "Forms",
          "orders": "Product orders",
          "settings": "Settings",
          "language": "Languages",
          "logout": "Log out",
          "download": "Download the app",
          "help": "Help & support",
          "business": "For businesses"
        },
        "dynamic": {
          "names": {
            "service-one": "Service One",
            "service-two": "Service Two",
            "consultation": "Consultation"
          }
        },
        "footer": {
          "copy": "© 2025 Malva Booking"
        }
      },
      "dashboard": {
        "meta": {
          "title": "Client Portal | Malva Booking"
        },
        "nav": {
          "overview": "Overview",
          "appointments": "Appointments",
          "files": "Files",
          "notifications": "Notifications",
          "profile": "Profile",
          "back": "Back to Home",
          "signOut": "Sign out"
        },
        "greetingNamed": "Hello, {{name}}!",
        "greetingAnon": "Hello, {{username}}!",
        "upcomingTitle": "Upcoming appointments",
        "upcomingEmpty": "No upcoming appointments.",
        "statsTitle": "Stats",
        "chartLabel": "Appointments",
        "recentTitle": "Recent appointments",
        "recentEmpty": "No completed appointments yet.",
        "table": {
          "date": "Date",
          "service": "Service",
          "master": "Master",
          "status": "Status",
          "payment": "Payment status",
          "receipt": "Receipt",
          "receiptCta": "View receipt",
          "noReceipt": "Not available yet"
        },
        "myTitle": "My appointments",
        "myEmpty": "No appointments.",
        "book": "+ Book",
        "appointment": {
          "cancel": "Cancel",
          "reschedule": "Reschedule",
          "completed": "Completed"
        },
        "filesTitle": "Files",
        "notificationsTitle": "Notifications",
        "comingSoon": "Coming soon.",
        "profileTitle": "Profile",
        "forms": {
          "pending": "Forms outstanding",
          "actionNeeded": "Action needed: we still need your intake form.",
          "complete": "Complete {{count}} form(s) before your next visit.",
          "completeCta": "Complete now",
          "upToDate": "All required forms are on file.",
          "review": "Need to make changes? Update your answers anytime.",
          "reviewCta": "Review forms"
        },
        "form": {
          "firstName": "First name",
          "lastName": "Last name",
          "phone": "Phone",
          "email": "E-mail",
          "birthDate": "Birth date",
          "save": "Save changes"
        },
        "reschedule": {
          "title": "Reschedule appointment",
          "masterLabel": "Master",
          "chooseTime": "Choose time",
          "hint": "Scroll horizontally. Red slots are busy.",
          "prev": "← Prev",
          "today": "Today",
          "current": "Current slot",
          "next": "Next →",
          "cancel": "Cancel",
          "save": "Save",
          "noMasters": "No masters available",
          "noAvailability": "No availability",
          "success": "Rescheduled to {{datetime}}",
          "failed": "Reschedule failed",
          "loadFailed": "Failed to load slots",
          "errorLoad": "Unable to fetch availability",
          "confirmCancel": "Cancel this appointment?",
          "cancelError": "Cancel error: {{detail}}"
        }
      }
    },
    "fr": {
      "languages": {
        "en": "English",
        "ru": "Russian",
        "uk": "Ukrainian",
        "fr": "French",
        "ar": "Arabic",
        "hi": "Hindi"
      },
      "common": {
        "brand": "Malva Booking",
        "language": "Language",
        "close": "Close",
        "cancel": "Cancel",
        "save": "Save",
        "saveChanges": "Save changes",
        "signOut": "Sign out",
        "backHome": "Back to Home",
        "clientProfile": "Client Profile",
        "login": "Login",
        "cart": "Cart",
        "checkout": "Checkout",
        "addToCart": "Add to cart",
        "free": "free",
        "busy": "busy",
        "service": "Service",
        "noTime": "No time"
      },
      "services": {
        "meta": {
          "title": "Malva Booking — Services"
        },
        "header": {
          "tagline": "Beauty & Wellness Studio",
          "sendGift": "Send a gift card",
          "listBusiness": "List your business",
          "openMenu": "Open menu",
          "closeMenu": "Close menu",
          "closeMenuText": "Close menu",
          "menuLabel": "Main menu",
          "calendar": "Open calendar shortcuts",
          "notifications": "Notifications",
          "openCart": "Open cart"
        },
        "hero": {
          "badge": "Luxury wellness",
          "title": "Our Services",
          "subtitle": "Book your appointment in 2 clicks",
          "description": "Pick a service, a specialist, and a time — we’ll handle the rest.",
          "cta": "Browse services ↓",
          "ctaPrimary": "Book now",
          "ctaSecondary": "Explore categories",
          "stats": {
            "clients": {
              "value": "3.2K+",
              "label": "Happy clients this month"
            },
            "specialists": {
              "value": "42",
              "label": "Verified specialists online"
            },
            "speed": {
              "value": "2 clicks",
              "label": "Average booking time"
            }
          }
        },
        "nav": {
          "cart": "Cart",
          "clientProfile": "Client Profile",
          "login": "Login",
          "register": "Create account"
        },
        "section": {
          "title": "Services"
        },
        "filters": {
          "searchLabel": "Search service",
          "categoryLabel": "Category",
          "searchPlaceholder": "Search a service…",
          "allCategories": "All categories",
          "submit": "Search",
          "reset": "Reset"
        },
        "categories": {
          "title": "Popular Services",
          "subtitle": "Discover trending treatments curated by Malva.",
          "all": "All Services"
        },
        "search": {
          "liveTitle": "Search results",
          "resultsTitle": "Search results",
          "noServerResults": "No results for “{{query}}”.",
          "noCategory": "No services in this category yet.",
          "uncategorized": "Uncategorized",
          "emptyCatalogue": "The catalog will be available soon 👍",
          "noResults": "No services found.",
          "error": "Could not load results. Please try again.",
          "loadFailed": "Failed to load"
        },
        "cards": {
          "addToCart": "Add to cart",
          "viewDetails": "View details",
          "tagPopular": "Popular",
          "noImage": "Preview coming soon",
          "imageAltFallback": "Service preview"
        },
        "detail": {
          "badgeFeatured": "Signature",
          "imageEmpty": "Preview coming soon",
          "unknownCategory": "Uncategorized",
          "descriptionFallback": "We will publish the description soon.",
          "durationLabel": "Duration",
          "categoryLabel": "Category",
          "priceLabel": "Investment",
          "discountLabel": "{{value}}% off today",
          "formsLabel": "Required forms",
          "formsEmpty": "No forms required before the visit.",
          "formsSingular": "{{count}} form to complete before arrival.",
          "formsPlural": "{{count}} forms to complete before arrival.",
          "highlightsTitle": "What to expect",
          "highlightCare": "Personal concierge care from our front-desk team.",
          "highlightProducts": "Sterile tools and lab-tested professional formulas.",
          "highlightPlan": "Personalized at-home plan after your visit.",
          "ctaPrimary": "Book this service",
          "ctaSecondary": "Back to catalog",
          "metaExtraTime": "+{{value}} min prep time",
          "imageAlt": "Preview for {{name}}",
          "openLabel": "View details for {{name}}"
        },
        "units": {
          "minutes": "{{value}} min"
        },
        "modal": {
          "title": "Add service:",
          "masterLabel": "Master",
          "chooseTime": "Choose time",
          "prev": "← Prev",
          "today": "Today",
          "next": "Next →",
          "legendFree": "free",
          "legendBusy": "busy",
          "legendHint": "Scroll horizontally. Red slots are busy and not clickable.",
          "summaryLabel": "Summary",
          "summaryPlaceholder": "Pick a master and time.",
          "summarySelected": "Master: {{master}}. Time: {{time}}, {{date}}.",
          "errorLoad": "Unable to fetch availability",
          "noMasters": "No masters available",
          "noAvailability": "No availability",
          "mobileEmpty": "No availability yet.",
          "mobileDate": "Date",
          "cartPreviewLabel": "In your cart",
          "cartPreviewEmpty": "Add services to your cart to see them here.",
          "cartPreviewUnknownMaster": "Any master",
          "cartPreviewMeta": "{{master}} · {{time}} · {{duration}}",
          "cartPreviewTotals": "Total: {{total}} • {{duration}}",
          "cartPreviewFee": "{{fee}} card processing fee (3% + $0.50) included.",
          "success": "Service added to cart.",
          "errorAdd": "Could not add service to cart",
          "errorGeneric": "Add to cart error",
          "inCartShort": "In cart",
          "slotInCart": "Already in your cart"
        },
        "cart": {
          "title": "Cart",
          "empty": "Your cart is empty.",
          "summary": "Total: {{total}} · {{duration}}",
          "processingFeeNotice": "{{fee}} card processing fee (3% + $0.50) is included in the total.",
          "discount": "Discount",
          "checkout": "Checkout",
          "open": "Open cart",
          "loadFailed": "Could not load cart",
          "removeSuccess": "Item removed from cart.",
          "removeFailed": "Failed to remove item",
          "checkoutFailed": "Checkout failed",
          "finalizeFailed": "Failed to finalize booking.",
          "checkoutSuccess": "Appointment created! Redirecting…",
          "freeSuccess": "Appointment booked. No payment required.",
          "remove": "Remove item"
        },
        "payment": {
          "amountDueLabel": "Amount due",
          "feeLabel": "Card processing fee",
          "optionLabel": "Payment option",
          "payInFullLabel": "Pay in full ({{percent}}%)",
          "payInFullHint": "The entire balance will be charged today.",
          "payPartialLabel": "Pay {{percent}}% now",
          "payPartialHint": "Remaining {{remaining}} will be due later.",
          "partialNote": "Remaining balance will be due in person or later.",
          "confirmButton": "Confirm booking"
        },
        "userMenu": {
          "open": "Open user menu",
          "greeting": "Welcome back",
          "tier": "Malva Member",
          "profile": "Profile",
          "appointments": "Appointments",
          "wallet": "Wallet",
          "favorites": "Favorites",
          "giftCard": "Send a gift card",
          "forms": "Forms",
          "orders": "Product orders",
          "settings": "Settings",
          "language": "Languages",
          "logout": "Log out",
          "download": "Download the app",
          "help": "Help & support",
          "business": "For businesses"
        },
        "dynamic": {
          "names": {
            "service-one": "Service One",
            "service-two": "Service Two",
            "consultation": "Consultation"
          }
        },
        "footer": {
          "copy": "© 2025 Malva Booking"
        }
      },
      "dashboard": {
        "meta": {
          "title": "Client Portal | Malva Booking"
        },
        "nav": {
          "overview": "Overview",
          "appointments": "Appointments",
          "files": "Files",
          "notifications": "Notifications",
          "profile": "Profile",
          "back": "Back to Home",
          "signOut": "Sign out"
        },
        "greetingNamed": "Hello, {{name}}!",
        "greetingAnon": "Hello, {{username}}!",
        "upcomingTitle": "Upcoming appointments",
        "upcomingEmpty": "No upcoming appointments.",
        "statsTitle": "Stats",
        "chartLabel": "Appointments",
        "recentTitle": "Recent appointments",
        "recentEmpty": "No completed appointments yet.",
        "table": {
          "date": "Date",
          "service": "Service",
          "master": "Master",
          "status": "Status",
          "payment": "Payment status",
          "receipt": "Receipt",
          "receiptCta": "View receipt",
          "noReceipt": "Not available yet"
        },
        "myTitle": "My appointments",
        "myEmpty": "No appointments.",
        "book": "+ Book",
        "appointment": {
          "cancel": "Cancel",
          "reschedule": "Reschedule",
          "completed": "Completed"
        },
        "filesTitle": "Files",
        "notificationsTitle": "Notifications",
        "comingSoon": "Coming soon.",
        "profileTitle": "Profile",
        "forms": {
          "pending": "Forms outstanding",
          "actionNeeded": "Action needed: we still need your intake form.",
          "complete": "Complete {{count}} form(s) before your next visit.",
          "completeCta": "Complete now",
          "upToDate": "All required forms are on file.",
          "review": "Need to make changes? Update your answers anytime.",
          "reviewCta": "Review forms"
        },
        "form": {
          "firstName": "First name",
          "lastName": "Last name",
          "phone": "Phone",
          "email": "E-mail",
          "birthDate": "Birth date",
          "save": "Save changes"
        },
        "reschedule": {
          "title": "Reschedule appointment",
          "masterLabel": "Master",
          "chooseTime": "Choose time",
          "hint": "Scroll horizontally. Red slots are busy.",
          "prev": "← Prev",
          "today": "Today",
          "current": "Current slot",
          "next": "Next →",
          "cancel": "Cancel",
          "save": "Save",
          "noMasters": "No masters available",
          "noAvailability": "No availability",
          "success": "Rescheduled to {{datetime}}",
          "failed": "Reschedule failed",
          "loadFailed": "Failed to load slots",
          "errorLoad": "Unable to fetch availability",
          "confirmCancel": "Cancel this appointment?",
          "cancelError": "Cancel error: {{detail}}"
        }
      }
    },
    "ar": {
      "languages": {
        "en": "English",
        "ru": "Russian",
        "uk": "Ukrainian",
        "fr": "French",
        "ar": "Arabic",
        "hi": "Hindi"
      },
      "common": {
        "brand": "Malva Booking",
        "language": "Language",
        "close": "Close",
        "cancel": "Cancel",
        "save": "Save",
        "saveChanges": "Save changes",
        "signOut": "Sign out",
        "backHome": "Back to Home",
        "clientProfile": "Client Profile",
        "login": "Login",
        "cart": "Cart",
        "checkout": "Checkout",
        "addToCart": "Add to cart",
        "free": "free",
        "busy": "busy",
        "service": "Service",
        "noTime": "No time"
      },
      "services": {
        "meta": {
          "title": "Malva Booking — Services"
        },
        "header": {
          "tagline": "Beauty & Wellness Studio",
          "sendGift": "Send a gift card",
          "listBusiness": "List your business",
          "openMenu": "Open menu",
          "closeMenu": "Close menu",
          "closeMenuText": "Close menu",
          "menuLabel": "Main menu",
          "calendar": "Open calendar shortcuts",
          "notifications": "Notifications",
          "openCart": "Open cart"
        },
        "hero": {
          "badge": "Luxury wellness",
          "title": "Our Services",
          "subtitle": "Book your appointment in 2 clicks",
          "description": "Pick a service, a specialist, and a time — we’ll handle the rest.",
          "cta": "Browse services ↓",
          "ctaPrimary": "Book now",
          "ctaSecondary": "Explore categories",
          "stats": {
            "clients": {
              "value": "3.2K+",
              "label": "Happy clients this month"
            },
            "specialists": {
              "value": "42",
              "label": "Verified specialists online"
            },
            "speed": {
              "value": "2 clicks",
              "label": "Average booking time"
            }
          }
        },
        "nav": {
          "cart": "Cart",
          "clientProfile": "Client Profile",
          "login": "Login",
          "register": "Create account"
        },
        "section": {
          "title": "Services"
        },
        "filters": {
          "searchLabel": "Search service",
          "categoryLabel": "Category",
          "searchPlaceholder": "Search a service…",
          "allCategories": "All categories",
          "submit": "Search",
          "reset": "Reset"
        },
        "categories": {
          "title": "Popular Services",
          "subtitle": "Discover trending treatments curated by Malva.",
          "all": "All Services"
        },
        "search": {
          "liveTitle": "Search results",
          "resultsTitle": "Search results",
          "noServerResults": "No results for “{{query}}”.",
          "noCategory": "No services in this category yet.",
          "uncategorized": "Uncategorized",
          "emptyCatalogue": "The catalog will be available soon 👍",
          "noResults": "No services found.",
          "error": "Could not load results. Please try again.",
          "loadFailed": "Failed to load"
        },
        "cards": {
          "addToCart": "Add to cart",
          "viewDetails": "View details",
          "tagPopular": "Popular",
          "noImage": "Preview coming soon",
          "imageAltFallback": "Service preview"
        },
        "detail": {
          "badgeFeatured": "Signature",
          "imageEmpty": "Preview coming soon",
          "unknownCategory": "Uncategorized",
          "descriptionFallback": "We will publish the description soon.",
          "durationLabel": "Duration",
          "categoryLabel": "Category",
          "priceLabel": "Investment",
          "discountLabel": "{{value}}% off today",
          "formsLabel": "Required forms",
          "formsEmpty": "No forms required before the visit.",
          "formsSingular": "{{count}} form to complete before arrival.",
          "formsPlural": "{{count}} forms to complete before arrival.",
          "highlightsTitle": "What to expect",
          "highlightCare": "Personal concierge care from our front-desk team.",
          "highlightProducts": "Sterile tools and lab-tested professional formulas.",
          "highlightPlan": "Personalized at-home plan after your visit.",
          "ctaPrimary": "Book this service",
          "ctaSecondary": "Back to catalog",
          "metaExtraTime": "+{{value}} min prep time",
          "imageAlt": "Preview for {{name}}",
          "openLabel": "View details for {{name}}"
        },
        "units": {
          "minutes": "{{value}} min"
        },
        "modal": {
          "title": "Add service:",
          "masterLabel": "Master",
          "chooseTime": "Choose time",
          "prev": "← Prev",
          "today": "Today",
          "next": "Next →",
          "legendFree": "free",
          "legendBusy": "busy",
          "legendHint": "Scroll horizontally. Red slots are busy and not clickable.",
          "summaryLabel": "Summary",
          "summaryPlaceholder": "Pick a master and time.",
          "summarySelected": "Master: {{master}}. Time: {{time}}, {{date}}.",
          "errorLoad": "Unable to fetch availability",
          "noMasters": "No masters available",
          "noAvailability": "No availability",
          "mobileEmpty": "No availability yet.",
          "mobileDate": "Date",
          "cartPreviewLabel": "In your cart",
          "cartPreviewEmpty": "Add services to your cart to see them here.",
          "cartPreviewUnknownMaster": "Any master",
          "cartPreviewMeta": "{{master}} · {{time}} · {{duration}}",
          "cartPreviewTotals": "Total: {{total}} • {{duration}}",
          "cartPreviewFee": "{{fee}} card processing fee (3% + $0.50) included.",
          "success": "Service added to cart.",
          "errorAdd": "Could not add service to cart",
          "errorGeneric": "Add to cart error",
          "inCartShort": "In cart",
          "slotInCart": "Already in your cart"
        },
        "cart": {
          "title": "Cart",
          "empty": "Your cart is empty.",
          "summary": "Total: {{total}} · {{duration}}",
          "processingFeeNotice": "{{fee}} card processing fee (3% + $0.50) is included in the total.",
          "discount": "Discount",
          "checkout": "Checkout",
          "open": "Open cart",
          "loadFailed": "Could not load cart",
          "removeSuccess": "Item removed from cart.",
          "removeFailed": "Failed to remove item",
          "checkoutFailed": "Checkout failed",
          "finalizeFailed": "Failed to finalize booking.",
          "checkoutSuccess": "Appointment created! Redirecting…",
          "freeSuccess": "Appointment booked. No payment required.",
          "remove": "Remove item"
        },
        "payment": {
          "amountDueLabel": "Amount due",
          "feeLabel": "Card processing fee",
          "optionLabel": "Payment option",
          "payInFullLabel": "Pay in full ({{percent}}%)",
          "payInFullHint": "The entire balance will be charged today.",
          "payPartialLabel": "Pay {{percent}}% now",
          "payPartialHint": "Remaining {{remaining}} will be due later.",
          "partialNote": "Remaining balance will be due in person or later.",
          "confirmButton": "Confirm booking"
        },
        "userMenu": {
          "open": "Open user menu",
          "greeting": "Welcome back",
          "tier": "Malva Member",
          "profile": "Profile",
          "appointments": "Appointments",
          "wallet": "Wallet",
          "favorites": "Favorites",
          "giftCard": "Send a gift card",
          "forms": "Forms",
          "orders": "Product orders",
          "settings": "Settings",
          "language": "Languages",
          "logout": "Log out",
          "download": "Download the app",
          "help": "Help & support",
          "business": "For businesses"
        },
        "dynamic": {
          "names": {
            "service-one": "Service One",
            "service-two": "Service Two",
            "consultation": "Consultation"
          }
        },
        "footer": {
          "copy": "© 2025 Malva Booking"
        }
      },
      "dashboard": {
        "meta": {
          "title": "Client Portal | Malva Booking"
        },
        "nav": {
          "overview": "Overview",
          "appointments": "Appointments",
          "files": "Files",
          "notifications": "Notifications",
          "profile": "Profile",
          "back": "Back to Home",
          "signOut": "Sign out"
        },
        "greetingNamed": "Hello, {{name}}!",
        "greetingAnon": "Hello, {{username}}!",
        "upcomingTitle": "Upcoming appointments",
        "upcomingEmpty": "No upcoming appointments.",
        "statsTitle": "Stats",
        "chartLabel": "Appointments",
        "recentTitle": "Recent appointments",
        "recentEmpty": "No completed appointments yet.",
        "table": {
          "date": "Date",
          "service": "Service",
          "master": "Master",
          "status": "Status",
          "payment": "Payment status",
          "receipt": "Receipt",
          "receiptCta": "View receipt",
          "noReceipt": "Not available yet"
        },
        "myTitle": "My appointments",
        "myEmpty": "No appointments.",
        "book": "+ Book",
        "appointment": {
          "cancel": "Cancel",
          "reschedule": "Reschedule",
          "completed": "Completed"
        },
        "filesTitle": "Files",
        "notificationsTitle": "Notifications",
        "comingSoon": "Coming soon.",
        "profileTitle": "Profile",
        "forms": {
          "pending": "Forms outstanding",
          "actionNeeded": "Action needed: we still need your intake form.",
          "complete": "Complete {{count}} form(s) before your next visit.",
          "completeCta": "Complete now",
          "upToDate": "All required forms are on file.",
          "review": "Need to make changes? Update your answers anytime.",
          "reviewCta": "Review forms"
        },
        "form": {
          "firstName": "First name",
          "lastName": "Last name",
          "phone": "Phone",
          "email": "E-mail",
          "birthDate": "Birth date",
          "save": "Save changes"
        },
        "reschedule": {
          "title": "Reschedule appointment",
          "masterLabel": "Master",
          "chooseTime": "Choose time",
          "hint": "Scroll horizontally. Red slots are busy.",
          "prev": "← Prev",
          "today": "Today",
          "current": "Current slot",
          "next": "Next →",
          "cancel": "Cancel",
          "save": "Save",
          "noMasters": "No masters available",
          "noAvailability": "No availability",
          "success": "Rescheduled to {{datetime}}",
          "failed": "Reschedule failed",
          "loadFailed": "Failed to load slots",
          "errorLoad": "Unable to fetch availability",
          "confirmCancel": "Cancel this appointment?",
          "cancelError": "Cancel error: {{detail}}"
        }
      }
    },
    "hi": {
      "languages": {
        "en": "English",
        "ru": "Russian",
        "uk": "Ukrainian",
        "fr": "French",
        "ar": "Arabic",
        "hi": "Hindi"
      },
      "common": {
        "brand": "Malva Booking",
        "language": "Language",
        "close": "Close",
        "cancel": "Cancel",
        "save": "Save",
        "saveChanges": "Save changes",
        "signOut": "Sign out",
        "backHome": "Back to Home",
        "clientProfile": "Client Profile",
        "login": "Login",
        "cart": "Cart",
        "checkout": "Checkout",
        "addToCart": "Add to cart",
        "free": "free",
        "busy": "busy",
        "service": "Service",
        "noTime": "No time"
      },
      "services": {
        "meta": {
          "title": "Malva Booking — Services"
        },
        "header": {
          "tagline": "Beauty & Wellness Studio",
          "sendGift": "Send a gift card",
          "listBusiness": "List your business",
          "openMenu": "Open menu",
          "closeMenu": "Close menu",
          "closeMenuText": "Close menu",
          "menuLabel": "Main menu",
          "calendar": "Open calendar shortcuts",
          "notifications": "Notifications",
          "openCart": "Open cart"
        },
        "hero": {
          "badge": "Luxury wellness",
          "title": "Our Services",
          "subtitle": "Book your appointment in 2 clicks",
          "description": "Pick a service, a specialist, and a time — we’ll handle the rest.",
          "cta": "Browse services ↓",
          "ctaPrimary": "Book now",
          "ctaSecondary": "Explore categories",
          "stats": {
            "clients": {
              "value": "3.2K+",
              "label": "Happy clients this month"
            },
            "specialists": {
              "value": "42",
              "label": "Verified specialists online"
            },
            "speed": {
              "value": "2 clicks",
              "label": "Average booking time"
            }
          }
        },
        "nav": {
          "cart": "Cart",
          "clientProfile": "Client Profile",
          "login": "Login",
          "register": "Create account"
        },
        "section": {
          "title": "Services"
        },
        "filters": {
          "searchLabel": "Search service",
          "categoryLabel": "Category",
          "searchPlaceholder": "Search a service…",
          "allCategories": "All categories",
          "submit": "Search",
          "reset": "Reset"
        },
        "categories": {
          "title": "Popular Services",
          "subtitle": "Discover trending treatments curated by Malva.",
          "all": "All Services"
        },
        "search": {
          "liveTitle": "Search results",
          "resultsTitle": "Search results",
          "noServerResults": "No results for “{{query}}”.",
          "noCategory": "No services in this category yet.",
          "uncategorized": "Uncategorized",
          "emptyCatalogue": "The catalog will be available soon 👍",
          "noResults": "No services found.",
          "error": "Could not load results. Please try again.",
          "loadFailed": "Failed to load"
        },
        "cards": {
          "addToCart": "Add to cart",
          "viewDetails": "View details",
          "tagPopular": "Popular",
          "noImage": "Preview coming soon",
          "imageAltFallback": "Service preview"
        },
        "detail": {
          "badgeFeatured": "Signature",
          "imageEmpty": "Preview coming soon",
          "unknownCategory": "Uncategorized",
          "descriptionFallback": "We will publish the description soon.",
          "durationLabel": "Duration",
          "categoryLabel": "Category",
          "priceLabel": "Investment",
          "discountLabel": "{{value}}% off today",
          "formsLabel": "Required forms",
          "formsEmpty": "No forms required before the visit.",
          "formsSingular": "{{count}} form to complete before arrival.",
          "formsPlural": "{{count}} forms to complete before arrival.",
          "highlightsTitle": "What to expect",
          "highlightCare": "Personal concierge care from our front-desk team.",
          "highlightProducts": "Sterile tools and lab-tested professional formulas.",
          "highlightPlan": "Personalized at-home plan after your visit.",
          "ctaPrimary": "Book this service",
          "ctaSecondary": "Back to catalog",
          "metaExtraTime": "+{{value}} min prep time",
          "imageAlt": "Preview for {{name}}",
          "openLabel": "View details for {{name}}"
        },
        "units": {
          "minutes": "{{value}} min"
        },
        "modal": {
          "title": "Add service:",
          "masterLabel": "Master",
          "chooseTime": "Choose time",
          "prev": "← Prev",
          "today": "Today",
          "next": "Next →",
          "legendFree": "free",
          "legendBusy": "busy",
          "legendHint": "Scroll horizontally. Red slots are busy and not clickable.",
          "summaryLabel": "Summary",
          "summaryPlaceholder": "Pick a master and time.",
          "summarySelected": "Master: {{master}}. Time: {{time}}, {{date}}.",
          "errorLoad": "Unable to fetch availability",
          "noMasters": "No masters available",
          "noAvailability": "No availability",
          "mobileEmpty": "No availability yet.",
          "mobileDate": "Date",
          "cartPreviewLabel": "In your cart",
          "cartPreviewEmpty": "Add services to your cart to see them here.",
          "cartPreviewUnknownMaster": "Any master",
          "cartPreviewMeta": "{{master}} · {{time}} · {{duration}}",
          "cartPreviewTotals": "Total: {{total}} • {{duration}}",
          "cartPreviewFee": "{{fee}} card processing fee (3% + $0.50) included.",
          "success": "Service added to cart.",
          "errorAdd": "Could not add service to cart",
          "errorGeneric": "Add to cart error",
          "inCartShort": "In cart",
          "slotInCart": "Already in your cart"
        },
        "cart": {
          "title": "Cart",
          "empty": "Your cart is empty.",
          "summary": "Total: {{total}} · {{duration}}",
          "processingFeeNotice": "{{fee}} card processing fee (3% + $0.50) is included in the total.",
          "discount": "Discount",
          "checkout": "Checkout",
          "open": "Open cart",
          "loadFailed": "Could not load cart",
          "removeSuccess": "Item removed from cart.",
          "removeFailed": "Failed to remove item",
          "checkoutFailed": "Checkout failed",
          "finalizeFailed": "Failed to finalize booking.",
          "checkoutSuccess": "Appointment created! Redirecting…",
          "freeSuccess": "Appointment booked. No payment required.",
          "remove": "Remove item"
        },
        "payment": {
          "amountDueLabel": "Amount due",
          "feeLabel": "Card processing fee",
          "optionLabel": "Payment option",
          "payInFullLabel": "Pay in full ({{percent}}%)",
          "payInFullHint": "The entire balance will be charged today.",
          "payPartialLabel": "Pay {{percent}}% now",
          "payPartialHint": "Remaining {{remaining}} will be due later.",
          "partialNote": "Remaining balance will be due in person or later.",
          "confirmButton": "Confirm booking"
        },
        "userMenu": {
          "open": "Open user menu",
          "greeting": "Welcome back",
          "tier": "Malva Member",
          "profile": "Profile",
          "appointments": "Appointments",
          "wallet": "Wallet",
          "favorites": "Favorites",
          "giftCard": "Send a gift card",
          "forms": "Forms",
          "orders": "Product orders",
          "settings": "Settings",
          "language": "Languages",
          "logout": "Log out",
          "download": "Download the app",
          "help": "Help & support",
          "business": "For businesses"
        },
        "dynamic": {
          "names": {
            "service-one": "Service One",
            "service-two": "Service Two",
            "consultation": "Consultation"
          }
        },
        "footer": {
          "copy": "© 2025 Malva Booking"
        }
      },
      "dashboard": {
        "meta": {
          "title": "Client Portal | Malva Booking"
        },
        "nav": {
          "overview": "Overview",
          "appointments": "Appointments",
          "files": "Files",
          "notifications": "Notifications",
          "profile": "Profile",
          "back": "Back to Home",
          "signOut": "Sign out"
        },
        "greetingNamed": "Hello, {{name}}!",
        "greetingAnon": "Hello, {{username}}!",
        "upcomingTitle": "Upcoming appointments",
        "upcomingEmpty": "No upcoming appointments.",
        "statsTitle": "Stats",
        "chartLabel": "Appointments",
        "recentTitle": "Recent appointments",
        "recentEmpty": "No completed appointments yet.",
        "table": {
          "date": "Date",
          "service": "Service",
          "master": "Master",
          "status": "Status",
          "payment": "Payment status",
          "receipt": "Receipt",
          "receiptCta": "View receipt",
          "noReceipt": "Not available yet"
        },
        "myTitle": "My appointments",
        "myEmpty": "No appointments.",
        "book": "+ Book",
        "appointment": {
          "cancel": "Cancel",
          "reschedule": "Reschedule",
          "completed": "Completed"
        },
        "filesTitle": "Files",
        "notificationsTitle": "Notifications",
        "comingSoon": "Coming soon.",
        "profileTitle": "Profile",
        "forms": {
          "pending": "Forms outstanding",
          "actionNeeded": "Action needed: we still need your intake form.",
          "complete": "Complete {{count}} form(s) before your next visit.",
          "completeCta": "Complete now",
          "upToDate": "All required forms are on file.",
          "review": "Need to make changes? Update your answers anytime.",
          "reviewCta": "Review forms"
        },
        "form": {
          "firstName": "First name",
          "lastName": "Last name",
          "phone": "Phone",
          "email": "E-mail",
          "birthDate": "Birth date",
          "save": "Save changes"
        },
        "reschedule": {
          "title": "Reschedule appointment",
          "masterLabel": "Master",
          "chooseTime": "Choose time",
          "hint": "Scroll horizontally. Red slots are busy.",
          "prev": "← Prev",
          "today": "Today",
          "current": "Current slot",
          "next": "Next →",
          "cancel": "Cancel",
          "save": "Save",
          "noMasters": "No masters available",
          "noAvailability": "No availability",
          "success": "Rescheduled to {{datetime}}",
          "failed": "Reschedule failed",
          "loadFailed": "Failed to load slots",
          "errorLoad": "Unable to fetch availability",
          "confirmCancel": "Cancel this appointment?",
          "cancelError": "Cancel error: {{detail}}"
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
