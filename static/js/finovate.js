(function () {
  "use strict";

  var root = document.documentElement;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  var darkQuery = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");

  function prefersReducedMotion() {
    return !!(reduceMotion && reduceMotion.matches);
  }

  function csrfToken() {
    var input = document.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  // ---------------------------------------------------------------------
  // Toasts and flash messages
  // ---------------------------------------------------------------------
  function dismiss(el) {
    if (!el || el.classList.contains("is-leaving")) return;
    el.classList.add("is-leaving");
    window.setTimeout(function () { el.remove(); }, prefersReducedMotion() ? 0 : 220);
  }

  function toast(message, kind) {
    var region = document.querySelector("[data-toast-region]");
    if (!region) return;
    var el = document.createElement("div");
    el.className = "message toast " + (kind || "success");
    var text = document.createElement("span");
    text.textContent = message;
    var close = document.createElement("button");
    close.type = "button";
    close.className = "message-close";
    close.setAttribute("aria-label", "Dismiss");
    close.textContent = "×";
    close.addEventListener("click", function () { dismiss(el); });
    el.appendChild(text);
    el.appendChild(close);
    region.appendChild(el);
    // Errors stay until dismissed so they can't be missed.
    if (kind !== "error") window.setTimeout(function () { dismiss(el); }, 5000);
  }

  document.querySelectorAll("[data-dismiss-message]").forEach(function (btn) {
    btn.addEventListener("click", function () { dismiss(btn.closest("[data-message]")); });
  });

  // ---------------------------------------------------------------------
  // Theme
  // ---------------------------------------------------------------------
  var THEME_KEY = "finovate-theme";
  var themeButtons = document.querySelectorAll("[data-theme-toggle]");
  var themeSelect = document.getElementById("id_theme");

  function currentPref() {
    return root.getAttribute("data-theme-pref") || "system";
  }

  function resolve(pref) {
    if (pref === "dark" || pref === "light") return pref;
    return darkQuery && darkQuery.matches ? "dark" : "light";
  }

  function applyTheme(pref, animate) {
    var resolved = resolve(pref);
    if (animate && !prefersReducedMotion()) {
      root.classList.add("theme-transition");
      window.setTimeout(function () { root.classList.remove("theme-transition"); }, 300);
    }
    root.setAttribute("data-theme-pref", pref);
    root.setAttribute("data-theme", resolved);
    var label = resolved === "dark" ? "Switch to light mode" : "Switch to dark mode";
    themeButtons.forEach(function (btn) {
      btn.setAttribute("aria-pressed", resolved === "dark" ? "true" : "false");
      btn.setAttribute("aria-label", label);
      btn.setAttribute("title", label);
    });
    document.dispatchEvent(new CustomEvent("finovate:themechange", { detail: { theme: resolved, preference: pref } }));
  }

  function storeLocally(pref) {
    try { localStorage.setItem(THEME_KEY, pref); } catch (e) { /* private mode: account copy still applies */ }
  }

  function saveToAccount(pref) {
    var endpoint = document.body.getAttribute("data-theme-endpoint");
    if (!endpoint) return Promise.resolve(true);
    var body = new URLSearchParams();
    body.set("theme", pref);
    return fetch(endpoint, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString()
    }).then(function (res) {
      if (!res.ok) throw new Error("save failed");
      return res.json();
    }).then(function (data) {
      if (!data || !data.ok) throw new Error("save failed");
      return true;
    });
  }

  applyTheme(currentPref(), false);

  themeButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (btn.getAttribute("aria-busy") === "true") return;
      var previous = currentPref();
      var next = resolve(previous) === "dark" ? "light" : "dark";
      applyTheme(next, true);
      storeLocally(next);
      if (themeSelect) themeSelect.value = next;
      themeButtons.forEach(function (b) { b.setAttribute("aria-busy", "true"); });
      saveToAccount(next).catch(function () {
        // Don't pretend it was saved: put the old theme back and say so.
        applyTheme(previous, true);
        storeLocally(previous);
        if (themeSelect) themeSelect.value = previous;
        toast("Couldn't save your theme. Check your connection and try again.", "error");
      }).then(function () {
        themeButtons.forEach(function (b) { b.removeAttribute("aria-busy"); });
      });
    });
  });

  // Live preview when choosing in Settings; it's saved with the form.
  if (themeSelect) {
    themeSelect.addEventListener("change", function () { applyTheme(themeSelect.value, true); });
  }

  // Follow OS changes while the preference is "system".
  if (darkQuery) {
    var onSystemChange = function () { if (currentPref() === "system") applyTheme("system", true); };
    if (darkQuery.addEventListener) darkQuery.addEventListener("change", onSystemChange);
    else if (darkQuery.addListener) darkQuery.addListener(onSystemChange);
  }

  // ---------------------------------------------------------------------
  // Layers: mobile menu and modals
  // ---------------------------------------------------------------------
  var lastFocus = null;

  function focusables(container) {
    return Array.prototype.filter.call(
      container.querySelectorAll("a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])"),
      function (el) { return el.offsetParent !== null; }
    );
  }

  function openModal(modal) {
    if (!modal || modal.classList.contains("is-open")) return;
    lastFocus = document.activeElement;
    modal.classList.remove("hidden");
    root.classList.add("has-modal");
    void modal.offsetWidth; // start the transition from the hidden state
    modal.classList.add("is-open");
    var first = focusables(modal)[0];
    if (first) first.focus();
  }

  function closeModal(modal) {
    if (!modal || modal.classList.contains("hidden")) return;
    modal.classList.remove("is-open");
    root.classList.remove("has-modal");
    window.setTimeout(function () { modal.classList.add("hidden"); }, prefersReducedMotion() ? 0 : 220);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  var reviewModal = document.getElementById("review-modal");
  document.querySelectorAll("[data-open-review]").forEach(function (btn) {
    btn.addEventListener("click", function () { openModal(reviewModal); });
  });
  document.querySelectorAll("[data-close-review]").forEach(function (btn) {
    btn.addEventListener("click", function () { closeModal(btn.closest(".modal-backdrop")); });
  });
  document.querySelectorAll(".modal-backdrop").forEach(function (backdrop) {
    backdrop.addEventListener("mousedown", function (event) {
      if (event.target === backdrop) closeModal(backdrop);
    });
    backdrop.addEventListener("keydown", function (event) {
      if (event.key !== "Tab") return;
      var items = focusables(backdrop);
      if (!items.length) return;
      var first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
  });

  var mobileMenu = document.querySelector("[data-mobile-menu]");
  var menuToggles = document.querySelectorAll("[data-menu-toggle]");
  function setMenu(open) {
    if (!mobileMenu) return;
    mobileMenu.classList.toggle("hidden", !open);
    menuToggles.forEach(function (btn) {
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      if (btn.closest(".mobile-header")) btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    });
  }
  menuToggles.forEach(function (btn) {
    btn.addEventListener("click", function (event) {
      event.stopPropagation();
      setMenu(mobileMenu && mobileMenu.classList.contains("hidden"));
    });
  });
  document.addEventListener("click", function (event) {
    if (mobileMenu && !mobileMenu.classList.contains("hidden") && !mobileMenu.contains(event.target)) setMenu(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    var open = document.querySelector(".modal-backdrop.is-open");
    if (open) { closeModal(open); return; }
    if (mobileMenu && !mobileMenu.classList.contains("hidden")) {
      setMenu(false);
      var toggle = document.querySelector(".mobile-header [data-menu-toggle]");
      if (toggle) toggle.focus();
    }
  });

  // ---------------------------------------------------------------------
  // Forms: one submission at a time, with a visible loading state
  // ---------------------------------------------------------------------
  function setLoading(button, loading) {
    if (!button) return;
    if (loading) {
      if (!button.dataset.label) button.dataset.label = button.innerHTML;
      button.classList.add("is-loading");
      button.setAttribute("aria-disabled", "true");
      if (button.dataset.loadingText) button.textContent = button.dataset.loadingText;
    } else {
      button.classList.remove("is-loading");
      button.removeAttribute("aria-disabled");
      if (button.dataset.label) { button.innerHTML = button.dataset.label; delete button.dataset.label; }
    }
  }

  document.querySelectorAll("form").forEach(function (form) {
    if ((form.getAttribute("method") || "").toLowerCase() !== "post" || form.hasAttribute("data-name-form")) return;
    form.addEventListener("submit", function (event) {
      if (form.dataset.submitting === "true") { event.preventDefault(); return; }
      form.dataset.submitting = "true";
      var submitter = event.submitter || form.querySelector("button[type=submit], button:not([type])");
      // The submitter must stay enabled until the browser has read its
      // name/value, so it's marked busy rather than disabled.
      if (submitter && submitter.classList.contains("button")) setLoading(submitter, true);
      else if (submitter) submitter.setAttribute("aria-disabled", "true");
    });
  });

  // A page restored from the back/forward cache must be usable again.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    document.querySelectorAll("form[data-submitting]").forEach(function (form) { delete form.dataset.submitting; });
    document.querySelectorAll(".is-loading").forEach(function (btn) { setLoading(btn, false); });
    document.querySelectorAll("[aria-disabled=true]").forEach(function (btn) { btn.removeAttribute("aria-disabled"); });
  });

  // ---------------------------------------------------------------------
  // Display name editor (works without JavaScript as a normal form post)
  // ---------------------------------------------------------------------
  var nameForm = document.querySelector("[data-name-form]");
  if (nameForm) {
    var nameInput = nameForm.querySelector("input[name=name]");
    var saveBtn = nameForm.querySelector("[data-name-save]");
    var cancelBtn = nameForm.querySelector("[data-name-cancel]");
    var errorEl = nameForm.querySelector("[data-name-error]");
    var saved = nameInput.value;
    var busy = false;

    var normalize = function (value) { return value.replace(/\s+/g, " ").trim(); };
    var showError = function (msg) {
      errorEl.textContent = msg || "";
      if (msg) nameInput.setAttribute("aria-invalid", "true");
      else nameInput.removeAttribute("aria-invalid");
    };
    var refresh = function () {
      var value = normalize(nameInput.value);
      var dirty = value !== normalize(saved);
      saveBtn.disabled = busy || !dirty || !value;
      cancelBtn.disabled = busy || nameInput.value === saved;
      if (!value && nameInput.value !== saved) showError("Enter a name.");
      else if (errorEl.textContent === "Enter a name.") showError("");
    };
    nameInput.addEventListener("input", refresh);
    nameForm.addEventListener("reset", function (event) {
      event.preventDefault();
      nameInput.value = saved;
      showError("");
      refresh();
      nameInput.focus();
    });
    nameForm.addEventListener("submit", function (event) {
      event.preventDefault();
      if (busy) return;
      var value = normalize(nameInput.value);
      if (!value) { showError("Enter a name."); nameInput.focus(); return; }
      busy = true;
      showError("");
      setLoading(saveBtn, true);
      refresh();
      var body = new URLSearchParams(new FormData(nameForm));
      body.set("name", value);
      fetch(nameForm.action, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrfToken(), "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString()
      }).then(function (res) {
        return res.json().catch(function () { return { ok: false }; }).then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "We couldn't save your name. Please try again.");
          return data;
        });
      }).then(function (data) {
        saved = data.name;
        nameInput.value = data.name;
        document.querySelectorAll("[data-user-name]").forEach(function (el) { el.textContent = data.name; });
        document.querySelectorAll("[data-user-initials]").forEach(function (el) { el.textContent = data.initials; });
        setLoading(saveBtn, false);
        saveBtn.classList.add("is-success");
        window.setTimeout(function () { saveBtn.classList.remove("is-success"); }, 1200);
        toast("Your name was updated.", "success");
      }).catch(function (err) {
        setLoading(saveBtn, false);
        var msg = err && err.message && err.message !== "Failed to fetch" ? err.message : "We couldn't reach Finovate. Check your connection and try again.";
        showError(msg);
        toast(msg, "error");
      }).then(function () {
        busy = false;
        refresh();
      });
    });
    refresh();
  }

  // ---------------------------------------------------------------------
  // Savings plan form: live check that the split adds up to 100%
  // ---------------------------------------------------------------------
  var planForm = document.querySelector("[data-plan-form]");
  if (planForm) {
    var percentInputs = planForm.querySelectorAll("[data-plan-percent]");
    var totalEl = planForm.querySelector("[data-percent-total]");
    var planSubmit = planForm.querySelector("button[type=submit]");
    var checkTotal = function () {
      var total = 0;
      var valid = true;
      percentInputs.forEach(function (input) {
        var n = Number(input.value);
        if (input.value === "" || !Number.isInteger(n) || n < 0 || n > 100) valid = false;
        total += Number.isFinite(n) ? n : 0;
      });
      var ok = valid && total === 100;
      if (totalEl) {
        totalEl.textContent = "Total: " + total + "%" + (ok ? "" : " — must add up to 100%");
        totalEl.classList.toggle("is-invalid", !ok);
      }
      if (planSubmit) planSubmit.disabled = !ok;
    };
    percentInputs.forEach(function (input) { input.addEventListener("input", checkTotal); });
    checkTotal();
  }

  // ---------------------------------------------------------------------
  // Scrolling: header shadow, reveals, settings scrollspy
  // ---------------------------------------------------------------------
  var topbar = document.querySelector(".desktop-topbar");
  if (topbar) {
    var onScroll = function () { topbar.classList.toggle("is-scrolled", window.scrollY > 4); };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  if ("IntersectionObserver" in window && !prefersReducedMotion()) {
    var revealTargets = document.querySelectorAll(".content .section-heading, .content .recommendation-grid > .card, .content .goals-grid > .card, .content .two-column > .card, .content .plan-settings, .content [data-reveal]");
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-revealed");
        observer.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -40px 0px", threshold: 0.05 });
    revealTargets.forEach(function (el) {
      // Only content that starts below the fold is hidden; nothing visible
      // on load ever blinks out.
      if (el.getBoundingClientRect().top > window.innerHeight) {
        el.classList.add("reveal-pending");
        observer.observe(el);
      }
    });
  }

  var spy = document.querySelector("[data-scrollspy]");
  if (spy && "IntersectionObserver" in window) {
    var links = Array.prototype.slice.call(spy.querySelectorAll("a[href^='#']"));
    var sections = links.map(function (a) { return document.getElementById(a.getAttribute("href").slice(1)); }).filter(Boolean);
    var setActive = function (id) {
      links.forEach(function (a) {
        var on = a.getAttribute("href") === "#" + id;
        a.classList.toggle("active", on);
        if (on) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
      });
    };
    var visible = {};
    var spyObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) { visible[entry.target.id] = entry.isIntersecting; });
      var first = sections.find(function (section) { return visible[section.id]; });
      if (first) setActive(first.id);
    }, { rootMargin: "-90px 0px -55% 0px" });
    sections.forEach(function (section) { spyObserver.observe(section); });
    links.forEach(function (a) { a.addEventListener("click", function () { setActive(a.getAttribute("href").slice(1)); }); });
    if (location.hash) setActive(location.hash.slice(1));
  }

  // ---------------------------------------------------------------------
  // Financial figures count up once on load (final value is server-rendered)
  // ---------------------------------------------------------------------
  if (!prefersReducedMotion() && window.requestAnimationFrame) {
    document.querySelectorAll("[data-count-to]").forEach(function (el) {
      var target = Number(el.getAttribute("data-count-to"));
      if (!Number.isFinite(target) || target === 0) return;
      var finalText = el.textContent;
      var start = null;
      var duration = 600;
      var fmt = function (n) {
        var sign = n < 0 ? "-" : "";
        return sign + "$" + Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      };
      var step = function (ts) {
        if (start === null) start = ts;
        var t = Math.min((ts - start) / duration, 1);
        var eased = 1 - Math.pow(1 - t, 3);
        el.textContent = t < 1 ? fmt(target * eased) : finalText;
        if (t < 1) window.requestAnimationFrame(step);
      };
      window.requestAnimationFrame(step);
    });
  }

  // ---------------------------------------------------------------------
  // Investing projection calculator
  // ---------------------------------------------------------------------
  var years = document.getElementById("calc-years");
  if (years) {
    var startValue = Number(years.dataset.start || "0");
    var monthly = Number(years.dataset.monthly || "0");
    var rate = Number(years.dataset.rate || "0.06");
    var project = function () {
      var n = Number(years.value);
      var label = document.getElementById("calc-years-label");
      var out = document.getElementById("calc-projection");
      var horizon = document.getElementById("calc-horizon");
      var monthlyRate = rate / 12;
      var growth = startValue * Math.pow(1 + rate, n);
      var contrib = monthlyRate === 0 ? monthly * n * 12 : monthly * ((Math.pow(1 + monthlyRate, n * 12) - 1) / monthlyRate);
      var value = Math.round(growth + contrib);
      if (label) label.textContent = n + " years";
      if (horizon) horizon.textContent = "Estimated portfolio value in " + n + " years";
      if (out) out.textContent = "$" + value.toLocaleString();
    };
    years.addEventListener("input", project);
    project();
  }

  window.Finovate = { toast: toast, openModal: openModal, closeModal: closeModal, applyTheme: applyTheme };
})();
