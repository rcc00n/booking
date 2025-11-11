(function (window, document) {
  "use strict";

  const STORAGE_PREFIX = "malva:autoFill:";
  const DEFAULT_USER_KEY = "guest";
  const subscribers = new Set();

  const scheduleMap = new WeakMap();
  const memoryStore = new Map();

  let storageStatus = null;

  function storageAvailable() {
    if (storageStatus !== null) {
      return storageStatus;
    }
    try {
      const key = "__malva_autofill_probe__";
      window.localStorage.setItem(key, "1");
      window.localStorage.removeItem(key);
      storageStatus = true;
      return storageStatus;
    } catch (err) {
      console.warn("[Autofill] localStorage is not accessible:", err);
      storageStatus = false;
      return storageStatus;
    }
  }

  function normalizeUserId(userId) {
    if (userId === null || userId === undefined || userId === "") {
      return DEFAULT_USER_KEY;
    }
    return String(userId);
  }

  function resolveUserId(options, form) {
    if (options && options.userId !== undefined) {
      return normalizeUserId(options.userId);
    }
    if (form && form.dataset.autofillUser) {
      return normalizeUserId(form.dataset.autofillUser);
    }
    const body = document.body;
    if (body && body.dataset && body.dataset.autofillUser) {
      return normalizeUserId(body.dataset.autofillUser);
    }
    return DEFAULT_USER_KEY;
  }

  function getKey(userId, group) {
    const safeGroup = group ? String(group).trim() : "";
    if (!safeGroup) {
      throw new Error("[Autofill] group name is required.");
    }
    return STORAGE_PREFIX + normalizeUserId(userId) + ":" + safeGroup;
  }

  function readState(userId, group) {
    const key = getKey(userId, group);
    if (!storageAvailable()) {
      return memoryStore.get(key) || { values: {}, updatedAt: null };
    }
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return { values: {}, updatedAt: null };
    }
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        return {
          values: parsed.values && typeof parsed.values === "object" ? parsed.values : {},
          updatedAt: parsed.updatedAt || null,
        };
      }
    } catch (err) {
      console.warn("[Autofill] Failed to parse stored state:", err);
    }
    return { values: {}, updatedAt: null };
  }

  function writeState(userId, group, values) {
    const key = getKey(userId, group);
    const payload = {
      values: values,
      updatedAt: new Date().toISOString(),
    };
    memoryStore.set(key, payload);
    if (!storageAvailable()) {
      notify(group, userId, payload);
      return;
    }
    try {
      window.localStorage.setItem(key, JSON.stringify(payload));
    } catch (err) {
      console.warn("[Autofill] Unable to persist state:", err);
    }
    notify(group, userId, payload);
  }

  function clearState(userId, group) {
    const key = getKey(userId, group);
    memoryStore.delete(key);
    if (!storageAvailable()) {
      notify(group, userId, { values: {}, updatedAt: null });
      return;
    }
    window.localStorage.removeItem(key);
    notify(group, userId, { values: {}, updatedAt: null });
  }

  function notify(group, userId, state) {
    subscribers.forEach((cb) => {
      try {
        cb({ group, userId, state });
      } catch (err) {
        console.error("[Autofill] subscriber error:", err);
      }
    });
  }

  function schedulePersist(form, userId, group, fields) {
    const persist = () => {
      scheduleMap.delete(form);
      const values = {};
      fields.forEach((field) => {
        const key = field.dataset.autofillKey;
        if (!key) {
          return;
        }
        values[key] = extractFieldValue(field);
      });
      writeState(userId, group, values);
    };
    if (scheduleMap.has(form)) {
      return;
    }
    const timeoutId = window.setTimeout(persist, 250);
    scheduleMap.set(form, timeoutId);
  }

  function extractFieldValue(field) {
    if (!field) {
      return null;
    }
    const tag = field.tagName.toLowerCase();
    if (tag === "input") {
      const type = (field.getAttribute("type") || "text").toLowerCase();
      if (type === "checkbox") {
        return field.checked;
      }
      if (type === "radio") {
        if (field.checked) {
          return field.value;
        }
        return null;
      }
      return field.value;
    }
    if (tag === "select") {
      if (field.multiple) {
        return Array.from(field.selectedOptions || []).map((opt) => opt.value);
      }
      return field.value;
    }
    if (tag === "textarea") {
      return field.value;
    }
    return null;
  }

  function applyFieldValue(field, value) {
    if (value === undefined || value === null) {
      return;
    }
    const tag = field.tagName.toLowerCase();
    if (tag === "input") {
      const type = (field.getAttribute("type") || "text").toLowerCase();
      if (type === "checkbox") {
        field.checked = Boolean(value);
        return;
      }
      if (type === "radio") {
        field.checked = field.value === String(value);
        return;
      }
      if (field.value === "") {
        field.value = value;
      }
      return;
    }
    if (tag === "select") {
      if (field.multiple && Array.isArray(value)) {
        const values = value.map(String);
        Array.from(field.options || []).forEach((opt) => {
          opt.selected = values.includes(opt.value);
        });
      } else if (field.value === "") {
        field.value = value;
      }
      return;
    }
    if (tag === "textarea" && field.value === "") {
      field.value = value;
    }
  }

  function getTrackedFields(form) {
    return Array.from(
      form.querySelectorAll("input[data-autofill-key], select[data-autofill-key], textarea[data-autofill-key]")
    );
  }

  function attach(form, options) {
    if (!form || form.dataset.autofillAttached === "1") {
      return;
    }
    const group = form.dataset.autofillGroup || (options && options.group);
    if (!group) {
      console.warn("[Autofill] Missing data-autofill-group on form", form);
      return;
    }

    const userId = resolveUserId(options || {}, form);
    const fields = getTrackedFields(form);
    const state = readState(userId, group);

    fields.forEach((field) => {
      const key = field.dataset.autofillKey;
      if (!key) {
        return;
      }
      const storedValue = state.values[key];
      if (storedValue !== undefined) {
        applyFieldValue(field, storedValue);
        field.dataset.autofillPopulated = "1";
      }
      const eventName =
        field.tagName.toLowerCase() === "select" || field.type === "checkbox" || field.type === "radio"
          ? "change"
          : "input";
      field.addEventListener(eventName, () => schedulePersist(form, userId, group, fields));
    });

    form.addEventListener("submit", () => {
      const timeoutId = scheduleMap.get(form);
      if (timeoutId) {
        window.clearTimeout(timeoutId);
        scheduleMap.delete(form);
      }
      const values = {};
      fields.forEach((field) => {
        const key = field.dataset.autofillKey;
        if (!key) {
          return;
        }
        values[key] = extractFieldValue(field);
      });
      writeState(userId, group, values);
    });

    form.dataset.autofillAttached = "1";
    notify(group, userId, state);
  }

  function attachAll(selector, options) {
    const forms = document.querySelectorAll(selector);
    forms.forEach((form) => attach(form, options));
  }

  function load(group, options) {
    const userId = resolveUserId(options || {}, null);
    return readState(userId, group);
  }

  function save(group, values, options) {
    const userId = resolveUserId(options || {}, null);
    const normalized = {};
    Object.keys(values || {}).forEach((key) => {
      const value = values[key];
      if (value === undefined) {
        return;
      }
      normalized[key] = value;
    });
    writeState(userId, group, normalized);
  }

  function clear(group, options) {
    const userId = resolveUserId(options || {}, null);
    clearState(userId, group);
  }

  function subscribe(callback) {
    if (typeof callback !== "function") {
      throw new Error("Callback must be a function");
    }
    subscribers.add(callback);
    return () => subscribers.delete(callback);
  }

  const api = {
    version: "1.0.0",
    attach,
    attachAll,
    load,
    save,
    clear,
    subscribe,
    storageAvailable,
  };

  window.MalvaAutofill = api;
})(window, document);
