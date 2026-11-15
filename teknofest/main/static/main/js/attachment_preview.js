const dialog = document.getElementById("attachment-preview-dialog");
const supportsDialog = dialog && typeof dialog.showModal === "function";

if (supportsDialog) {
  const body = dialog.querySelector("[data-preview-body]");
  const title = dialog.querySelector("[data-preview-title]");
  const download = dialog.querySelector("[data-preview-download]");
  const closeButton = dialog.querySelector("[data-preview-close]");
  let trigger = null;

  const clearMedia = () => {
    body.querySelectorAll("video").forEach((video) => {
      video.pause();
      video.removeAttribute("src");
      video.load();
    });
    body.replaceChildren();
  };

  const openPreview = (link) => {
    const kind = link.dataset.previewKind;
    const url = link.dataset.previewUrl;
    const name = link.dataset.previewTitle || "";

    trigger = link;
    title.textContent = name;
    download.href = link.dataset.downloadUrl || url;
    download.removeAttribute("download");
    clearMedia();

    if (kind === "video") {
      const video = document.createElement("video");
      video.className = "attachment-preview-media";
      video.controls = true;
      video.autoplay = true;
      video.playsInline = true;
      video.preload = "metadata";
      video.src = url;
      body.append(video);
    } else {
      const image = document.createElement("img");
      image.className = "attachment-preview-media";
      image.src = url;
      image.alt = name;
      body.append(image);
    }

    document.body.classList.add("attachment-preview-open");
    dialog.showModal();
    closeButton?.focus();
  };

  document.querySelectorAll("[data-attachment-preview]").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (event.defaultPrevented) return;
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      event.preventDefault();
      openPreview(link);
    });
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });

  closeButton?.addEventListener("click", () => dialog.close());

  dialog.addEventListener("close", () => {
    clearMedia();
    document.body.classList.remove("attachment-preview-open");
    if (trigger) {
      trigger.focus();
      trigger = null;
    }
  });
}
