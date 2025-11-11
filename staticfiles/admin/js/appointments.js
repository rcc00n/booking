function getLocalDateString(date = new Date()) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function changeDateToToday() {
    const today = getLocalDateString();
    document.getElementById('realDateInput').value = today;
    onDateChange(today);
}

function changeDateByDays(days) {
    const input = document.getElementById('realDateInput');

    // Преобразуем вручную в YYYY-MM-DD → локальная дата
    const [year, month, day] = input.value.split('-').map(Number);
    const currentDate = new Date(year, month - 1, day); // ← важно: месяц от 0
    currentDate.setHours(12);  // 👈 Устанавливаем безопасное время (чтобы избежать смещений при DST)

    // Меняем дату
    currentDate.setDate(currentDate.getDate() + days);

    const newDate = getLocalDateString(currentDate);
    input.value = newDate;

    onDateChange(newDate);
}

function getCsrfToken() {
    const match = document.cookie.match(/(?:^|;)\s*csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
}

function onDateChange(value) {
    const display = document.getElementById("displayDate");
    display.textContent = value;

    const formData = new FormData(document.getElementById("filterForm"));
    formData.append("action", "calendar");
    formData.set("date", value);  // заменяем дату

    const params = new URLSearchParams(formData).toString();

    fetch(`/admin/core/appointment/?${params}`, {
        credentials: 'same-origin',
        headers: { 'x-requested-with': 'XMLHttpRequest' }
    })
        .then(res => res.json())
        .then(data => {
            document.getElementById("calendar-container").innerHTML = data.html;
            attachTooltipHandlers();
        });
}


const sidebar = document.getElementById("filterSidebar");
const filterBtn = document.getElementById("nav-icon2");
const filterForm = document.getElementById("filterForm");

filterBtn.addEventListener("click", () => {

    sidebar.classList.remove("hidden");
    setTimeout(() => sidebar.classList.add("visible"), 200);
});
function closeSidebar() {
    sidebar.classList.remove("visible");
    setTimeout(() => sidebar.classList.add("hidden"), 350);
}

function toggleSection(el) {
    const content = el.nextElementSibling;
    content.style.display = content.style.display === 'block' ? 'none' : 'block';
}

function clearAllFilters() {
    // Сброс чекбоксов
    document.querySelectorAll('#filterForm input[type="checkbox"]').forEach(cb => cb.checked = false);
    // Сброс селектов
    document.querySelectorAll('#filterForm select').forEach(sel => sel.value = "");
}

// Преобразуем несколько чекбоксов в один параметр запроса: ?status=1&status=2
filterForm.addEventListener("submit", function (e) {
    e.preventDefault();

    const formData = new FormData(filterForm);
    formData.append("action", "filter");
    const selectedDate = document.getElementById("realDateInput").value;
    formData.append("date", selectedDate);
    const params = new URLSearchParams(formData).toString();
    console.log(params);
    fetch(`?${params}`, {
        credentials: 'same-origin',
        headers: {
            "X-Requested-With": "XMLHttpRequest"
        }
    })
        .then(res => res.json())
        .then(data => {
            document.getElementById("calendar-container").innerHTML = data.html;
            attachTooltipHandlers();
            closeSidebar();
        })
        .catch(err => {
            console.error("Error loading appointments:", err);
        });
});
let popup = document.getElementById("addPopup");
let popupTime = document.getElementById("popupTime");


let lastActiveCell = null;

function showAddPopup(event, time, label) {
    closePopup();

    const cell = event.currentTarget;
    cell.innerHTML = `<span class="cell-label">${label}</span>`;
    const rect = cell.getBoundingClientRect();
    const masterId = cell.dataset.master;
    cell.value = time;
    // Обновить текст времени
    const popupTimeEl = document.getElementById("popupTime");
    popupTimeEl.textContent = label;

    lastActiveCell = cell;
    cell.classList.add("active");

    // Заполняем тело popup-а новыми действиями
    const popupBody = popup.querySelector(".popup-body");
    popupBody.innerHTML = `
        <div class="popup-action" onclick="handleAdd('appointment', '${time}', '${masterId}')">📅 Add appointment</div>
        <div class="popup-action" onclick="handleAdd('vacation', '${time}', '${masterId}')">🗓️ Add time off</div>
    `;

    if ((rect.left + window.scrollX - 230) < 0 || rect.width < 100) {
        // либо слишком близко к левому краю, либо слишком узкая ячейка
        popup.style.left = `${rect.left + window.scrollX + rect.width + 10}px`;
    } else {
        popup.style.left = `${rect.left + window.scrollX - rect.width/2.5}px`;
    }
    popup.style.top = `${rect.top + window.scrollY - 40}px`;


    popup.classList.remove("hidden");
}

function closePopup() {
    popup.classList.add("hidden");

    // Сбросить активную ячейку
    if (lastActiveCell) {
        lastActiveCell.classList.remove("active");
        lastActiveCell.innerHTML = ``;
        lastActiveCell = null;
    }
}

document.addEventListener("click", function (e) {
    if (!popup.contains(e.target) && !e.target.classList.contains("calendar-cell")) {
        closePopup();
    }
});

const tooltip = document.getElementById("apptTooltip");

function parseCurrencyValue(raw) {
    if (raw === undefined || raw === null || raw === "") {
        return null;
    }
    const numeric = parseFloat(String(raw).replace(/[^0-9.\-]+/g, ""));
    return Number.isNaN(numeric) ? null : numeric;
}

function formatCurrencyValue(amount) {
    if (amount === null || amount === undefined || Number.isNaN(amount)) {
        return "";
    }
    return `$${amount.toFixed(2)}`;
}

function attachTooltipHandlers() {
    document.querySelectorAll(".event").forEach(box => {
        box.addEventListener("mouseenter", function () {
            showTooltip(box);
        });
        box.addEventListener("mouseleave", function () {
            hideTooltip();
        });
    });
    document.querySelectorAll(".unavailable-cell").forEach(cell => {
        cell.addEventListener("click", () => {
            const id = cell.dataset.id;
            if (id) {
                window.location.href = `/admin/core/masteravailability/${id}/change/`;
            }
        });
    });
    document.querySelectorAll(".unavailable-cell").forEach(cell => {
        cell.addEventListener("mouseenter", () => showUnavailableTooltip(cell));
        cell.addEventListener("mouseleave", () => hideTooltip());
    });
}

attachTooltipHandlers();


function showTooltip(box) {
    const rect = box.getBoundingClientRect();
    const client = box.dataset.client || "";
    const phone = box.dataset.phone || "";
    const service = box.dataset.service || "";
    const time = box.dataset.timeLabel || "";
    const status = box.dataset.status || "";
    const duration = box.dataset.duration || "";
    const price = box.dataset.price || "";
    const final = box.dataset.final || "";
    const master = box.dataset.master || "";
    const editUrl = box.dataset.editUrl || "";
    const statusUrl = box.dataset.statusUrl || "";
    const rescheduleUrl = box.dataset.rescheduleUrl || "";

    const firstLetter = client.trim().charAt(0).toUpperCase();
    const baseRawValue = parseCurrencyValue(box.dataset.baseRaw);
    const finalRawSource = box.dataset.finalRaw;
    const finalRawValue = parseCurrencyValue(
        finalRawSource !== undefined && finalRawSource !== null && finalRawSource !== "" ? finalRawSource : final
    );
    const serviceTotalValueRaw = parseCurrencyValue(box.dataset.serviceTotal);
    const productTotalValueRaw = parseCurrencyValue(box.dataset.productTotal);
    const hasDiscount = box.dataset.hasDiscount === "true";
    const hasProducts = productTotalValueRaw !== null && productTotalValueRaw > 0.009;

    const priceDisplay = price || (baseRawValue !== null ? formatCurrencyValue(baseRawValue) : "");
    const finalDisplay = final || (finalRawValue !== null ? formatCurrencyValue(finalRawValue) : "");

    let serviceDisplayValue = serviceTotalValueRaw;
    if (serviceDisplayValue === null) {
        if (finalRawValue !== null && productTotalValueRaw !== null) {
            serviceDisplayValue = Number((finalRawValue - productTotalValueRaw).toFixed(2));
        } else {
            serviceDisplayValue = finalRawValue;
        }
    }
    const serviceDisplay = serviceDisplayValue !== null ? formatCurrencyValue(serviceDisplayValue) : "";
    const productDisplay = productTotalValueRaw !== null ? formatCurrencyValue(productTotalValueRaw) : "";

    const priceLines = [];
    const hasBasePrice = baseRawValue !== null && baseRawValue > 0.009;
    const serviceLineValue = serviceDisplay || (!hasProducts ? finalDisplay || priceDisplay : "");
    if (serviceLineValue) {
        priceLines.push({
            label: (hasProducts || hasDiscount) ? "Service" : "Total",
            current: serviceLineValue,
            original: hasDiscount && hasBasePrice ? formatCurrencyValue(baseRawValue) : null
        });
    }
    if (hasProducts && productDisplay) {
        priceLines.push({
            label: "Products",
            current: productDisplay,
            original: null
        });
    }
    if (hasProducts && finalDisplay) {
        priceLines.push({
            label: "Total",
            current: finalDisplay,
            original: null
        });
    }
    if (!priceLines.length && finalDisplay) {
        priceLines.push({
            label: "Total",
            current: finalDisplay,
            original: hasDiscount && hasBasePrice ? formatCurrencyValue(baseRawValue) : null
        });
    }

    const priceLinesHtml = priceLines.map(line => {
        const labelHtml = `<span class="tooltip-price-label">${line.label}</span>`;
        const originalHtml = line.original ? `<span class="tooltip-price-old">${line.original}</span>` : "";
        const arrowHtml = line.original ? `<span class="tooltip-price-arrow">→</span>` : "";
        const currentHtml = line.current ? `<span class="tooltip-price-current">${line.current}</span>` : "";
        return `<div class="tooltip-price-line">${labelHtml}<span class="tooltip-price-value">${originalHtml}${arrowHtml}${currentHtml}</span></div>`;
    }).join("");

    const priceBlockHtml = priceLinesHtml ? `<div class="tooltip-price-block">${priceLinesHtml}</div>` : "";

    const actionsHtml = "";

    tooltip.innerHTML = `
        <div class="tooltip-card">
            <div class="tooltip-header">
                <span>${time}</span>
                <span>${status}</span>
            </div>
            <div class="tooltip-body">
                <div class="tooltip-client">
                    <div class="tooltip-avatar">${firstLetter}</div>
                    <div class="tooltip-client-info">
                        <div class="tooltip-client-name">${client}</div>
                        <div class="tooltip-client-phone">${phone}</div>
                    </div>
                </div>
                <div class="tooltip-footer-row">
                    <div class="tooltip-details">
                        ${service ? `<div class="tooltip-service-name">${service}</div>` : ""}
                        <div class="tooltip-meta">${master} | ${duration}</div>
                    </div>
                    ${priceBlockHtml}
                </div>
                ${actionsHtml}
            </div>
        </div>
    `;

    const tooltipWidth = 375;
    const tooltipCardEl = tooltip.querySelector(".tooltip-card");
    const tooltipHeight = tooltipCardEl ? tooltipCardEl.offsetHeight : 210;

    let top = rect.top + window.scrollY;
    let left = rect.left + window.scrollX - tooltipWidth - 10;

    if (top + tooltipHeight > window.scrollY + window.innerHeight) {
        top = window.scrollY + window.innerHeight - tooltipHeight - 20;
    }
    if (left < 0) {
        left = rect.left + window.scrollX + box.offsetWidth + 10;
    }

    tooltip.style.top = `${top}px`;
    tooltip.style.left = `${left}px`;
    tooltip.classList.remove("hidden");
    tooltip.classList.add("visible");

    tooltip.querySelectorAll(".tooltip-action-btn").forEach(btn => {
        btn.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            handleTooltipAction(box, btn.dataset.action);
        });
    });
}

