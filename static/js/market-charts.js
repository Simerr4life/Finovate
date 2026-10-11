(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const WIDTH = 720;
  const HEIGHT = 260;
  const PLOT = { left: 66, right: 16, top: 20, bottom: 34 };
  const COLORS = {
    up: "#21865b",
    down: "#d14d4d",
    flat: "#8a9a95",
    grid: "#e7eeeb",
    label: "#71817b",
    cursor: "#52645e",
  };

  function svgElement(name, attributes = {}, text = "") {
    const element = document.createElementNS(SVG_NS, name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    if (text) element.textContent = text;
    return element;
  }

  function formatMoney(value) {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  }

  function pointColor(points, index) {
    if (index === 0 || points[index].close === points[index - 1].close) return COLORS.flat;
    return points[index].close > points[index - 1].close ? COLORS.up : COLORS.down;
  }

  function setupChart(card) {
    const dataElement = document.getElementById(card.dataset.seriesId);
    const chart = card.querySelector("[data-market-chart]");
    const svg = chart && chart.querySelector("svg");
    const slider = chart && chart.querySelector("[data-chart-slider]");
    const table = card.querySelector("[data-market-table]");
    const points = dataElement ? JSON.parse(dataElement.textContent) : [];
    if (!svg || !slider || !table || points.length < 2) return;

    points.forEach((point) => {
      point.close = Number(point.close);
    });
    const min = Math.min(...points.map((point) => point.close));
    const max = Math.max(...points.map((point) => point.close));
    const padding = Math.max((max - min) * 0.12, max * 0.002, 0.01);
    const low = min - padding;
    const high = max + padding;
    const plotWidth = WIDTH - PLOT.left - PLOT.right;
    const plotHeight = HEIGHT - PLOT.top - PLOT.bottom;
    const coordinates = points.map((point, index) => ({
      x: PLOT.left + (points.length === 1 ? 0 : (index / (points.length - 1)) * plotWidth),
      y: PLOT.top + ((high - point.close) / (high - low)) * plotHeight,
    }));

    svg.setAttribute("viewBox", `0 0 ${WIDTH} ${HEIGHT}`);
    svg.replaceChildren();
    for (let step = 0; step <= 4; step += 1) {
      const y = PLOT.top + (step / 4) * plotHeight;
      const value = high - (step / 4) * (high - low);
      svg.append(
        svgElement("line", {
          x1: PLOT.left,
          y1: y,
          x2: WIDTH - PLOT.right,
          y2: y,
          stroke: COLORS.grid,
          "stroke-width": 1,
        }),
        svgElement("text", {
          x: PLOT.left - 9,
          y: y + 4,
          fill: COLORS.label,
          "font-size": 11,
          "text-anchor": "end",
        }, formatMoney(value)),
      );
    }

    for (let index = 1; index < points.length; index += 1) {
      const previous = coordinates[index - 1];
      const current = coordinates[index];
      svg.appendChild(svgElement("line", {
        x1: previous.x,
        y1: previous.y,
        x2: current.x,
        y2: current.y,
        stroke: pointColor(points, index),
        "stroke-width": 3,
        "stroke-linecap": "round",
      }));
    }

    const cursor = svgElement("line", {
      x1: 0,
      y1: PLOT.top,
      x2: 0,
      y2: HEIGHT - PLOT.bottom,
      stroke: COLORS.cursor,
      "stroke-width": 1,
      "stroke-dasharray": "4 4",
      visibility: "hidden",
      "data-chart-cursor": "",
    });
    const selectedPoint = svgElement("circle", {
      cx: 0,
      cy: 0,
      r: 6,
      fill: COLORS.up,
      stroke: "#ffffff",
      "stroke-width": 3,
      visibility: "hidden",
      "data-chart-point": "",
    });
    svg.append(cursor, selectedPoint);

    const dateOutput = chart.querySelector("[data-chart-date]");
    const priceOutput = chart.querySelector("[data-chart-price]");
    const changeOutput = chart.querySelector("[data-chart-change]");

    function selectPoint(index) {
      const boundedIndex = Math.max(0, Math.min(points.length - 1, index));
      const point = points[boundedIndex];
      const coordinate = coordinates[boundedIndex];
      slider.value = String(boundedIndex);
      dateOutput.textContent = point.date;
      priceOutput.textContent = formatMoney(point.close);
      if (boundedIndex === 0) {
        changeOutput.textContent = "First recorded sample date";
        changeOutput.className = "";
      } else {
        const previousClose = points[boundedIndex - 1].close;
        const difference = point.close - previousClose;
        const percent = previousClose ? (difference / previousClose) * 100 : 0;
        const direction = difference > 0 ? "up" : difference < 0 ? "down" : "unchanged";
        const sign = difference > 0 ? "+" : "";
        changeOutput.textContent = `${direction === "unchanged" ? "Unchanged" : direction} ${sign}${formatMoney(difference)} (${sign}${percent.toFixed(2)}%) vs previous date`;
        changeOutput.className = difference > 0 ? "market-chart-up" : difference < 0 ? "market-chart-down" : "";
      }
      cursor.setAttribute("x1", coordinate.x);
      cursor.setAttribute("x2", coordinate.x);
      cursor.setAttribute("visibility", "visible");
      selectedPoint.setAttribute("cx", coordinate.x);
      selectedPoint.setAttribute("cy", coordinate.y);
      selectedPoint.setAttribute("fill", pointColor(points, boundedIndex));
      selectedPoint.setAttribute("visibility", "visible");
      slider.setAttribute("aria-valuetext", `${point.date}, ${formatMoney(point.close)}`);
      svg.setAttribute("aria-label", `${point.date}: ${formatMoney(point.close)} sample close`);
    }

    slider.addEventListener("input", () => selectPoint(Number(slider.value)));
    svg.addEventListener("pointermove", (event) => {
      const bounds = svg.getBoundingClientRect();
      if (!bounds.width) return;
      const svgX = ((event.clientX - bounds.left) / bounds.width) * WIDTH;
      const fraction = (svgX - PLOT.left) / plotWidth;
      selectPoint(Math.round(fraction * (points.length - 1)));
    });
    svg.addEventListener("pointerleave", () => selectPoint(Number(slider.value)));

    card.querySelectorAll("[data-market-view]").forEach((button) => {
      button.addEventListener("click", () => {
        const chartSelected = button.dataset.marketView === "chart";
        chart.hidden = !chartSelected;
        table.hidden = chartSelected;
        if (chartSelected) table.open = false;
        else table.open = true;
        card.querySelectorAll("[data-market-view]").forEach((viewButton) => {
          const selected = viewButton === button;
          viewButton.classList.toggle("active", selected);
          viewButton.setAttribute("aria-pressed", String(selected));
        });
      });
    });

    selectPoint(points.length - 1);
  }

  document.querySelectorAll(".market-asset-card[data-series-id]").forEach(setupChart);
  document.body.classList.add("has-market-chart-js");
})();
