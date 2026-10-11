(() => {
  const status = document.querySelector("[data-market-live-status]");
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
        status.textContent = data.error || "Twelve Data quotes could not be loaded.";
        return;
      }

      Object.entries(data.quotes).forEach(([symbol, quote]) => {
        document.querySelectorAll("[data-live-symbol]").forEach((card) => {
          if (card.dataset.liveSymbol !== symbol) return;
          const value = card.querySelector("[data-market-quote-price]");
          const caption = card.querySelector("[data-market-quote-caption]");
          if (value) value.textContent = formatMoney(quote.market_value);
          if (caption) {
            caption.textContent = `Twelve Data quote · ${formatTime(quote.fetched_at)}`;
          }
        });
      });

      const lastQuote = Object.values(data.quotes).reduce((latest, quote) => (
        !latest || new Date(quote.fetched_at) > new Date(latest.fetched_at) ? quote : latest
      ), null);
      const label = lastQuote ? new Date(lastQuote.fetched_at) : new Date();
      document.dispatchEvent(new CustomEvent("finovate:live-quotes", {
        detail: {
          quotes: data.quotes,
          label: new Intl.DateTimeFormat(undefined, {
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
          }).format(label),
        },
      }));

      const errorCount = Object.keys(data.errors || {}).length;
      if (!data.market_open) {
        status.textContent = lastQuote
          ? `US market is closed. Showing the last Twelve Data prices from ${formatTime(lastQuote.fetched_at)}.`
          : "US market is closed. Daily Twelve Data prices remain available.";
      } else if (errorCount) {
        status.textContent = "Some quotes could not refresh. Showing available cached prices; the next check is in five minutes.";
      } else if (lastQuote) {
        status.textContent = `Twelve Data quotes updated at ${formatTime(lastQuote.fetched_at)}. Refreshes every five minutes while this page is open.`;
      } else {
        status.textContent = "Waiting for the first Twelve Data quote.";
      }
    } catch {
      status.textContent = "Twelve Data quotes could not be reached. Cached provider history remains available.";
    }
  }

  window.setInterval(refreshQuotes, 5 * 60 * 1000);
  refreshQuotes();
})();