function handleTooltipAction(box, action) {
    if (!box || !action) {
        return;
    }
}

function performItemReschedule(box) {
    const rescheduleUrl = box.dataset.rescheduleUrl;
    if (!rescheduleUrl) {
        return;
    }
    const currentStart = box.dataset.startIso || "";
    const defaultPrompt = currentStart ? currentStart.replace("T", " ").slice(0, 16) : "";
    const userInput = window.prompt("New start time (local, YYYY-MM-DD HH:MM)", defaultPrompt);
    if (userInput === null) {
        return;
    }
    const trimmed = userInput.trim();
    if (!trimmed) {
        return;
    }
    const isoCandidate = trimmed.includes("T") ? trimmed : trimmed.replace(" ", "T");
    const parsed = new Date(isoCandidate);
    if (Number.isNaN(parsed.getTime())) {
        window.alert("Invalid date/time. Please use YYYY-MM-DD HH:MM format.");
        return;
    }
    const payload = { start_time: parsed.toISOString() };

    fetch(rescheduleUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrfToken(),
        },
        body: JSON.stringify(payload),
    })
        .then(response => {
            if (!response.ok) {
                return response.json().catch(() => ({})).then(data => {
                    throw new Error(data.error || response.statusText || "Unable to reschedule item");
                });
            }
            return response.json();
        })
        .then(() => {
            hideTooltip();
            window.location.reload();
        })
        .catch(err => {
            window.alert(err.message || "Unable to reschedule item");
        });
}
function hideTooltip() {
    tooltip.classList.remove("visible");
    tooltip.classList.add("hidden");
}

