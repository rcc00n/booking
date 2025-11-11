(function () {
    function initDatePickers(root) {
        // Django SplitDateTimeWidget даёт date-инпутам type="date"
        const dateInputs = (root || document).querySelectorAll('input[type="date"]');

        dateInputs.forEach((inp) => {
            // Не пересоздаём
            if (inp.dataset.fpBound === "1") return;

            // Сохраняем текущее значение (если оно есть) — flatpickr его подхватит
            const defaultDate = inp.value || null;

            flatpickr(inp, {
                dateFormat: "Y-m-d",         // что уходит на сервер
                altInput: true,
                altFormat: "D, d M Y",       // красиво для пользователя
                allowInput: false,
                disableMobile: true,         // на мобиле тоже наш вид
                weekNumbers: true,
                defaultDate: defaultDate,
            });

            inp.dataset.fpBound = "1";
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => initDatePickers(document));
    } else {
        initDatePickers(document);
    }

    // На всякий: если админка/инлайн подмонтируют поля позднее
    document.addEventListener("formset:added", (e) => initDatePickers(e.target || document));
})();
