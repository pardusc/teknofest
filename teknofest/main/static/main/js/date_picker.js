const dialog = document.getElementById("site-datepicker");

if (dialog) {
  const grid = dialog.querySelector("[data-date-grid]");
  const weekdays = dialog.querySelector("[data-date-weekdays]");
  const title = dialog.querySelector("#site-datepicker-title");
  const language = document.documentElement.lang || "tr";

  const monthFormat = new Intl.DateTimeFormat(language, {
    month: "long",
    year: "numeric",
  });
  const weekdayFormat = new Intl.DateTimeFormat(language, { weekday: "short" });
  const dayFormat = new Intl.DateTimeFormat(language, { dateStyle: "full" });

  let firstDay = 1;
  try {
    const locale = new Intl.Locale(language);
    firstDay = locale.weekInfo?.firstDay || locale.getWeekInfo?.()?.firstDay || 1;
  } catch (error) {
    firstDay = 1;
  }

  const weekdayBase = new Date(2024, 0, 7);
  weekdays.replaceChildren(
    ...Array.from({ length: 7 }, (_, index) => {
      const date = new Date(weekdayBase);
      date.setDate(weekdayBase.getDate() + (firstDay % 7) + index);
      const label = document.createElement("span");
      label.className = "date-picker-weekday";
      label.textContent = weekdayFormat.format(date);
      return label;
    }),
  );

  let activeInput = null;
  let viewYear = new Date().getFullYear();
  let viewMonth = new Date().getMonth();

  const parseValue = (value) => {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
    if (!match) return null;
    return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  };

  const toValue = (date) =>
    [
      date.getFullYear(),
      String(date.getMonth() + 1).padStart(2, "0"),
      String(date.getDate()).padStart(2, "0"),
    ].join("-");

  const isSameDay = (left, right) =>
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate();

  const today = () => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  };

  const dispatchChange = (input) => {
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  };

  const render = () => {
    const firstOfMonth = new Date(viewYear, viewMonth, 1);
    const leading = (firstOfMonth.getDay() - (firstDay % 7) + 7) % 7;
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
    const selected = activeInput ? parseValue(activeInput.value) : null;
    const currentDay = today();

    title.textContent = monthFormat.format(firstOfMonth);
    grid.replaceChildren();

    for (let index = 0; index < leading; index += 1) {
      const blank = document.createElement("span");
      blank.className = "date-picker-blank";
      blank.setAttribute("aria-hidden", "true");
      grid.append(blank);
    }

    for (let day = 1; day <= daysInMonth; day += 1) {
      const date = new Date(viewYear, viewMonth, day);
      const button = document.createElement("button");
      const isSelected = Boolean(selected && isSameDay(date, selected));
      button.type = "button";
      button.className = "date-picker-day";
      button.textContent = String(day);
      button.dataset.date = toValue(date);
      button.setAttribute("aria-label", dayFormat.format(date));
      button.setAttribute("aria-pressed", isSelected ? "true" : "false");

      if (isSameDay(date, currentDay)) button.classList.add("is-today");
      if (isSameDay(date, currentDay)) button.setAttribute("aria-current", "date");
      if (isSelected) button.classList.add("is-selected");

      button.addEventListener("click", () => {
        if (!activeInput) return;
        activeInput.value = toValue(date);
        dispatchChange(activeInput);
        closePicker();
      });

      grid.append(button);
    }
  };

  const closePicker = () => {
    if (dialog.open) {
      dialog.close();
    } else {
      dialog.removeAttribute("open");
    }
  };

  const openPicker = (input) => {
    if (dialog.open) return;
    activeInput = input;
    const current = parseValue(input.value) || today();
    viewYear = current.getFullYear();
    viewMonth = current.getMonth();
    render();

    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }

    const target =
      dialog.querySelector(".date-picker-day.is-selected") ||
      dialog.querySelector(".date-picker-day.is-today") ||
      dialog.querySelector(".date-picker-day");
    target?.focus({ preventScroll: true });
  };

  const shiftMonth = (offset) => {
    const next = new Date(viewYear, viewMonth + offset, 1);
    viewYear = next.getFullYear();
    viewMonth = next.getMonth();
    render();
  };

  dialog.querySelector("[data-date-prev]").addEventListener("click", () => shiftMonth(-1));
  dialog.querySelector("[data-date-next]").addEventListener("click", () => shiftMonth(1));

  dialog.querySelector("[data-date-today]").addEventListener("click", () => {
    if (!activeInput) return;
    const now = today();
    activeInput.value = toValue(now);
    dispatchChange(activeInput);
    closePicker();
  });

  dialog.querySelector("[data-date-clear]").addEventListener("click", () => {
    if (!activeInput) return;
    activeInput.value = "";
    dispatchChange(activeInput);
    closePicker();
  });

  dialog.querySelector("[data-date-close]").addEventListener("click", closePicker);
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) closePicker();
  });

  dialog.addEventListener("close", () => {
    const input = activeInput;
    activeInput = null;
    input?.focus({ preventScroll: true });
  });

  dialog.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
      return;
    }
    const buttons = [...grid.querySelectorAll(".date-picker-day")];
    const index = buttons.indexOf(document.activeElement);
    if (index === -1) return;
    event.preventDefault();
    const offset = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -7,
      ArrowDown: 7,
    }[event.key];
    buttons[Math.max(0, Math.min(buttons.length - 1, index + offset))]?.focus();
  });

  document.querySelectorAll(".date-input-wrap").forEach((wrap) => {
    const input = wrap.querySelector('input[type="date"]');
    if (!input) return;

    wrap.classList.add("is-enhanced");
    const toggle = wrap.querySelector("[data-date-open]");
    if (toggle) {
      toggle.hidden = false;
      toggle.addEventListener("click", () => openPicker(input));
    }

    input.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      input.focus({ preventScroll: true });
      openPicker(input);
    });

    input.addEventListener("keydown", (event) => {
      if (!["Enter", " ", "ArrowDown"].includes(event.key)) return;
      event.preventDefault();
      openPicker(input);
    });
  });
}