document.querySelectorAll(".unavailable-cell").forEach(cell => {
    cell.addEventListener("mouseenter", () => showUnavailableTooltip(cell));
    cell.addEventListener("mouseleave", () => hideTooltip());
});

function showUnavailableTooltip(cell) {
    const rect = cell.getBoundingClientRect();
    const reason = cell.dataset.reason || "Unavailable";
    const start = cell.dataset.start || "";
    const end = cell.dataset.end || "";
    const until = cell.dataset.until || "";

    const tooltip = document.getElementById("apptTooltip");

    tooltip.innerHTML = `
        <div class="tooltip-card">
            <div class="tooltip-header">
                <span><strong>${reason.charAt(0).toUpperCase() + reason.slice(1)}</strong></span>
            </div>
            <div class="tooltip-body">
                <div style="font-size:1.6vh; font-weight:500; margin-bottom: 0.66vh;">
                    ${start} - ${end}
                </div>
                ${until ? `<div style="font-size:1.4vh; color:#777;">Ends ${until}</div>` : ""}
            </div>
        </div>
    `;
    const tooltipWidth = 375;
    const tooltipHeight = 120; // можно скорректировать
    const middleY = rect.top + rect.height / 2 + window.scrollY;
    const leftX = rect.left + window.scrollX - tooltipWidth - 10;
    const rightX = rect.right + window.scrollX + 10;

    // Установим начальные координаты
    tooltip.style.top = `${middleY - tooltipHeight / 2}px`;

    // Если не влезает слева — показываем справа
    if (leftX < 0) {
        tooltip.style.left = `${rightX}px`;
    } else {
        tooltip.style.left = `${leftX}px`;
    }


    tooltip.classList.remove("hidden");
    tooltip.classList.add("visible");
}

const addBtn = document.getElementById("addDropdownBtn");
const menu = document.getElementById("addDropdownMenu");
const arrow = document.getElementById("arrow");

addBtn.addEventListener("click", () => {
    menu.classList.toggle("hidden");
    arrow.textContent = menu.classList.contains("hidden") ? "▾" : "▴";
});

// Закрытие по клику вне меню
document.addEventListener("click", (e) => {
    if (!addBtn.contains(e.target) && !menu.contains(e.target)) {
        menu.classList.add("hidden");
        arrow.textContent = "▾";
    }
});

function handleAdd(type) {
    const selectedDate = document.getElementById("realDateInput").value;
    const masterId = lastActiveCell?.dataset?.master;
    const time = lastActiveCell?.value;

    let url = "#";

    if (type === "appointment") {
        url = `/admin/core/appointment/add/?date=${selectedDate}&time=${time}&master=${masterId}`;
    } else if (type === "vacation") {
        url = `/admin/core/masteravailability/add/?date=${selectedDate}&time=${time}&master=${masterId}`;
    } else {
        alert(`"${type}" action is not implemented yet.`);
        return;
    }

    window.location.href = url;

}
