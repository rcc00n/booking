(function () {
  "use strict";

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

  ready(function () {
    const productField = document.getElementById("id_product");
    const unitPriceInput = document.getElementById("id_unit_price");
    const quantityInput = document.getElementById("id_quantity");
    const totalAmountDisplay = document.querySelector(
      ".field-total_amount .readonly"
    );

    if (!productField || !unitPriceInput || !quantityInput || !totalAmountDisplay) {
      return;
    }

    const priceEndpoint = productField.dataset.priceEndpoint || "";
    const moneyFormatter = new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

    function updateTotalAmount() {
      const quantity = parseDecimal(quantityInput.value);
      const unitPrice = parseDecimal(unitPriceInput.value);
      if (Number.isFinite(quantity) && quantity > 0 && Number.isFinite(unitPrice)) {
        const total = Math.round(quantity * unitPrice * 100) / 100;
        totalAmountDisplay.textContent = moneyFormatter.format(total);
      } else {
        totalAmountDisplay.textContent = "-";
      }
    }

    async function syncUnitPrice() {
      if (!priceEndpoint) {
        return;
      }
      const productId = productField.value;
      if (!productId) {
        return;
      }
      const url = new URL(priceEndpoint, window.location.origin);
      url.searchParams.set("product", productId);
      try {
        const response = await fetch(url.toString(), {
          credentials: "same-origin",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
          },
        });
        if (!response.ok) {
          throw new Error(`Failed to load price (${response.status})`);
        }
        const payload = await response.json();
        if (payload && typeof payload.unit_price === "string") {
          unitPriceInput.value = payload.unit_price;
          unitPriceInput.dataset.userEdited = "";
          updateTotalAmount();
        }
      } catch (error) {
        console.warn("Unable to fetch product price", error);
      }
    }

    productField.addEventListener("change", function () {
      syncUnitPrice();
    });

    quantityInput.addEventListener("input", updateTotalAmount);
    quantityInput.addEventListener("change", updateTotalAmount);
    unitPriceInput.addEventListener("input", function () {
      unitPriceInput.dataset.userEdited = "1";
      updateTotalAmount();
    });
    unitPriceInput.addEventListener("change", updateTotalAmount);

    updateTotalAmount();
  });
})();

