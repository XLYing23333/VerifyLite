/**
 * Bidirectional GUI <-> JSON editor for verification config.
 */
(function () {
  "use strict";

  const BLOB_VALUE = /^\{\{blob_url:([^}]+)\}\}$/;
  const UNLIMITED = new Set([
    "",
    "inf",
    "infty",
    "infinity",
    "∞",
    "-1",
    "none",
    "null",
    "unlimited"
  ]);

  function numberOrNull(value) {
    if (value === "" || value === null || value === undefined) {
      return null;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function usesOrNull(value) {
    if (value === null || value === undefined) {
      return null;
    }
    const text = String(value).trim().toLowerCase();
    if (UNLIMITED.has(text)) {
      return null;
    }
    const parsed = Number(text);
    if (!Number.isFinite(parsed) || parsed < 0) {
      return null;
    }
    return Math.trunc(parsed);
  }

  function displayMaxUses(value) {
    const parsed = usesOrNull(value);
    return parsed === null ? "infty" : String(parsed);
  }

  function toDatetimeLocal(value) {
    if (!value) {
      return "";
    }
    const text = String(value).replace(" ", "T");
    return text.slice(0, 16);
  }

  function fromDatetimeLocal(value) {
    if (!value) {
      return null;
    }
    return String(value).replace("T", " ") + ":00";
  }

  function detectKind(value) {
    if (typeof value === "number") {
      return "number";
    }
    if (typeof value === "string" && BLOB_VALUE.test(value)) {
      return "blob";
    }
    return "text";
  }

  function displayValue(value) {
    if (value === null || value === undefined) {
      return "";
    }
    if (typeof value === "object") {
      return JSON.stringify(value);
    }
    return String(value);
  }

  function parseStoredValue(kind, raw, blobName) {
    if (kind === "blob") {
      return blobName ? "{{blob_url:" + blobName + "}}" : "";
    }
    if (kind === "number") {
      const parsed = Number(raw);
      return Number.isFinite(parsed) ? parsed : raw;
    }
    const trimmed = String(raw || "").trim();
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try {
        return JSON.parse(trimmed);
      } catch (error) {
        return raw;
      }
    }
    return raw;
  }

  function extraObject(code) {
    const root = document.querySelector('.extra-gui[data-code="' + code + '"]');
    const extra = {};
    if (!root) {
      return extra;
    }
    root.querySelectorAll(".extra-row").forEach(function (row) {
      const key = (row.querySelector(".extra-key").value || "").trim();
      if (!key || key === "code" || key === "msg") {
        return;
      }
      const kind = row.querySelector(".extra-kind").value;
      const blobName = row.querySelector(".extra-blob").value;
      const raw = row.querySelector(".extra-value").value;
      extra[key] = parseStoredValue(kind, raw, blobName);
    });
    return extra;
  }

  function syncRowKind(row) {
    const kind = row.querySelector(".extra-kind").value;
    const valueInput = row.querySelector(".extra-value");
    const blobSelect = row.querySelector(".extra-blob");
    const blobMode = kind === "blob";
    valueInput.classList.toggle("d-none", blobMode);
    blobSelect.classList.toggle("d-none", !blobMode);
    valueInput.disabled = blobMode;
    blobSelect.disabled = !blobMode;
  }

  function buildRow(labels, blobs, field) {
    const row = document.createElement("div");
    row.className = "extra-row";

    const keyInput = document.createElement("input");
    keyInput.className = "form-control extra-key";
    keyInput.type = "text";
    keyInput.placeholder = labels.key;
    keyInput.value = field.key || "";

    const kindSelect = document.createElement("select");
    kindSelect.className = "form-select extra-kind";
    [
      ["text", labels.text],
      ["number", labels.number],
      ["blob", labels.blob]
    ].forEach(function (pair) {
      const option = document.createElement("option");
      option.value = pair[0];
      option.textContent = pair[1];
      kindSelect.appendChild(option);
    });
    kindSelect.value = field.kind || "text";

    const valueInput = document.createElement("input");
    valueInput.className = "form-control extra-value";
    valueInput.type = field.kind === "number" ? "number" : "text";
    valueInput.placeholder = labels.value;
    valueInput.value = field.value || "";

    const blobSelect = document.createElement("select");
    blobSelect.className = "form-select extra-blob";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = blobs.length ? labels.pickBlob : labels.noBlobs;
    blobSelect.appendChild(placeholder);
    blobs.forEach(function (name) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      blobSelect.appendChild(option);
    });
    blobSelect.value = field.blob || "";

    const removeBtn = document.createElement("button");
    removeBtn.className = "btn btn-sm btn-outline-danger icon-only extra-remove";
    removeBtn.type = "button";
    removeBtn.title = labels.remove;
    removeBtn.setAttribute("aria-label", labels.remove);
    removeBtn.innerHTML = '<i class="bi bi-trash"></i>';

    row.appendChild(keyInput);
    row.appendChild(kindSelect);
    row.appendChild(valueInput);
    row.appendChild(blobSelect);
    row.appendChild(removeBtn);
    syncRowKind(row);
    return row;
  }

  function fieldsFromExtra(extra) {
    const fields = [];
    Object.keys(extra || {}).forEach(function (key) {
      const value = extra[key];
      const kind = detectKind(value);
      const blobMatch = typeof value === "string" ? value.match(BLOB_VALUE) : null;
      fields.push({
        key: key,
        kind: kind,
        value: kind === "blob" ? "" : displayValue(value),
        blob: blobMatch ? blobMatch[1] : ""
      });
    });
    return fields;
  }

  function renderExtras(code, extra, labels, blobs) {
    const root = document.querySelector('.extra-gui[data-code="' + code + '"]');
    if (!root) {
      return;
    }
    root.innerHTML = "";
    fieldsFromExtra(extra).forEach(function (field) {
      root.appendChild(buildRow(labels, blobs, field));
    });
  }

  function readForm(resultCodes) {
    const responses = {};
    resultCodes.forEach(function (code) {
      const extra = extraObject(code);
      responses[code] = Object.assign({}, extra, {
        code: numberOrNull(document.getElementById("resp-" + code + "-code").value) || 0,
        msg: document.getElementById("resp-" + code + "-msg").value
      });
    });
    return {
      bind_hwid: document.getElementById("bind_hwid").checked,
      defaults: {
        ttl_seconds: numberOrNull(document.getElementById("ttl_seconds").value),
        max_uses: usesOrNull(document.getElementById("max_uses").value),
        valid_from: fromDatetimeLocal(document.getElementById("valid_from").value),
        valid_until: fromDatetimeLocal(document.getElementById("valid_until").value)
      },
      responses: responses
    };
  }

  function fillForm(config, resultCodes, labels, blobs) {
    const defaults = config.defaults || {};
    document.getElementById("bind_hwid").checked = Boolean(config.bind_hwid);
    document.getElementById("ttl_seconds").value =
      defaults.ttl_seconds === null || defaults.ttl_seconds === undefined ? "" : defaults.ttl_seconds;
    document.getElementById("max_uses").value = displayMaxUses(defaults.max_uses);
    document.getElementById("valid_from").value = toDatetimeLocal(defaults.valid_from);
    document.getElementById("valid_until").value = toDatetimeLocal(defaults.valid_until);
    const responses = config.responses || {};
    resultCodes.forEach(function (code) {
      const item = responses[code] || {};
      document.getElementById("resp-" + code + "-code").value =
        item.code === undefined ? 0 : item.code;
      document.getElementById("resp-" + code + "-msg").value = item.msg || "";
      const extra = {};
      Object.keys(item).forEach(function (key) {
        if (key !== "code" && key !== "msg") {
          extra[key] = item[key];
        }
      });
      renderExtras(code, extra, labels, blobs);
    });
  }

  function setJsonError(visible) {
    const node = document.getElementById("json-error");
    if (!node) {
      return;
    }
    node.classList.toggle("d-none", !visible);
  }

  function init(options) {
    const resultCodes = options.resultCodes || [];
    const labels = options.labels || {};
    const blobs = options.blobs || [];
    const jsonBox = document.getElementById("config_json");
    if (!jsonBox) {
      return;
    }
    document.getElementById("valid_from").value = toDatetimeLocal(options.validFrom);
    document.getElementById("valid_until").value = toDatetimeLocal(options.validUntil);

    const initialExtras = options.extras || {};
    resultCodes.forEach(function (code) {
      renderExtras(code, initialExtras[code] || {}, labels, blobs);
    });

    let syncing = false;

    function formToJson() {
      if (syncing) {
        return;
      }
      try {
        const data = readForm(resultCodes);
        syncing = true;
        jsonBox.value = JSON.stringify(data, null, 2);
        jsonBox.classList.remove("is-invalid");
        setJsonError(false);
      } catch (error) {
        jsonBox.classList.add("is-invalid");
        setJsonError(true);
      } finally {
        syncing = false;
      }
    }

    function jsonToForm() {
      if (syncing) {
        return;
      }
      try {
        const parsed = JSON.parse(jsonBox.value);
        if (!parsed || typeof parsed !== "object") {
          throw new Error("shape");
        }
        syncing = true;
        fillForm(parsed, resultCodes, labels, blobs);
        jsonBox.classList.remove("is-invalid");
        setJsonError(false);
      } catch (error) {
        jsonBox.classList.add("is-invalid");
        setJsonError(true);
      } finally {
        syncing = false;
      }
    }

    document.querySelectorAll(".js-sync").forEach(function (node) {
      node.addEventListener("input", formToJson);
      node.addEventListener("change", formToJson);
    });
    jsonBox.addEventListener("input", jsonToForm);

    document.querySelectorAll(".js-extra-add").forEach(function (button) {
      button.addEventListener("click", function () {
        const code = button.getAttribute("data-code");
        const root = document.querySelector('.extra-gui[data-code="' + code + '"]');
        if (!root) {
          return;
        }
        root.appendChild(buildRow(labels, blobs, { kind: "text" }));
        formToJson();
      });
    });

    document.addEventListener("click", function (event) {
      const remove = event.target.closest(".extra-remove");
      if (!remove) {
        return;
      }
      const row = remove.closest(".extra-row");
      if (row) {
        row.remove();
        formToJson();
      }
    });

    document.addEventListener("change", function (event) {
      const row = event.target.closest(".extra-row");
      if (!row) {
        return;
      }
      if (event.target.classList.contains("extra-kind")) {
        const valueInput = row.querySelector(".extra-value");
        valueInput.type = event.target.value === "number" ? "number" : "text";
        syncRowKind(row);
      }
      formToJson();
    });

    document.addEventListener("input", function (event) {
      if (event.target.closest(".extra-row")) {
        formToJson();
      }
    });
  }

  window.VerifyLiteDual = { init: init };
})();
