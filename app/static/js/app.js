/**
 * Shared admin UI helpers: history navigation, slugify, clipboard.
 */
(function () {
  "use strict";

  function slugify(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 63);
  }

  function bindSlug(nameId, slugId) {
    const name = document.getElementById(nameId);
    const slug = document.getElementById(slugId);
    if (!name || !slug) {
      return;
    }
    let auto = !slug.value;
    name.addEventListener("input", function () {
      if (auto) {
        slug.value = slugify(name.value);
      }
    });
    slug.addEventListener("input", function () {
      auto = slug.value.length === 0;
    });
  }

  async function copyText(text) {
    if (!text) {
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
    } catch (error) {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
  }

  function downloadText(filename, text) {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  function resolveTheme() {
    const theme = document.documentElement.getAttribute("data-theme");
    if (theme === "dark" || theme === "welight") {
      return theme;
    }
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
    return "welight";
  }

  document.addEventListener("DOMContentLoaded", function () {
    const back = document.getElementById("nav-back");
    const forward = document.getElementById("nav-forward");
    if (back) {
      back.addEventListener("click", function () {
        window.history.back();
      });
    }
    if (forward) {
      forward.addEventListener("click", function () {
        window.history.forward();
      });
    }
    document.querySelectorAll(".js-copy").forEach(function (button) {
      button.addEventListener("click", function () {
        const from = button.getAttribute("data-copy-from");
        const node = from ? document.getElementById(from) : null;
        const text = node
          ? (node.value || node.textContent || "").trim()
          : button.getAttribute("data-copy") || "";
        copyText(text);
        const icon = button.querySelector("i");
        if (icon) {
          icon.className = "bi bi-clipboard-check";
          setTimeout(function () {
            icon.className = "bi bi-clipboard";
          }, 1200);
        }
      });
    });
    document.querySelectorAll(".js-confirm-form").forEach(bindConfirmForm);
    bindConfirmModal();
    document.querySelectorAll(".js-download-text").forEach(function (button) {
      button.addEventListener("click", function () {
        const from = button.getAttribute("data-from");
        const name = button.getAttribute("data-filename") || "keys.txt";
        const node = document.getElementById(from);
        downloadText(name, node ? node.value : "");
      });
    });
    document.querySelectorAll(".app-toast").forEach(function (toast) {
      let hiding = false;
      function hide() {
        if (hiding) {
          return;
        }
        hiding = true;
        toast.classList.add("is-leaving");
        setTimeout(function () {
          toast.remove();
        }, 280);
      }
      const closer = toast.querySelector(".app-toast-close");
      if (closer) {
        closer.addEventListener("click", hide);
      }
      setTimeout(hide, 5000);
    });
    bindSidebar();
    bindFileFields();
    bindPasswordToggles();
    enhanceSelects(document);
    observeSelects();
  });

  function isCompactNav() {
    return window.matchMedia("(orientation: portrait), (max-width: 960px)").matches;
  }

  function bindSidebar() {
    const toggle = document.getElementById("sidebar-toggle");
    const sidebar = document.getElementById("app-sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (!toggle || !sidebar) {
      return;
    }
    const icon = toggle.querySelector("i");
    const openLabel = toggle.getAttribute("data-open-label") || "";
    const closeLabel = toggle.getAttribute("data-close-label") || "";

    function setOpen(open) {
      if (!isCompactNav()) {
        open = false;
      }
      document.body.classList.toggle("sidebar-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      sidebar.setAttribute("aria-hidden", isCompactNav() && !open ? "true" : "false");
      if (icon) {
        icon.className = open ? "bi bi-x-lg" : "bi bi-list";
      }
      const label = open ? closeLabel : openLabel;
      if (label) {
        toggle.setAttribute("aria-label", label);
        toggle.setAttribute("title", label);
      }
    }

    toggle.addEventListener("click", function () {
      setOpen(!document.body.classList.contains("sidebar-open"));
    });
    if (backdrop) {
      backdrop.addEventListener("click", function () {
        setOpen(false);
      });
    }
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && document.body.classList.contains("sidebar-open")) {
        setOpen(false);
      }
    });
    window.addEventListener("resize", function () {
      if (!isCompactNav()) {
        setOpen(false);
      }
    });
    setOpen(false);
  }

  function bindPasswordToggles() {
    document.querySelectorAll(".password-toggle").forEach(function (button) {
      button.addEventListener("click", function () {
        const field = button.closest(".password-field");
        const input = field ? field.querySelector("input") : null;
        if (!input) {
          return;
        }
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        const icon = button.querySelector("i");
        if (icon) {
          icon.className = show ? "bi bi-eye-slash" : "bi bi-eye";
        }
        const label = show
          ? button.getAttribute("data-hide")
          : button.getAttribute("data-show");
        if (label) {
          button.setAttribute("aria-label", label);
        }
      });
    });
  }

  function bindFileFields() {
    document.querySelectorAll(".file-field").forEach(function (field) {
      const input = field.querySelector("input[type='file']");
      const name = field.querySelector(".file-field-name");
      if (!input || !name) {
        return;
      }
      const empty = name.getAttribute("data-empty") || "";
      input.addEventListener("change", function () {
        const file = input.files && input.files[0];
        name.textContent = file ? file.name : empty;
      });
    });
  }

  function selectedLabel(select) {
    const opt = select.options[select.selectedIndex];
    return opt ? opt.textContent : "";
  }

  function closeAllSelects(except) {
    document.querySelectorAll(".cselect.is-open").forEach(function (wrap) {
      if (wrap !== except) {
        wrap.classList.remove("is-open");
      }
    });
  }

  function placeMenu(wrap) {
    const toggle = wrap.querySelector(".cselect-toggle");
    const menu = wrap.querySelector(".cselect-menu");
    if (!toggle || !menu) {
      return;
    }
    const rect = toggle.getBoundingClientRect();
    const width = Math.max(rect.width, 160);
    menu.style.left = rect.left + "px";
    menu.style.width = width + "px";
    const spaceBelow = window.innerHeight - rect.bottom;
    if (spaceBelow < 200 && rect.top > spaceBelow) {
      menu.style.top = "auto";
      menu.style.bottom = window.innerHeight - rect.top + 4 + "px";
      menu.style.maxHeight = Math.min(260, rect.top - 12) + "px";
    } else {
      menu.style.bottom = "auto";
      menu.style.top = rect.bottom + 4 + "px";
      menu.style.maxHeight = Math.min(260, spaceBelow - 12) + "px";
    }
  }

  function fillMenu(select, menu) {
    menu.innerHTML = "";
    Array.prototype.forEach.call(select.options, function (opt) {
      if (opt.hidden) {
        return;
      }
      const item = document.createElement("button");
      item.type = "button";
      item.className = "cselect-option";
      item.textContent = opt.textContent;
      item.dataset.value = opt.value;
      if (opt.disabled) {
        item.disabled = true;
      }
      if (opt.selected) {
        item.classList.add("is-selected");
      }
      item.addEventListener("click", function () {
        if (opt.disabled) {
          return;
        }
        select.value = opt.value;
        select.dispatchEvent(new Event("input", { bubbles: true }));
        select.dispatchEvent(new Event("change", { bubbles: true }));
        closeAllSelects();
      });
      menu.appendChild(item);
    });
  }

  function enhanceSelect(select) {
    if (select.dataset.enhanced === "1") {
      return;
    }
    select.dataset.enhanced = "1";
    const wrap = document.createElement("div");
    wrap.className = "cselect";
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    select.classList.add("cselect-native");
    select.tabIndex = -1;

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "form-select cselect-toggle";
    const label = document.createElement("span");
    label.className = "cselect-toggle-label";
    label.textContent = selectedLabel(select);
    toggle.appendChild(label);
    wrap.appendChild(toggle);

    const menu = document.createElement("div");
    menu.className = "cselect-menu";
    wrap.appendChild(menu);

    function sync() {
      label.textContent = selectedLabel(select);
      fillMenu(select, menu);
      wrap.classList.toggle("d-none", select.classList.contains("d-none"));
      toggle.disabled = select.disabled;
    }

    sync();

    toggle.addEventListener("click", function (event) {
      event.preventDefault();
      if (select.disabled) {
        return;
      }
      const open = !wrap.classList.contains("is-open");
      closeAllSelects();
      if (open) {
        wrap.classList.add("is-open");
        placeMenu(wrap);
      }
    });

    select.addEventListener("change", function () {
      label.textContent = selectedLabel(select);
      fillMenu(select, menu);
    });

    const observer = new MutationObserver(sync);
    observer.observe(select, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["hidden", "disabled", "selected", "class"]
    });
  }

  function enhanceSelects(root) {
    (root || document).querySelectorAll("select.form-select").forEach(enhanceSelect);
  }

  function observeSelects() {
    document.addEventListener("click", function (event) {
      if (!event.target.closest(".cselect")) {
        closeAllSelects();
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeAllSelects();
      }
    });
    window.addEventListener("resize", function () {
      document.querySelectorAll(".cselect.is-open").forEach(placeMenu);
    });
    window.addEventListener("scroll", function () {
      document.querySelectorAll(".cselect.is-open").forEach(placeMenu);
    }, true);
    const observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          if (node.nodeType !== 1) {
            return;
          }
          if (node.matches && node.matches("select.form-select")) {
            enhanceSelect(node);
          }
          if (node.querySelectorAll) {
            enhanceSelects(node);
          }
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  let openConfirmModal = function () {};

  function bindConfirmForm(form) {
    if (form.dataset.confirmBound === "1") {
      return;
    }
    form.dataset.confirmBound = "1";
    form.addEventListener("submit", function (event) {
      if (form.dataset.confirmed === "1") {
        form.dataset.confirmed = "";
        return;
      }
      const message = form.getAttribute("data-confirm") || "";
      if (!message) {
        return;
      }
      event.preventDefault();
      openConfirmModal(form);
    });
  }

  function bindConfirmModal() {
    const modal = document.getElementById("confirm-modal");
    if (!modal) {
      return;
    }
    const title = document.getElementById("confirm-modal-title");
    const body = document.getElementById("confirm-modal-body");
    const okBtn = document.getElementById("confirm-modal-ok");
    const dialog = modal.querySelector(".app-modal-dialog");
    const okLabel = okBtn ? okBtn.querySelector("span") : null;
    const defaultOk = okBtn ? okBtn.getAttribute("data-default-label") || "" : "";
    const defaultTitle = title ? title.textContent : "";
    let pendingForm = null;
    let lastFocus = null;

    function closeModal() {
      pendingForm = null;
      modal.hidden = true;
      document.body.classList.remove("confirm-open");
      if (lastFocus && lastFocus.focus) {
        lastFocus.focus();
      }
      lastFocus = null;
    }

    openConfirmModal = function (form) {
      pendingForm = form;
      lastFocus = document.activeElement;
      if (title) {
        title.textContent = form.getAttribute("data-confirm-title") || defaultTitle;
      }
      if (body) {
        body.textContent = form.getAttribute("data-confirm") || "";
      }
      if (okLabel) {
        okLabel.textContent = form.getAttribute("data-confirm-ok") || defaultOk;
      }
      modal.hidden = false;
      document.body.classList.add("confirm-open");
      if (dialog) {
        dialog.focus();
      }
    };

    modal.querySelectorAll("[data-confirm-dismiss]").forEach(function (node) {
      node.addEventListener("click", closeModal);
    });
    if (okBtn) {
      okBtn.addEventListener("click", function () {
        const form = pendingForm;
        closeModal();
        if (!form) {
          return;
        }
        form.dataset.confirmed = "1";
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          form.submit();
        }
      });
    }
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !modal.hidden) {
        event.preventDefault();
        closeModal();
      }
    });
  }

  window.VerifyLite = {
    bindSlug: bindSlug,
    slugify: slugify,
    copyText: copyText,
    downloadText: downloadText,
    resolveTheme: resolveTheme
  };
})();
