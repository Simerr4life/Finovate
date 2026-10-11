(() => {
  const status = document.querySelector("[data-live-quotes-status]");
  if (!status) return;

  const formatMoney = (value) => new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value));
  const formatTime = (value) => new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));

  async function refreshQuotes() {
    try {
      const response = await fetch(status.dataset.quotesUrl, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const data = await response.json();
      if (!response.ok) {
        status.textContent = data.error || "Live prices could not be loaded.";
        if (response.status === 503) window.clearInterval(intervalId);
        return;
      }

      Object.entries(data.quotes).forEach(([symbol, quote]) => {
        document.querySelectorAll("[data-live-symbol]").forEach((card) => {
          if (card.dataset.liveSymbol !== symbol) return;
          const value = card.querySelector("[data-live-value]");
          const caption = card.querySelector("[data-live-value-caption]");
          if (value) value.textContent = formatMoney(quote.market_value);
          if (caption) caption.textContent = `Twelve Data quote · ${formatTime(quote.fetched_at)}`;
        });
      });

      if (data.portfolio_value) {
        const portfolioValue = document.querySelector("[data-live-portfolio-value]");
        const portfolioChange = document.querySelector("[data-live-portfolio-change]");
        const portfolioCaption = document.querySelector("[data-live-portfolio-caption]");
        const changeCaption = document.querySelector("[data-live-change-caption]");
        const costBasisElement = document.querySelector(".holdings-summary .summary-card:nth-child(2) .money");
        const costBasis = costBasisElement
          ? Number(costBasisElement.textContent.replace(/[^0-9.-]/g, ""))
          : 0;
        const change = Number(data.portfolio_value) - costBasis;
        if (portfolioValue) portfolioValue.textContent = formatMoney(data.portfolio_value);
        if (portfolioChange) {
          portfolioChange.textContent = formatMoney(change);
          portfolioChange.classList.toggle("positive", change >= 0);
          portfolioChange.classList.toggle("negative", change < 0);
        }
        if (portfolioCaption) portfolioCaption.textContent = "Latest Twelve Data prices";
        if (changeCaption) changeCaption.textContent = "Compared with simulated cost basis";
      }

      const lastQuote = Object.values(data.quotes).reduce((latest, quote) => (
        !latest || new Date(quote.fetched_at) > new Date(latest.fetched_at) ? quote : latest
      ), null);
      const label = lastQuote ? new Date(lastQuote.fetched_at) : new Date();
      const chartLabel = new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }).format(label);
      document.dispatchEvent(new CustomEvent("finovate:live-quotes", {
        detail: {
          quotes: data.quotes,
          portfolioValue: data.portfolio_value,
          label: chartLabel,
        },
      }));

      const errorCount = Object.keys(data.errors || {}).length;
      if (!data.market_open) {
        status.textContent = lastQuote
          ? `US market is closed. Showing the last Twelve Data prices from ${formatTime(lastQuote.fetched_at)}.`
          : "US market is closed. Live prices refresh every five minutes during regular market hours.";
      } else if (errorCount) {
        status.textContent = "Some quotes could not refresh (provider quota or temporary error). Showing the latest available prices; next check in five minutes.";
      } else if (lastQuote) {
        status.textContent = `Twelve Data prices updated at ${formatTime(lastQuote.fetched_at)}. Refreshes every five minutes while this page is open.`;
      } else {
        status.textContent = "Waiting for the first live quote from Twelve Data.";
      }
    } catch {
      status.textContent = "Live prices could not be reached. The historical sample graph remains available.";
    }
  }

  const intervalId = window.setInterval(refreshQuotes, 5 * 60 * 1000);
  refreshQuotes();
})();
