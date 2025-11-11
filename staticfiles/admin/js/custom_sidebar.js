document.addEventListener("DOMContentLoaded", function () {
    const sidebar = document.getElementById("sidebar");

    highlightActiveMenu(sidebar);
    enhanceBreadcrumbs(sidebar);
    setupSidebarHover(sidebar);
    updateSidebarOffsets();

    window.addEventListener("resize", debounce(updateSidebarOffsets, 150));
});

function toggleDropdown(clickedElement) {
    const allDropdowns = document.querySelectorAll(".icon-sidebar .dropdown");

    allDropdowns.forEach(function (dropdown) {
        if (dropdown !== clickedElement.parentElement) {
            dropdown.classList.remove("open");
        }
    });

    clickedElement.parentElement.classList.toggle("open");
}

function highlightActiveMenu(sidebar) {
    if (!sidebar) {
        return;
    }

    const currentPath = window.location.pathname;
    const navLinks = Array.from(sidebar.querySelectorAll("a[href]")).filter(function (link) {
        const href = link.getAttribute("href");
        return href && !href.startsWith("javascript");
    });

    let activeLink = null;
    let longestMatch = 0;

    navLinks.forEach(function (link) {
        const href = link.getAttribute("href");
        let linkPath;

        try {
            linkPath = new URL(href, window.location.origin).pathname;
        } catch (error) {
            return;
        }

        if (isPathMatch(currentPath, linkPath) && linkPath.length >= longestMatch) {
            longestMatch = linkPath.length;
            activeLink = link;
        }
    });

    if (activeLink) {
        activeLink.classList.add("is-active");
        const dropdown = activeLink.closest(".dropdown");

        if (dropdown) {
            dropdown.classList.add("is-current");
            const toggleLink = dropdown.querySelector(":scope > a");
            if (toggleLink) {
                toggleLink.classList.add("is-active");
            }
        }
    }
}

function isPathMatch(currentPath, linkPath) {
    if (!linkPath || linkPath === "#") {
        return false;
    }

    if (linkPath === "/admin/") {
        return currentPath === linkPath;
    }

    const normalizedCandidate = linkPath.endsWith("/") ? linkPath : linkPath + "/";
    const normalizedCurrent = currentPath.endsWith("/") ? currentPath : currentPath + "/";

    return (
        normalizedCurrent === normalizedCandidate ||
        normalizedCurrent.startsWith(normalizedCandidate)
    );
}

function enhanceBreadcrumbs(sidebar) {
    const breadcrumbNav = document.querySelector('nav[aria-label="Breadcrumbs"]');
    if (!breadcrumbNav) {
        return;
    }

    const original = breadcrumbNav.querySelector(".breadcrumbs");
    let crumbs = [];

    if (original) {
        crumbs = extractCrumbData(original);
    }

    if (!crumbs.length) {
        crumbs = buildFallbackCrumbs(sidebar);
    }

    if (!crumbs.length) {
        return;
    }

    normalizeDashboardCrumb(crumbs, sidebar);

    breadcrumbNav.classList.add("ma-breadcrumbs");

    const list = document.createElement("ol");
    list.className = "ma-breadcrumbs__list";

    crumbs.forEach(function (crumb, index) {
        if (!crumb || !crumb.label) {
            return;
        }

        const item = document.createElement("li");
        item.className = "ma-breadcrumbs__item";
        const isLast = index === crumbs.length - 1;

        if (crumb.href && !isLast) {
            const link = document.createElement("a");
            link.href = crumb.href;
            link.textContent = crumb.label;
            item.appendChild(link);
        } else {
            const span = document.createElement("span");
            span.textContent = crumb.label;
            item.appendChild(span);
            if (isLast) {
                item.classList.add("ma-breadcrumbs__item--current");
            }
        }

        list.appendChild(item);
    });

    breadcrumbNav.innerHTML = "";
    breadcrumbNav.appendChild(list);
}

function extractCrumbData(container) {
    const crumbs = [];

    container.childNodes.forEach(function (node) {
        if (node.nodeType === 1) {
            const element = node;
            const label = normalizeLabel(element.textContent);
            if (!label) {
                return;
            }

            if (element.tagName === "A") {
                crumbs.push({
                    label: label,
                    href: element.getAttribute("href") || ""
                });
            } else {
                crumbs.push({ label: label });
            }
        } else if (node.nodeType === 3) {
            const label = normalizeLabel(node.textContent);
            if (label) {
                crumbs.push({ label: label });
            }
        }
    });

    return crumbs;
}

