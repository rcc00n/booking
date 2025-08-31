// static/core/admin/appointment_add.js
(function () {
    var $ = (window.django && django.jQuery) ? django.jQuery : window.jQuery;

    function priceInputIdFromServiceSelectId(selectId) {
        // id_items-0-service -> id_items-0-unit_price
        return selectId.replace(/-service$/, "-unit_price");
    }

    async function fetchServicePrice(serviceId) {
        if (!serviceId) return null;
        try {
            // UUID в value — используем конвертер <uuid:pk> (см. urls ниже)
            const resp = await fetch(`/api/service/${serviceId}/price/`, {
                headers: { "X-Requested-With": "XMLHttpRequest" }
            });
            if (!resp.ok) return null;
            const data = await resp.json();
            return (data && data.base_price != null) ? data.base_price : null;
        } catch (e) { return null; }
    }

    async function handleServiceChange(ev) {
        const select = ev.target;
        // Нас интересуют только поля вида items-*-service
        if (!select || !select.name || !/^items-\d+|__prefix__-service$/.test(select.name)) return;

        const priceInputId = priceInputIdFromServiceSelectId(select.id || "");
        const priceInput = document.getElementById(priceInputId);
        if (!priceInput) return;

        const serviceId = select.value;
        if (!serviceId) {
            // Очистили выбор — очистим цену
            priceInput.value = "";
            priceInput.dispatchEvent(new Event("input", { bubbles: true }));
            priceInput.dispatchEvent(new Event("change", { bubbles: true }));
            return;
        }

        const price = await fetchServicePrice(serviceId);
        if (price != null) {
            // Всегда подставляем при выборе сервиса (админ может потом переписать)
            priceInput.value = String(price);
            priceInput.dispatchEvent(new Event("input", { bubbles: true }));
            priceInput.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }

    // Делегированные обработчики — работают и для новых инлайнов:
    $(document).on("change",        'select[name^="items-"][name$="-service"]', handleServiceChange);
    $(document).on("select2:select",'select[name^="items-"][name$="-service"]', handleServiceChange);
    $(document).on("select2:clear", 'select[name^="items-"][name$="-service"]', handleServiceChange);

    // Когда админка добавляет новую строку инлайна
    $(document).on("formset:added", function (_ev, row/*DOM*/, _prefix) {
        // Если Select2 не инициализировался — подкинем инициализацию Jazzmin/Django
        $(row).find('select').trigger('change'); // подхватит автоподстановку, если сервис уже выбран
    });

})();
(function(){
    // Эти переменные уже существуют из основного скрипта:
    // clientEl, itemsSection, container, addRow, recalcGrandTotal, populateServices, ...

    // Забираем initial из Django
    const INITIAL_ITEMS = JSON.parse('{{ items_json|escapejs }}' || '[]');

    // 1) Проставим клиента и покажем секцию позиций
    clientEl.value = "{{ instance.client_id }}";
    if (clientEl.value) {
        itemsSection.classList.remove('ab-hidden');
    }

    // 2) Если есть позиции — очистим контейнер и развернём их
    if (INITIAL_ITEMS.length > 0) {
        container.innerHTML = "";
        document.getElementById('id_items-TOTAL_FORMS').value = 0;

        INITIAL_ITEMS.forEach(function(data){
            addRow();
            const row = container.lastElementChild;

            const masterSel = row.querySelector('.js-master');
            const serviceSel = row.querySelector('.js-service');

            // мастер → сервисы
            masterSel.value = data.master_id;
            masterSel.dispatchEvent(new Event('change')); // заполнит список услуг под мастера

            // сервис
            serviceSel.value = data.service_id;
            serviceSel.dispatchEvent(new Event('change')); // подставит цену/длительность в hint

            // дата/время/цена/промо
            row.querySelector('.js-date').value = data.date || "";
            row.querySelector('.js-time').value = data.time || "";
            if (data.unit_price) row.querySelector('.js-price').value = data.unit_price;
            if (data.promocode)  row.querySelector('.js-promo').value = data.promocode;
        });

        // 3) Пересчёт общей суммы
        recalcGrandTotal();
    }
})();

