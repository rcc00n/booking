(function () {
    function pad2(n) { return String(n).padStart(2, "0"); }
    function toHHMM(val) {
        if (!val) return "";
        const p = String(val).split(":");
        return pad2(+p[0] || 0) + ":" + pad2(+p[1] || 0);
    }
    function snapToQuarter(hhmm) {
        if (!hhmm) return "";
        const [h, m] = hhmm.split(":").map(v => parseInt(v, 10));
        const candidates = [0, 15, 30, 45];
        let best = 0, diff = 1e9;
        for (const c of candidates) {
            const d = Math.abs(c - (isNaN(m) ? 0 : m));
            if (d < diff) { diff = d; best = c; }
        }
        return pad2(isNaN(h) ? 0 : h) + ":" + pad2(best);
    }

    function buildSelect() {
        const sel = document.createElement("select");
        sel.className = "ab-select js-quarter-picker";
        for (let h = 0; h < 24; h++) {
            for (const m of [0, 15, 30, 45]) {
                const v = pad2(h) + ":" + pad2(m);
                const opt = document.createElement("option");
                opt.value = v;
                opt.textContent = v;
                sel.appendChild(opt);
            }
        }
        return sel;
    }

    function enhanceTimeInput(timeInput) {
        if (!timeInput || timeInput.dataset.enhanced === "1") return;
        timeInput.dataset.enhanced = "1";

        // прячем, но НЕ disabled — иначе не отправится
        timeInput.style.display = "none";

        const sel = buildSelect();
        timeInput.insertAdjacentElement("afterend", sel);

        // ---- ИНИЦИАЛЬНАЯ СИНХРОНИЗАЦИЯ ✅ ----
        // берём текущее значение инпута (если оно было), иначе первый слот селекта
        const current = snapToQuarter(toHHMM(timeInput.value));
        const initial = current && [...sel.options].some(o => o.value === current)
            ? current
            : sel.options[0].value;    // "00:00"
        sel.value = initial;
        timeInput.value = initial;   // ← ключевая строка
        timeInput.dispatchEvent(new Event("input", { bubbles: true }));
        timeInput.dispatchEvent(new Event("change", { bubbles: true }));

        // ---- ДВУСТОРОННЯЯ СВЯЗЬ ----
        sel.addEventListener("change", () => {
            timeInput.value = sel.value;
            timeInput.dispatchEvent(new Event("input", { bubbles: true }));
            timeInput.dispatchEvent(new Event("change", { bubbles: true }));
        });
    }

    function enhanceAll() {
        document.querySelectorAll('input[type="time"]').forEach(enhanceTimeInput);
    }

    // ---- ПЕРЕД САБМИТОМ: форс-синхронизация на всякий случай ✅ ----
    document.addEventListener("submit", (e) => {
        const form = e.target;
        if (!(form instanceof HTMLFormElement)) return;
        form.querySelectorAll("select.js-quarter-picker").forEach(sel => {
            const input = sel.previousElementSibling;
            if (input && input.matches('input[type="time"]') && !input.disabled) {
                input.value = sel.value || input.value || "00:00";
            }
        });
    }, true);

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", enhanceAll);
    } else {
        enhanceAll();
    }
})();