function buildFallbackCrumbs(sidebar) {
    const crumbs = [];

    crumbs.push({
        label: "Dashboard",
        href: "/admin/"
    });

    if (!sidebar) {
        return crumbs;
    }

    const parentLink = sidebar.querySelector(".dropdown > a.is-active");
    const activeChild = sidebar.querySelector(".dropdown .submenu a.is-active");
    const primaryActive =
        activeChild ||
        sidebar.querySelector(".icon-sidebar > ul > li > a.is-active:not([href^='javascript'])");

    if (parentLink && parentLink !== primaryActive) {
        const parentLabel = getSidebarLabel(parentLink);
        if (parentLabel && !crumbs.some(function (crumb) { return crumb.label === parentLabel; })) {
            crumbs.push({ label: parentLabel });
        }
    }

    if (primaryActive) {
        const label = getSidebarLabel(primaryActive);
        const href = primaryActive.getAttribute("href");

        if (label && !crumbs.some(function (crumb) { return crumb.label === label; })) {
            if (href && !href.startsWith("javascript")) {
                crumbs.push({ label: label, href: href });
            } else {
                crumbs.push({ label: label });
            }
        }
    }

    return crumbs;
}

function getSidebarLabel(link) {
    if (!link) {
        return "";
    }

    const labelNode = link.querySelector(".sidebar-label");
    if (labelNode) {
        const clone = labelNode.cloneNode(true);
        const dropdownArrow = clone.querySelector(".dropdown-arrow");
        if (dropdownArrow) {
            dropdownArrow.remove();
        }
        return normalizeLabel(clone.textContent);
    }

    return normalizeLabel(link.textContent);
}

function normalizeLabel(value) {
    if (!value) {
        return "";
    }

    return value.replace(/›/g, "").replace(/\s+/g, " ").trim();
}

function normalizeDashboardCrumb(crumbs, sidebar) {
    if (!crumbs.length) {
        return;
    }

    const dashboardLabel = getDashboardLabel(sidebar);
    if (!dashboardLabel) {
        return;
    }

    crumbs[0].label = dashboardLabel;
    crumbs[0].href = "/admin/";
}

function getDashboardLabel(sidebar) {
    if (!sidebar) {
        return "";
    }

    const dashboardLink = sidebar.querySelector('a[href="/admin/"]');
    if (!dashboardLink) {
        return "";
    }

    return getSidebarLabel(dashboardLink);
}

function setupSidebarHover(sidebar) {
    if (!sidebar) {
        return;
    }

    const hoverClass = "sidebar-hover";

    function applyHoverState() {
        document.body.classList.add(hoverClass);
    }

    function clearHoverState() {
        document.body.classList.remove(hoverClass);
    }

    sidebar.addEventListener("mouseenter", applyHoverState);

    sidebar.addEventListener("mouseleave", function () {
        clearHoverState();

        const openDropdowns = sidebar.querySelectorAll(".dropdown.open");
        openDropdowns.forEach(function (dropdown) {
            if (!dropdown.classList.contains("is-current")) {
                dropdown.classList.remove("open");
            }
        });
    });

    // Provide hover expansion without locking labels open when using the mouse.
}

function updateSidebarOffsets() {
    const root = document.documentElement;
    if (!root) {
        return;
    }

    const header = document.querySelector(".main-header");
    const hasHeader = Boolean(header);
    let headerHeight = 0;

    if (hasHeader) {
        const rect = header.getBoundingClientRect();
        headerHeight = rect.height;
    }

    const minimumOffset = hasHeader ? 72 : 0;
    const computedOffset = hasHeader ? Math.round(headerHeight) + 16 : 0;
    const offsetValue = Math.max(computedOffset, minimumOffset);

    root.style.setProperty("--icon-sidebar-offset-top", offsetValue + "px");
}

function debounce(fn, wait) {
    let timerId;
    return function () {
        const context = this;
        const args = arguments;

        clearTimeout(timerId);
        timerId = setTimeout(function () {
            fn.apply(context, args);
        }, wait);
    };
}
