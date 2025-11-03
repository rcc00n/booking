document.addEventListener("DOMContentLoaded", () => {
  console.log("[Refund Debug][JS] Initializing refund tool");
  const amountInput = document.querySelector("[data-refund-amount-input]");
  const checkboxes = Array.from(document.querySelectorAll("[data-refund-checkbox]"));
  const selectedTotalEl = document.querySelector("[data-selected-total]");

  if (!amountInput) {
    console.log("[Refund Debug][JS] Amount input not found, aborting");
    return;
  }

  const currencySymbol = selectedTotalEl ? selectedTotalEl.dataset.currencySymbol || "" : "";

  let manualOverride = false;
  let lastAutoMinor = 0;

  const parseMinor = (value) => {
    if (!value) {
      return 0;
    }
    const normalized = String(value).replace(/[^0-9.,]/g, "").replace(",", ".");
    const number = Number.parseFloat(normalized);
    if (Number.isNaN(number) || number <= 0) {
      return 0;
    }
    return Math.round(number * 100);
  };

  const formatMinor = (minor) => {
    const value = Number(minor || 0) / 100;
    return value.toFixed(2);
  };

  const updateSelectedDisplay = (minor) => {
    if (!selectedTotalEl) {
      return;
    }
    selectedTotalEl.textContent = `${currencySymbol}${formatMinor(minor)}`;
  };

  const computeSelectionTotal = () =>
    checkboxes.reduce((total, checkbox) => {
      if (!checkbox.checked) {
        return total;
      }
      const amountMinor = Number.parseInt(checkbox.dataset.amountMinor || "0", 10);
      if (Number.isNaN(amountMinor) || amountMinor < 0) {
        return total;
      }
      console.log("[Refund Debug][JS] Including line in selection", {
        id: checkbox.value,
        amountMinor,
        checked: checkbox.checked,
      });
      return total + amountMinor;
    }, 0);

  const syncFromSelection = (force = false) => {
    const totalMinor = computeSelectionTotal();
    console.log("[Refund Debug][JS] syncFromSelection", {
      totalMinor,
      force,
      manualOverride,
    });
    updateSelectedDisplay(totalMinor);
    if (force || !manualOverride) {
      amountInput.value = formatMinor(totalMinor);
      lastAutoMinor = totalMinor;
      manualOverride = false;
    }
  };

  checkboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      console.log("[Refund Debug][JS] Checkbox toggled", {
        id: checkbox.value,
        checked: checkbox.checked,
      });
      syncFromSelection(false);
    });
  });

  amountInput.addEventListener("input", () => {
    const cleaned = amountInput.value.replace(/[^0-9.,]/g, "").replace(",", ".");
    if (cleaned !== amountInput.value) {
      amountInput.value = cleaned;
    }
    manualOverride = true;
    console.log("[Refund Debug][JS] Manual override detected", {
      rawValue: amountInput.value,
    });
  });

  amountInput.addEventListener("blur", () => {
    const currentMinor = parseMinor(amountInput.value);
    amountInput.value = formatMinor(currentMinor);
    lastAutoMinor = currentMinor;
    console.log("[Refund Debug][JS] Amount input blur", {
      currentMinor,
    });
  });

  const initialMinor = parseMinor(amountInput.value);
  if (amountInput.value) {
    amountInput.value = formatMinor(initialMinor);
    manualOverride = initialMinor > 0;
    lastAutoMinor = initialMinor;
    console.log("[Refund Debug][JS] Initial input value", {
      initialMinor,
      manualOverride,
    });
  }

  syncFromSelection(false);
});
