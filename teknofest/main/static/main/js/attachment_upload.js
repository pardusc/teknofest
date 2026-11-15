const input = document.querySelector("[data-attachment-input]");

if (input) {
  const form = input.closest("form");
  const dropzone = input.closest("[data-file-drop]") || input.parentElement;
  const selection = document.querySelector("[data-attachment-selection]");
  const errorElement = document.querySelector("[data-attachment-error]");
  const quotaFiles = document.querySelector("[data-quota-files]");
  const quotaVideos = document.querySelector("[data-quota-videos]");
  const quotaBytes = document.querySelector("[data-quota-bytes]");
  const status = document.querySelector("[data-attachment-status]");
  const previewDialog = document.getElementById("attachment-preview-dialog");
  const canPreview = previewDialog && typeof previewDialog.showModal === "function";
  const supportsDataTransfer = typeof DataTransfer !== "undefined";
  const requiredOnLoad = input.required;

  const config = {
    profile: input.dataset.profile || "default",
    maxFiles: Number(input.dataset.maxFiles || 0),
    maxVideos: Number(input.dataset.maxVideos || 0),
    maxImageBytes: Number(input.dataset.maxImageBytes || 0),
    maxVideoBytes: Number(input.dataset.maxVideoBytes || 0),
    maxTotalBytes: Number(input.dataset.maxTotalBytes || 0),
    existingFiles: Number(input.dataset.existingFiles || 0),
    existingVideos: Number(input.dataset.existingVideos || 0),
    existingBytes: Number(input.dataset.existingBytes || 0),
    messages: {
      image: input.dataset.msgImage || "",
      video: input.dataset.msgVideo || "",
      size: input.dataset.msgSize || "",
      fileLimit: input.dataset.msgFileLimit || "",
      videoLimit: input.dataset.msgVideoLimit || "",
      totalLimit: input.dataset.msgTotalLimit || "",
      remove: input.dataset.msgRemove || "Remove",
      preview: input.dataset.msgPreview || "Preview",
    },
  };

  let selected = [];
  let objectUrls = [];
  let syncingInput = false;
  let clearTimer = null;

  const formatBytes = (bytes) => {
    if (bytes >= 1024 * 1024) {
      const value = bytes / (1024 * 1024);
      return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} MB`;
    }
    if (bytes >= 1024) return `${Math.ceil(bytes / 1024)} KB`;
    return `${bytes} B`;
  };

  const fileKind = (file) => {
    const name = (file.name || "").toLowerCase();
    const type = (file.type || "").toLowerCase();
    if (type === "video/webm" || name.endsWith(".webm")) return "video";
    if (type.startsWith("image/") || /\.(webp|jpe?g|png)$/.test(name)) return "image";
    return null;
  };

  const imageAllowed = (file) => {
    const name = (file.name || "").toLowerCase();
    const type = (file.type || "").toLowerCase();
    if (config.profile === "webp_webm") {
      return type === "image/webp" || name.endsWith(".webp");
    }
    return (
      type === "image/jpeg" ||
      type === "image/png" ||
      /\.(jpe?g|png)$/.test(name)
    );
  };

  const videoAllowed = (file) => {
    const name = (file.name || "").toLowerCase();
    const type = (file.type || "").toLowerCase();
    return type === "video/webm" || name.endsWith(".webm");
  };

  const revokeObjectUrls = () => {
    objectUrls.forEach((url) => URL.revokeObjectURL(url));
    objectUrls = [];
  };

  const openLocalPreview = (file, objectUrl) => {
    const kind = fileKind(file);
    if (!canPreview) {
      window.open(objectUrl, "_blank", "noopener");
      return;
    }

    const body = previewDialog.querySelector("[data-preview-body]");
    const title = previewDialog.querySelector("[data-preview-title]");
    const download = previewDialog.querySelector("[data-preview-download]");
    if (!body || !title) return;

    title.textContent = file.name;
    body.replaceChildren();

    if (kind === "video") {
      const video = document.createElement("video");
      video.className = "attachment-preview-media";
      video.controls = true;
      video.autoplay = true;
      video.playsInline = true;
      video.preload = "metadata";
      video.src = objectUrl;
      body.append(video);
    } else {
      const image = document.createElement("img");
      image.className = "attachment-preview-media";
      image.src = objectUrl;
      image.alt = file.name;
      body.append(image);
    }

    if (download) {
      download.href = objectUrl;
      download.download = file.name;
    }

    document.body.classList.add("attachment-preview-open");
    previewDialog.showModal();
    previewDialog.querySelector("[data-preview-close]")?.focus();
  };

  const updateQuota = () => {
    const selectedBytes = selected.reduce((total, file) => total + file.size, 0);
    const selectedVideos = selected.filter((file) => fileKind(file) === "video").length;

    if (quotaFiles) {
      quotaFiles.textContent = String(
        Math.max(0, config.maxFiles - config.existingFiles - selected.length),
      );
    }
    if (quotaVideos) {
      quotaVideos.textContent = String(
        Math.max(0, config.maxVideos - config.existingVideos - selectedVideos),
      );
    }
    if (quotaBytes) {
      quotaBytes.textContent = formatBytes(
        Math.max(0, config.maxTotalBytes - config.existingBytes - selectedBytes),
      );
    }
  };

  const setError = (message) => {
    input.setCustomValidity(message);
    if (errorElement) {
      errorElement.textContent = message;
      errorElement.hidden = !message;
    }
  };

  const validate = () => {
    if (config.maxFiles && config.existingFiles + selected.length > config.maxFiles) {
      setError(config.messages.fileLimit);
      return false;
    }

    let selectedVideos = 0;
    let cutAt = null;
    let invalidKind = null;
    let invalidSize = false;
    let selectedBytes = 0;

    selected.forEach((file, index) => {
      const kind = fileKind(file);
      if (kind === "video") {
        selectedVideos += 1;
        if (!config.maxVideos || !videoAllowed(file)) invalidKind = "video";
        if (config.maxVideoBytes && file.size > config.maxVideoBytes) invalidSize = true;
      } else if (kind === "image") {
        if (!imageAllowed(file)) invalidKind = "image";
        if (config.maxImageBytes && file.size > config.maxImageBytes) invalidSize = true;
      } else {
        invalidKind = "image";
      }

      selectedBytes += file.size || 0;
      if (cutAt === null && config.maxVideos && config.existingVideos + selectedVideos > config.maxVideos) {
        cutAt = index;
      }
    });

    if (cutAt !== null) {
      setError(config.messages.videoLimit);
      return false;
    }
    if (invalidKind) {
      setError(invalidKind === "video" ? config.messages.video : config.messages.image);
      return false;
    }
    if (invalidSize) {
      setError(config.messages.size);
      return false;
    }
    if (
      config.maxTotalBytes &&
      config.existingBytes + selectedBytes > config.maxTotalBytes
    ) {
      setError(config.messages.totalLimit);
      return false;
    }

    setError("");
    return true;
  };

  const formatLabel = (file, kind) => {
    if (kind === "video") return "WebM";
    if (config.profile === "webp_webm") return "WebP";
    return (file.name || "").toLowerCase().endsWith(".png") ? "PNG" : "JPEG";
  };

  const renderSelection = () => {
    if (!selection) return;
    revokeObjectUrls();
    selection.replaceChildren();
    selection.hidden = selected.length === 0;

    selected.forEach((file, index) => {
      const kind = fileKind(file);
      const item = document.createElement("article");
      item.className = "attachment-card attachment-card--selection";

      const open = document.createElement("button");
      open.type = "button";
      open.className = "attachment-link";
      open.setAttribute("aria-label", `${config.messages.preview}: ${file.name}`);

      const preview = document.createElement("span");
      preview.className = `attachment-thumb${kind === "video" ? " attachment-thumb--video" : ""}`;
      const objectUrl = URL.createObjectURL(file);
      objectUrls.push(objectUrl);

      if (kind === "video") {
        const video = document.createElement("video");
        video.src = objectUrl;
        video.muted = true;
        video.playsInline = true;
        video.preload = "metadata";
        preview.append(video);
        const play = document.createElement("span");
        play.className = "attachment-play";
        play.setAttribute("aria-hidden", "true");
        play.textContent = "▶";
        preview.append(play);
      } else {
        const image = document.createElement("img");
        image.src = objectUrl;
        image.alt = file.name;
        preview.append(image);
      }

      const info = document.createElement("span");
      info.className = "attachment-info";
      const name = document.createElement("span");
      name.className = "attachment-name";
      name.textContent = file.name;
      const meta = document.createElement("span");
      meta.className = "attachment-meta";
      meta.textContent = `${formatBytes(file.size || 0)} · ${formatLabel(file, kind)}`;
      info.append(name, meta);

      open.append(preview, info);
      open.addEventListener("click", () => openLocalPreview(file, objectUrl));

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "attachment-delete";
      remove.textContent = "×";
      remove.title = config.messages.remove;
      remove.setAttribute("aria-label", `${config.messages.remove}: ${file.name}`);
      remove.addEventListener("click", () => {
        const next = selected.filter((_, fileIndex) => fileIndex !== index);
        rebuildFileList(next);
      });

      item.append(open, remove);
      selection.append(item);
    });
  };

  const rebuildFileList = (files) => {
    selected = Array.from(files);
    cancelInputClear();
    syncInputFiles();
    refresh();
    updateRequired();
    if (supportsDataTransfer) input.value = "";
  };

  const fileKey = (file) =>
    `${file.name || ""}::${file.size || 0}::${file.lastModified || 0}`;

  const syncInputFiles = () => {
    if (typeof DataTransfer === "undefined") {
      if (!selected.length) input.value = "";
      return;
    }
    const transfer = new DataTransfer();
    selected.forEach((file) => transfer.items.add(file));
    syncingInput = true;
    try {
      input.files = transfer.files;
    } catch (error) {
      // The browser does not allow assigning the FileList; keep the native list.
    } finally {
      syncingInput = false;
    }
  };

  const refresh = () => {
    renderSelection();
    updateQuota();
    validate();
  };

  const updateRequired = () => {
    if (!requiredOnLoad) return;
    input.required = selected.length === 0;
  };

  const showPreparing = () => {
    if (status) {
      status.hidden = false;
      input.disabled = true;
    }
  };

  const hidePreparing = () => {
    if (status) {
      status.hidden = true;
      input.disabled = false;
    }
  };

  const cancelInputClear = () => {
    if (clearTimer) {
      window.clearTimeout(clearTimer);
      clearTimer = null;
    }
    hidePreparing();
  };

  const scheduleInputClear = () => {
    if (!supportsDataTransfer) return;
    if (clearTimer) window.clearTimeout(clearTimer);
    showPreparing();
    clearTimer = window.setTimeout(() => {
      clearTimer = null;
      input.value = "";
      hidePreparing();
      updateRequired();
    }, 500);
  };

  const addFiles = (files) => {
    const keys = new Set(selected.map(fileKey));
    let added = false;
    files.forEach((file) => {
      const key = fileKey(file);
      if (!keys.has(key)) {
        selected.push(file);
        keys.add(key);
        added = true;
      }
    });
    if (!added) return;

    syncInputFiles();
    refresh();
    updateRequired();
    scheduleInputClear();
  };

  const readSelection = () => {
    if (syncingInput) return;
    const incoming = Array.from(input.files || []);
    if (!incoming.length) return;

    if (typeof DataTransfer === "undefined") {
      selected = incoming;
      refresh();
      updateRequired();
      return;
    }

    addFiles(incoming);
  };

  input.addEventListener("change", readSelection);

  if (dropzone) {
    ["dragenter", "dragover"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.remove("is-dragover");
      });
    });
    dropzone.addEventListener("drop", (event) => {
      const files = Array.from(event.dataTransfer?.files || []);
      if (files.length) {
        if (typeof DataTransfer === "undefined") {
          selected = files;
          refresh();
          updateRequired();
        } else {
          addFiles(files);
        }
      }
    });
  }

  if (form) {
    form.addEventListener("submit", (event) => {
      const submitter = event.submitter;
      cancelInputClear();
      if (submitter && submitter.hasAttribute("formnovalidate")) {
        if (supportsDataTransfer) input.value = "";
        return;
      }
      if (!validate()) {
        event.preventDefault();
        input.reportValidity();
        input.focus();
        if (supportsDataTransfer) input.value = "";
        return;
      }
      syncInputFiles();
    });
    form.addEventListener("reset", () => {
      cancelInputClear();
      window.setTimeout(() => {
        selected = [];
        refresh();
        updateRequired();
        input.value = "";
      }, 0);
    });
  }

  updateQuota();
  updateRequired();
}
