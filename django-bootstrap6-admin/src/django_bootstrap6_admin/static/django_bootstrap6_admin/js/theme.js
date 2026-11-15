"use strict";

/*
 * Keeps Django's theme preference (auto/light/dark) in sync with
 * Bootstrap 6's `data-bs-theme` attribute and `color-scheme`.
 */
(() => {
    const STORAGE_KEY = "theme";
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const modes = ["auto", "light", "dark"];

    function normalize(mode) {
        return modes.includes(mode) ? mode : "auto";
    }

    function current() {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (modes.includes(stored)) {
            return stored;
        }
        // First visit: start in the effective OS theme so the visible page
        // and the toggle icon agree immediately. Auto remains in the cycle.
        return media.matches ? "dark" : "light";
    }

    function updateButtons(mode) {
        document.querySelectorAll(".theme-toggle").forEach((button) => {
            const label =
                button.dataset[
                    `label${mode.charAt(0).toUpperCase()}${mode.slice(1)}`
                ];
            button.dataset.theme = mode;
            if (label) {
                button.setAttribute("aria-label", label);
                button.setAttribute("title", label);
            }
        });
    }

    function apply(mode) {
        mode = normalize(mode);
        const root = document.documentElement;
        const effective =
            mode === "auto" ? (media.matches ? "dark" : "light") : mode;

        root.dataset.theme = mode;
        root.dataset.effectiveTheme = effective;
        if (mode === "auto") {
            delete root.dataset.bsTheme;
        } else {
            root.dataset.bsTheme = mode;
        }

        updateButtons(mode);
    }

    function set(mode) {
        mode = normalize(mode);
        localStorage.setItem(STORAGE_KEY, mode);
        apply(mode);
    }

    function cycle() {
        const mode = current();
        let next;

        if (media.matches) {
            next =
                mode === "auto" ? "light" : mode === "light" ? "dark" : "auto";
        } else {
            next =
                mode === "auto" ? "dark" : mode === "dark" ? "light" : "auto";
        }

        set(next);
    }

    function bindButtons() {
        document.querySelectorAll(".theme-toggle").forEach((button) => {
            if (button.dataset.themeBound === "true") {
                return;
            }
            button.dataset.themeBound = "true";
            button.addEventListener("click", cycle);
        });
        updateButtons(current());
    }

    apply(current());

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bindButtons, {
            once: true,
        });
    } else {
        bindButtons();
    }

    if (media.addEventListener) {
        media.addEventListener("change", () => {
            if (current() === "auto") {
                apply("auto");
            }
        });
    }

    window.Bootstrap6AdminTheme = { apply, current, cycle, set };
})();
