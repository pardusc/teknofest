"use strict";

/*
 * Small progressive enhancement layer for the Bootstrap 6 admin.
 *
 * Django's own admin JavaScript remains the source of truth for the
 * sidebar state (`#main.shifted` and `#nav-sidebar[aria-expanded]`).
 * This file only mirrors that state to the topbar button, adds a mobile
 * backdrop, and closes the sidebar with Escape or an outside click.
 */
(() => {
    const MOBILE = window.matchMedia("(max-width: 1023.98px)");
    const STORAGE_KEY = "django.admin.navSidebarIsOpen";

    function initSidebar() {
        const main = document.getElementById("main");
        const sidebar = document.getElementById("nav-sidebar");
        const nativeToggle = document.getElementById("toggle-nav-sidebar");
        const topbarToggle = document.getElementById("ba-sidebar-toggle");
        const closeButton = document.getElementById("ba-sidebar-close");
        const backdrop = document.getElementById("ba-sidebar-backdrop");

        if (!topbarToggle) {
            return;
        }

        // Pages such as the dashboard and the login screen deliberately
        // render without the navigation sidebar.
        if (!main || !sidebar || !nativeToggle) {
            topbarToggle.hidden = true;
            return;
        }

        function isOpen() {
            return main.classList.contains("shifted");
        }

        function sync() {
            const open = isOpen();
            topbarToggle.setAttribute("aria-expanded", open ? "true" : "false");
            sidebar.toggleAttribute("inert", !open);
            sidebar.setAttribute("aria-hidden", open ? "false" : "true");
            document.body.classList.toggle(
                "ba-sidebar-open",
                open && MOBILE.matches,
            );
            if (backdrop) {
                backdrop.hidden = !(open && MOBILE.matches);
            }
        }

        function focusSidebar() {
            if (!MOBILE.matches) {
                return;
            }
            const target =
                closeButton ||
                sidebar.querySelector("#nav-filter, a, button");
            if (target) {
                window.requestAnimationFrame(() => target.focus());
            }
        }

        function closeSidebar(returnFocus) {
            if (isOpen()) {
                nativeToggle.click();
            }
            if (returnFocus) {
                topbarToggle.focus();
            }
        }

        topbarToggle.addEventListener("click", () => {
            const opening = !isOpen();
            nativeToggle.click();
            if (opening) {
                focusSidebar();
            }
        });

        if (closeButton) {
            closeButton.addEventListener("click", () => {
                closeSidebar(true);
            });
        }

        if (backdrop) {
            backdrop.addEventListener("click", () => {
                closeSidebar(true);
            });
        }

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && MOBILE.matches && isOpen()) {
                closeSidebar(true);
            }
        });

        // Close the mobile drawer after choosing a destination. Keeping it
        // open through navigation makes every link cost an extra close tap.
        sidebar.addEventListener("click", (event) => {
            if (!MOBILE.matches || !isOpen()) {
                return;
            }
            const link = event.target.closest("a");
            if (link && sidebar.contains(link)) {
                nativeToggle.click();
            }
        });

        const observer = new MutationObserver(sync);
        observer.observe(main, {
            attributes: true,
            attributeFilter: ["class"],
        });
        observer.observe(sidebar, {
            attributes: true,
            attributeFilter: ["aria-expanded"],
        });

        if (MOBILE.addEventListener) {
            MOBILE.addEventListener("change", sync);
        }

        // On the first mobile visit, open the page with the navigation
        // closed. A stored preference always wins.
        if (MOBILE.matches && localStorage.getItem(STORAGE_KEY) === null) {
            window.requestAnimationFrame(() => {
                if (isOpen()) {
                    nativeToggle.click();
                }
            });
        }

        sync();
    }

    function initAccessibility() {
        // SelectFilter2 generates a span with aria-label but no role.
        document
            .querySelectorAll(
                ".selector-filter .help-tooltip.search-label-icon[aria-label]",
            )
            .forEach((element) => {
                if (!element.hasAttribute("role")) {
                    element.setAttribute("role", "img");
                }
            });

        // Select2 replaces the labelled <select> with spans. Copy the label
        // onto the generated container and selection elements.
        document
            .querySelectorAll("select.admin-autocomplete")
            .forEach((select) => {
                if (!select.id) {
                    return;
                }
                const labelElement = document.querySelector(
                    `label[for="${CSS.escape(select.id)}"]`,
                );
                const label =
                    labelElement?.textContent.trim() ||
                    select.getAttribute("aria-label") ||
                    select.name ||
                    "Select";
                const container =
                    select.parentElement?.querySelector(".select2-container") ||
                    select.nextElementSibling;
                if (!container) {
                    return;
                }
                const selection = container.querySelector(
                    ".select2-selection",
                );
                if (selection && !selection.getAttribute("aria-label")) {
                    selection.setAttribute("aria-label", label);
                }
                if (!container.getAttribute("aria-label")) {
                    container.setAttribute("aria-label", label);
                }
                const rendered = container.querySelector(
                    ".select2-selection__rendered",
                );
                if (rendered && !rendered.getAttribute("aria-label")) {
                    rendered.setAttribute("aria-label", label);
                }
            });

        // Django renders list-editable widgets without labels. Give each
        // control an accessible name derived from its column and row.
        const table = document.getElementById("result_list");
        if (!table || !table.tHead || !table.tBodies.length) {
            return;
        }
        const headers = Array.from(table.tHead.rows[0]?.cells || []).map(
            (cell) => cell.textContent.trim(),
        );
        Array.from(table.tBodies[0].rows).forEach((row) => {
            const rowName =
                row.querySelector("th a, td a")?.textContent.trim() || "";
            Array.from(row.cells).forEach((cell, index) => {
                cell.querySelectorAll("input, select, textarea").forEach(
                    (control) => {
                        if (
                            control.type === "hidden" ||
                            control.getAttribute("aria-label") ||
                            (control.labels && control.labels.length)
                        ) {
                            return;
                        }
                        const column = headers[index] || "Field";
                        control.setAttribute(
                            "aria-label",
                            rowName ? `${column} for ${rowName}` : column,
                        );
                    },
                );
            });
        });
    }

    function initFilterDisclosure() {
        const toggle = document.getElementById("ba-filters-toggle");
        const changelist = document.getElementById("changelist");
        const panel = document.getElementById("changelist-filter");
        const close = document.getElementById("ba-filters-close");
        if (!toggle || !changelist) {
            return;
        }

        const sync = () => {
            toggle.setAttribute(
                "aria-expanded",
                changelist.classList.contains("ba-filters-open")
                    ? "true"
                    : "false",
            );
        };

        toggle.addEventListener("click", () => {
            changelist.classList.toggle("ba-filters-open");
            sync();
            if (changelist.classList.contains("ba-filters-open")) {
                const target =
                    panel?.querySelector(".ba-filters-close, summary, a, button");
                window.requestAnimationFrame(() => target?.focus());
            }
        });

        if (close) {
            close.addEventListener("click", () => {
                changelist.classList.remove("ba-filters-open");
                sync();
                toggle.focus();
            });
        }

        sync();
    }

    function initDirtyGuard() {
        const form =
            document.querySelector(".ba-change-form form") ||
            document.getElementById("changelist-form");
        if (!form) {
            return;
        }

        const isChangelist = form.id === "changelist-form";
        let dirty = false;

        const markDirty = (event) => {
            if (
                isChangelist &&
                (!event.target.closest("#result_list") ||
                    event.target.matches(".action-select, #action-toggle"))
            ) {
                return;
            }
            dirty = true;
        };

        form.addEventListener("input", markDirty);
        form.addEventListener("change", markDirty);
        form.addEventListener("submit", () => {
            dirty = false;
        });
        window.addEventListener("beforeunload", (event) => {
            if (!dirty) {
                return;
            }
            event.preventDefault();
            event.returnValue = "";
        });
    }

    function initErrorFocus() {
        const alert = document.querySelector(".ba-form-alert");
        if (!alert) {
            return;
        }

        document.querySelectorAll("details.ba-collapse").forEach((details) => {
            if (details.querySelector(".errors, .errorlist, .errornote")) {
                details.open = true;
            }
        });

        const errorList = document.querySelector(
            ".ba-change-form .errors, .ba-change-form .errorlist",
        );
        const container = errorList?.closest(
            ".form-row, .ba-field, .ba-inline-card, td",
        );
        const invalid = container?.querySelector(
            "input:not([type=hidden]), select, textarea",
        );

        if (invalid) {
            invalid.focus({ preventScroll: true });
            invalid.scrollIntoView({ block: "center" });
        } else {
            alert.focus();
        }
    }

    function initAll() {
        initSidebar();
        initFilterDisclosure();
        initDirtyGuard();
        initErrorFocus();
        initAccessibility();
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            initAll,
            { once: true },
        );
    } else {
        initAll();
    }

    // SelectFilter2 runs from jQuery's ready handler and may create its
    // labelled icon spans just after ours. Re-run once the window is loaded
    // and after each dynamically added inline formset.
    window.addEventListener(
        "load",
        () => {
            initAccessibility();
            // Select2 can finish its DOM replacement a little later.
            window.setTimeout(initAccessibility, 750);
        },
        { once: true },
    );
    document.addEventListener("formset:added", () => {
        window.setTimeout(initAccessibility, 100);
    });
})();
