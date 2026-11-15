const initLengthHints = (field) => {
  const control = field.querySelector("[data-maxlength], [data-minlength]");
  if (!control) return;

  const counter = field.querySelector("[data-maxlength-counter]");
  const warning = field.querySelector("[data-minlength-warning]");
  const max = Number.parseInt(control.dataset.maxlength || "", 10);
  const min = Number.parseInt(control.dataset.minlength || "", 10);
  const hasMax = Number.isFinite(max) && max > 0;
  const hasMin = Number.isFinite(min) && min > 0;

  const updateCounter = () => {
    if (!counter || !hasMax) return;

    const length = control.value.length;
    const visible = length > max / 2;
    counter.hidden = !visible;

    if (!visible) {
      counter.classList.remove("is-near-limit", "is-at-limit");
      return;
    }

    counter.textContent = `${length} / ${max}`;
    counter.classList.toggle("is-near-limit", length >= max * 0.9);
    counter.classList.toggle("is-at-limit", length >= max);
  };

  const validateMin = () => {
    if (!warning || !hasMin) return;

    const length = control.value.trim().length;
    const invalid = length > 0 && length < min;
    warning.hidden = !invalid;
    warning.textContent = invalid ? control.dataset.minlengthMessage || "" : "";

    if (invalid) {
      control.setAttribute("aria-invalid", "true");
    } else {
      control.removeAttribute("aria-invalid");
    }
  };

  control.addEventListener("input", () => {
    updateCounter();
    if (warning && !warning.hidden) validateMin();
  });
  control.addEventListener("blur", validateMin);

  updateCounter();
};

document.querySelectorAll(".dynamic-field").forEach(initLengthHints);
