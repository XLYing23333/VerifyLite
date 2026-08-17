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

  function pickerCopy() {
    const root = document.documentElement;
    const zh = String(root.lang || "en").toLowerCase().indexOf("zh") === 0;
    return {
      zh: zh,
      monthsEn: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
      monthsShortEn: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
      weekdays: zh ? ["日", "一", "二", "三", "四", "五", "六"] : ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"],
      clear: root.getAttribute("data-picker-clear") || (zh ? "清除" : "Clear"),
      now: root.getAttribute("data-picker-now") || (zh ? "此刻" : "Now"),
      empty: root.getAttribute("data-picker-placeholder") || (zh ? "选择日期时间" : "Select date and time")
    };
  }

  function pad2(value) {
    return String(value).padStart(2, "0");
  }

  function parseDateTimeLocal(value) {
    const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!match) {
      return null;
    }
    return new Date(
      Number(match[1]),
      Number(match[2]) - 1,
      Number(match[3]),
      Number(match[4]),
      Number(match[5]),
      0
    );
  }

  function toDateTimeLocal(date) {
    return (
      date.getFullYear() +
      "-" +
      pad2(date.getMonth() + 1) +
      "-" +
      pad2(date.getDate()) +
      "T" +
      pad2(date.getHours()) +
      ":" +
      pad2(date.getMinutes())
    );
  }

  function formatDateTimeDisplay(value) {
    const copy = pickerCopy();
    const date = parseDateTimeLocal(value);
    if (!date) {
      return copy.empty;
    }
    const time = pad2(date.getHours()) + ":" + pad2(date.getMinutes());
    if (copy.zh) {
      return date.getFullYear() + "年" + (date.getMonth() + 1) + "月" + date.getDate() + "日 " + time;
    }
    return copy.monthsShortEn[date.getMonth()] + " " + date.getDate() + ", " + date.getFullYear() + ", " + time;
  }

  function closeAllDateTimes(except) {
    document.querySelectorAll(".cdtp.is-open").forEach(function (wrap) {
      if (wrap !== except) {
        wrap.classList.remove("is-open");
      }
    });
  }

  function placeDateMenu(wrap) {
    const toggle = wrap.querySelector(".cdtp-toggle");
    const menu = wrap.querySelector(".cdtp-menu");
    if (!toggle || !menu) {
      return;
    }
    const rect = toggle.getBoundingClientRect();
    const width = Math.max(rect.width, 320);
    menu.style.width = width + "px";
    menu.style.left = Math.min(rect.left, window.innerWidth - width - 8) + "px";
    const spaceBelow = window.innerHeight - rect.bottom;
    const estimated = 360;
    if (spaceBelow < estimated && rect.top > spaceBelow) {
      menu.style.top = "auto";
      menu.style.bottom = window.innerHeight - rect.top + 4 + "px";
      menu.style.maxHeight = Math.min(420, rect.top - 12) + "px";
    } else {
      menu.style.bottom = "auto";
      menu.style.top = rect.bottom + 4 + "px";
      menu.style.maxHeight = Math.min(420, spaceBelow - 12) + "px";
    }
  }

  function interceptInputValue(input, onSet) {
    if (input.dataset.valueIntercept === "1") {
      return;
    }
    input.dataset.valueIntercept = "1";
    const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
    Object.defineProperty(input, "value", {
      configurable: true,
      enumerable: true,
      get: function () {
        return desc.get.call(this);
      },
      set: function (next) {
        desc.set.call(this, next);
        onSet();
      }
    });
  }

  function enhanceDateTime(input) {
    if (input.dataset.enhanced === "1" || input.type !== "datetime-local") {
      return;
    }
    input.dataset.enhanced = "1";
    const wrap = document.createElement("div");
    wrap.className = "cdtp";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    input.classList.add("cdtp-native");
    input.tabIndex = -1;

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "form-control cdtp-toggle";
    const label = document.createElement("span");
    label.className = "cdtp-label";
    toggle.appendChild(label);
    const icon = document.createElement("i");
    icon.className = "bi bi-calendar3";
    icon.setAttribute("aria-hidden", "true");
    toggle.appendChild(icon);
    wrap.appendChild(toggle);

    const menu = document.createElement("div");
    menu.className = "cdtp-menu";
    wrap.appendChild(menu);

    const view = { year: 0, month: 0, hour: 0, minute: 0, day: 1 };

    function currentDate() {
      return parseDateTimeLocal(input.value) || new Date();
    }

    function syncLabel() {
      const value = input.value;
      label.textContent = formatDateTimeDisplay(value);
      wrap.classList.toggle("is-empty", !value);
    }

    function writeValue(date) {
      const next = toDateTimeLocal(date);
      const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
      desc.set.call(input, next);
      syncLabel();
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function loadViewFromValue() {
      const date = currentDate();
      view.year = date.getFullYear();
      view.month = date.getMonth();
      view.day = date.getDate();
      view.hour = date.getHours();
      view.minute = date.getMinutes();
    }

    function selectedDate() {
      const dim = new Date(view.year, view.month + 1, 0).getDate();
      if (view.day > dim) {
        view.day = dim;
      }
      return new Date(view.year, view.month, view.day, view.hour, view.minute, 0);
    }

    function renderMenu() {
      const copy = pickerCopy();
      const monthLabel = copy.zh
        ? (view.month + 1) + "月"
        : copy.monthsEn[view.month];
      const first = new Date(view.year, view.month, 1);
      const startWeekday = first.getDay();
      const daysInMonth = new Date(view.year, view.month + 1, 0).getDate();
      const prevDays = new Date(view.year, view.month, 0).getDate();
      const today = new Date();
      const selected = parseDateTimeLocal(input.value);
      let html = "";
      html += '<div class="cdtp-head">';
      html += '<button type="button" class="btn btn-sm btn-outline-secondary icon-only cdtp-nav" data-delta="-1" aria-label="Previous month"><i class="bi bi-chevron-left"></i></button>';
      html += '<div class="cdtp-month-wrap">';
      html += '<input class="form-control cdtp-year" type="number" min="1" max="9999" value="' + view.year + '">';
      html += '<span class="cdtp-month-label">' + monthLabel + "</span>";
      html += "</div>";
      html += '<button type="button" class="btn btn-sm btn-outline-secondary icon-only cdtp-nav" data-delta="1" aria-label="Next month"><i class="bi bi-chevron-right"></i></button>';
      html += "</div>";
      html += '<div class="cdtp-weekdays">';
      copy.weekdays.forEach(function (name) {
        html += "<span>" + name + "</span>";
      });
      html += '</div><div class="cdtp-days">';
      const cells = [];
      for (let i = 0; i < startWeekday; i += 1) {
        cells.push({
          day: prevDays - startWeekday + i + 1,
          outside: true,
          year: view.month === 0 ? view.year - 1 : view.year,
          month: view.month === 0 ? 11 : view.month - 1
        });
      }
      for (let day = 1; day <= daysInMonth; day += 1) {
        cells.push({ day: day, outside: false, year: view.year, month: view.month });
      }
      let extra = 1;
      while (cells.length % 7 !== 0) {
        cells.push({
          day: extra,
          outside: true,
          year: view.month === 11 ? view.year + 1 : view.year,
          month: view.month === 11 ? 0 : view.month + 1
        });
        extra += 1;
      }
      cells.forEach(function (cell) {
        const classes = ["cdtp-day"];
        if (cell.outside) {
          classes.push("is-outside");
        }
        if (
          cell.year === today.getFullYear() &&
          cell.month === today.getMonth() &&
          cell.day === today.getDate()
        ) {
          classes.push("is-today");
        }
        if (
          selected &&
          cell.year === selected.getFullYear() &&
          cell.month === selected.getMonth() &&
          cell.day === selected.getDate()
        ) {
          classes.push("is-selected");
        }
        html +=
          '<button type="button" class="' +
          classes.join(" ") +
          '" data-year="' +
          cell.year +
          '" data-month="' +
          cell.month +
          '" data-day="' +
          cell.day +
          '">' +
          cell.day +
          "</button>";
      });
      html += "</div>";
      html += '<div class="cdtp-time">';
      html += '<input class="form-control cdtp-hour" type="number" min="0" max="23" value="' + pad2(view.hour) + '">';
      html += '<span class="cdtp-time-sep">:</span>';
      html += '<input class="form-control cdtp-minute" type="number" min="0" max="59" value="' + pad2(view.minute) + '">';
      html += "</div>";
      html += '<div class="cdtp-foot">';
      html += '<button type="button" class="btn btn-sm btn-outline-secondary cdtp-clear">' + copy.clear + "</button>";
      html += '<button type="button" class="btn btn-sm btn-outline-secondary cdtp-now">' + copy.now + "</button>";
      html += "</div>";
      menu.innerHTML = html;
    }

    function openMenu() {
      loadViewFromValue();
      renderMenu();
      closeAllSelects();
      closeAllDateTimes();
      wrap.classList.add("is-open");
      placeDateMenu(wrap);
    }

    function applyDay(year, month, day) {
      view.year = year;
      view.month = month;
      view.day = day;
      writeValue(selectedDate());
      renderMenu();
      placeDateMenu(wrap);
    }

    toggle.addEventListener("click", function (event) {
      event.preventDefault();
      if (input.disabled) {
        return;
      }
      if (wrap.classList.contains("is-open")) {
        wrap.classList.remove("is-open");
        return;
      }
      openMenu();
    });

    menu.addEventListener("click", function (event) {
      const nav = event.target.closest(".cdtp-nav");
      if (nav) {
        const delta = Number(nav.getAttribute("data-delta") || 0);
        const next = new Date(view.year, view.month + delta, 1);
        view.year = next.getFullYear();
        view.month = next.getMonth();
        renderMenu();
        placeDateMenu(wrap);
        return;
      }
      const dayBtn = event.target.closest(".cdtp-day");
      if (dayBtn) {
        applyDay(
          Number(dayBtn.getAttribute("data-year")),
          Number(dayBtn.getAttribute("data-month")),
          Number(dayBtn.getAttribute("data-day"))
        );
        return;
      }
      if (event.target.closest(".cdtp-clear")) {
        const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
        desc.set.call(input, "");
        syncLabel();
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
        wrap.classList.remove("is-open");
        return;
      }
      if (event.target.closest(".cdtp-now")) {
        const now = new Date();
        view.year = now.getFullYear();
        view.month = now.getMonth();
        view.day = now.getDate();
        view.hour = now.getHours();
        view.minute = now.getMinutes();
        writeValue(now);
        renderMenu();
        placeDateMenu(wrap);
      }
    });

    menu.addEventListener("change", function (event) {
      if (event.target.classList.contains("cdtp-year")) {
        const year = Number(event.target.value);
        if (Number.isFinite(year) && year >= 1 && year <= 9999) {
          view.year = year;
          writeValue(selectedDate());
          renderMenu();
          placeDateMenu(wrap);
        }
      }
    });

    menu.addEventListener("input", function (event) {
      if (event.target.classList.contains("cdtp-hour")) {
        let hour = Number(event.target.value);
        if (!Number.isFinite(hour)) {
          return;
        }
        hour = Math.max(0, Math.min(23, hour));
        view.hour = hour;
        writeValue(selectedDate());
      }
      if (event.target.classList.contains("cdtp-minute")) {
        let minute = Number(event.target.value);
        if (!Number.isFinite(minute)) {
          return;
        }
        minute = Math.max(0, Math.min(59, minute));
        view.minute = minute;
        writeValue(selectedDate());
      }
    });

    interceptInputValue(input, syncLabel);
    input.addEventListener("input", syncLabel);
    input.addEventListener("change", syncLabel);
    syncLabel();
  }

  function enhanceDateTimes(root) {
    (root || document).querySelectorAll("input[type='datetime-local']").forEach(enhanceDateTime);
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
    enhanceDateTimes(document);
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
      closeAllDateTimes();
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
      if (!event.target.closest(".cdtp")) {
        closeAllDateTimes();
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeAllSelects();
        closeAllDateTimes();
      }
    });
    window.addEventListener("resize", function () {
      document.querySelectorAll(".cselect.is-open").forEach(placeMenu);
      document.querySelectorAll(".cdtp.is-open").forEach(placeDateMenu);
    });
    window.addEventListener("scroll", function () {
      document.querySelectorAll(".cselect.is-open").forEach(placeMenu);
      document.querySelectorAll(".cdtp.is-open").forEach(placeDateMenu);
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
          if (node.matches && node.matches("input[type='datetime-local']")) {
            enhanceDateTime(node);
          }
          if (node.querySelectorAll) {
            enhanceSelects(node);
            enhanceDateTimes(node);
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
