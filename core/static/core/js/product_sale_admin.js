(function () {
  "use strict";

  const SCOPE_ATTR = "data-product-sale-form";
  const ROLE_SELECTOR = (role) => `[data-product-sale-role="${role}"]`;

  function ready(fn) {
    if (document.readyState !== "loading") {
      fn();
    } else {
      document.addEventListener("DOMContentLoaded", fn);
    }
  }

  function parseDecimal(value) {
    if (typeof value !== "string") {
      return NaN;
    }
    const normalized = value.replace(/\s+/g, "").replace(",", ".");
    return parseFloat(normalized);
  }

  function findScope(element) {
    return (
      element.closest("[" + SCOPE_ATTR + "]") ||
      element.closest(".inline-related") ||
      element.closest("form") ||
      document
    );
  }

  function findTotalDisplay(scope) {
    return (
      scope.querySelector(ROLE_SELECTOR("total")) ||
      scope.querySelector(".field-total_amount .readonly")
    );
  }

  function formatMoney(number) {
    const formatter = new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return `$${formatter.format(number)}`;
  }

  async function fetchUnitPrice(endpoint, productId) {
    if (!endpoint || !productId) {
      return null;
    }
    const url = new URL(endpoint, window.location.origin);
    url.searchParams.set("product", productId);
    const response = await fetch(url.toString(), {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    if (!response.ok) {
      throw new Error(`Failed to load price (${response.status})`);
    }
    const payload = await response.json();
    if (payload && typeof payload.unit_price === "string") {
      return payload.unit_price;
    }
    return null;
  }

  function enhanceScope(scope) {
    if (!scope || scope.dataset.productSaleEnhanced === "1") {
      return;
    }

    const productField = scope.querySelector(ROLE_SELECTOR("product"));
    const unitPriceInput = scope.querySelector(ROLE_SELECTOR("unit-price"));
    const quantityInput = scope.querySelector(ROLE_SELECTOR("quantity"));
    const totalDisplay = findTotalDisplay(scope);

    if (!productField || !unitPriceInput || !quantityInput || !totalDisplay) {
      scope.dataset.productSaleEnhanced = "1";
      return;
    }

    const priceEndpointValue = productField.dataset.priceEndpoint || window.PRODUCT_SALE_PRICE_ENDPOINT || "";
    productField.dataset.priceEndpoint = priceEndpointValue;
    const priceEndpoint = priceEndpointValue;

    function updateTotal() {
      const quantity = parseDecimal(quantityInput.value);
      const unitPrice = parseDecimal(unitPriceInput.value);
      if (Number.isFinite(quantity) && quantity > 0 && Number.isFinite(unitPrice)) {
        const total = Math.round(quantity * unitPrice * 100) / 100;
        totalDisplay.textContent = formatMoney(total);
      } else {
        totalDisplay.textContent = "$0.00";
      }
    }

    async function syncUnitPrice(force = false) {
      if (!priceEndpoint) {
        return;
      }
      const productId = productField.value;
      if (!productId) {
        return;
      }
      if (!force && unitPriceInput.value && unitPriceInput.value.trim().length) {
        return;
      }
      if (!force && unitPriceInput.dataset.userEdited === "1" && unitPriceInput.value) {
        return;
      }
      try {
        const newPrice = await fetchUnitPrice(priceEndpoint, productId);
        if (newPrice !== null) {
          const previousValue = unitPriceInput.value;
          unitPriceInput.value = newPrice;
          unitPriceInput.dataset.userEdited = "";
          updateTotal();
          if (previousValue !== newPrice) {
            unitPriceInput.dispatchEvent(new Event("input", { bubbles: true }));
            unitPriceInput.dispatchEvent(new Event("change", { bubbles: true }));
          }
        }
      } catch (error) {
        console.warn("Unable to fetch product price", error);
      }
    }

    productField.addEventListener("change", () => syncUnitPrice(true));
    quantityInput.addEventListener("input", updateTotal);
    quantityInput.addEventListener("change", updateTotal);
    unitPriceInput.addEventListener("input", () => {
      unitPriceInput.dataset.userEdited = "1";
      updateTotal();
    });
    unitPriceInput.addEventListener("change", updateTotal);

    syncUnitPrice(false);
    updateTotal();

    scope.dataset.productSaleEnhanced = "1";
  }

  function enhanceAll() {
    document
      .querySelectorAll(ROLE_SELECTOR("product"))
      .forEach((productField) => enhanceScope(findScope(productField)));
  }

  ready(() => {
    enhanceAll();
  });

  document.addEventListener("formset:added", (event) => {
    const target = event.target || event.detail?.form || null;
    if (!target || !(target instanceof HTMLElement)) {
      return;
    }
    const scope = target.matches("[" + SCOPE_ATTR + "]")
      ? target
      : findScope(target);
    if (scope) {
      enhanceScope(scope);
    } else {
      enhanceAll();
    }
  });

  window.ProductSaleForm = {
    enhanceScope,
    enhanceAll,
  };
})();
