(function () {
  const mobileMenu = document.querySelector("[data-mobile-menu]");
  document.querySelectorAll("[data-menu-toggle]").forEach(function (menuBtn) {
    menuBtn.addEventListener("click", function () {
      if (mobileMenu) mobileMenu.classList.toggle("hidden");
    });
  });

  document.querySelectorAll("[data-open-review]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const modal = document.getElementById("review-modal");
      if (modal) modal.classList.remove("hidden");
    });
  });

  document.querySelectorAll("[data-close-review]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const modal = document.getElementById("review-modal");
      const form = document.getElementById("review-form");
      const success = document.getElementById("review-success");
      if (modal) modal.classList.add("hidden");
      if (form) form.classList.remove("hidden");
      if (success) success.classList.add("hidden");
    });
  });

  const savePlan = document.getElementById("save-proposed-plan");
  if (savePlan) {
    savePlan.addEventListener("click", function () {
      const form = document.getElementById("review-form");
      const success = document.getElementById("review-success");
      if (form) form.classList.add("hidden");
      if (success) success.classList.remove("hidden");
    });
  }

  const emergency = document.getElementById("emergency-alloc");
  if (emergency) {
    const surplus = Number(emergency.dataset.surplus || "0");
    function renderAlloc() {
      const pct = Number(emergency.value);
      const emergencyAmt = Math.round(surplus * pct) / 100;
      const longTerm = Math.round(surplus * 10) / 100;
      const shortTerm = Math.round((surplus - emergencyAmt - longTerm) * 100) / 100;
      const emEl = document.getElementById("alloc-emergency");
      const stEl = document.getElementById("alloc-short");
      const ltEl = document.getElementById("alloc-long");
      const bar = document.getElementById("alloc-bar-emergency");
      if (emEl) emEl.textContent = "$" + emergencyAmt.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
      if (stEl) stEl.textContent = "$" + Math.max(shortTerm, 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
      if (ltEl) ltEl.textContent = "$" + longTerm.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
      if (bar) bar.style.width = pct + "%";
    }
    emergency.addEventListener("input", renderAlloc);
    renderAlloc();
  }

  const years = document.getElementById("calc-years");
  if (years) {
    const start = Number(years.dataset.start || "0");
    const monthly = Number(years.dataset.monthly || "0");
    const rate = Number(years.dataset.rate || "0.06");
    function project() {
      const n = Number(years.value);
      const label = document.getElementById("calc-years-label");
      const out = document.getElementById("calc-projection");
      const horizon = document.getElementById("calc-horizon");
      const monthlyRate = rate / 12;
      const growth = start * Math.pow(1 + rate, n);
      const contrib = monthlyRate === 0 ? monthly * n * 12 : monthly * ((Math.pow(1 + monthlyRate, n * 12) - 1) / monthlyRate);
      const value = Math.round(growth + contrib);
      if (label) label.textContent = n + " years";
      if (horizon) horizon.textContent = "Estimated portfolio value in " + n + " years";
      if (out) out.textContent = "$" + value.toLocaleString();
    }
    years.addEventListener("input", project);
    project();
  }

  const backdrop = document.querySelector(".modal-backdrop");
  if (backdrop) {
    backdrop.addEventListener("mousedown", function (event) {
      if (event.target === backdrop) {
        backdrop.classList.add("hidden");
      }
    });
  }
})();
