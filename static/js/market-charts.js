(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const WIDTH = 1000;
  const HEIGHT = 360;
  const PLOT = { left: 26, right: 92, top: 28, bottom: 34 };
  const COLORS = {
    up: "#16c784",
    down: "#f0445e",
    flat: "#9ba6a2",
    grid: "#ffffff24",
    label: "#929b9e",
    cursor: "#ffffff7a",
    line: "#f4c542",
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
    if (!svg || !slider || points.length < 2) return;

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
      x: PLOT.left + (index / (points.length - 1)) * plotWidth,
      y: PLOT.top + ((high - point.close) / (high - low)) * plotHeight,
    }));

    svg.setAttribute("viewBox", `0 0 ${WIDTH} ${HEIGHT}`);
    svg.replaceChildren();
    const defs = svgElement("defs");
    const gradientId = `chart-fill-${card.dataset.seriesId}`;
    const gradient = svgElement("linearGradient", {
      id: gradientId,
      x1: "0",
      x2: "0",
      y1: "0",
      y2: "1",
    });
    const trendColor = points[points.length - 1].close >= points[0].close ? COLORS.up : COLORS.down;
    gradient.append(
      svgElement("stop", { offset: "0%", "stop-color": trendColor, "stop-opacity": ".3" }),
      svgElement("stop", { offset: "100%", "stop-color": trendColor, "stop-opacity": ".015" }),
    );
    defs.appendChild(gradient);
    svg.appendChild(defs);

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
          "stroke-dasharray": "2 7",
        }),
        svgElement("text", {
          x: WIDTH - PLOT.right + 10,
          y: y + 4,
          fill: COLORS.label,
          "font-size": 11,
          "text-anchor": "start",
        }, formatMoney(value)),
      );
    }

    const linePath = coordinates
      .map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`)
      .join(" ");
    const bottom = HEIGHT - PLOT.bottom;
    const areaPath = `${linePath} L ${coordinates[coordinates.length - 1].x} ${bottom} L ${coordinates[0].x} ${bottom} Z`;
    svg.appendChild(svgElement("path", {
      d: areaPath,
      fill: `url(#${gradientId})`,
      "data-chart-area": "",
    }));

    for (let index = 1; index < points.length; index += 1) {
      const previous = coordinates[index - 1];
      const current = coordinates[index];
      svg.appendChild(svgElement("line", {
        x1: previous.x,
        y1: previous.y,
        x2: current.x,
        y2: current.y,
        stroke: pointColor(points, index),
        "stroke-width": 2.5,
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
      }));
    }

    const firstIndex = 0;
    const middleIndex = Math.floor((points.length - 1) / 2);
    [firstIndex, middleIndex, points.length - 1].forEach((index) => {
      const point = points[index];
      svg.appendChild(svgElement("text", {
        x: coordinates[index].x,
        y: HEIGHT - 8,
        fill: COLORS.label,
        "font-size": 10,
        "text-anchor": index === 0 ? "start" : index === points.length - 1 ? "end" : "middle",
      }, point.date));
    });

    const cursor = svgElement("line", {
      x1: 0,
      y1: PLOT.top,
      x2: 0,
      y2: bottom,
      stroke: COLORS.cursor,
      "stroke-width": 1,
      "stroke-dasharray": "4 5",
      visibility: "hidden",
      "data-chart-cursor": "",
    });
    const selectedPriceLine = svgElement("line", {
      x1: PLOT.left,
      y1: 0,
      x2: WIDTH - PLOT.right,
      y2: 0,
      stroke: COLORS.line,
      "stroke-width": 1,
      "stroke-dasharray": "5 5",
      "stroke-opacity": ".75",
      visibility: "hidden",
      "data-chart-price-line": "",
    });
    const selectedPoint = svgElement("circle", {
      cx: 0,
      cy: 0,
      r: 5,
      fill: COLORS.line,
      stroke: "#111416",
      "stroke-width": 2,
      visibility: "hidden",
      "data-chart-point": "",
    });
    const badge = svgElement("g", { visibility: "hidden", "data-chart-badge": "" });
    const badgeRect = svgElement("rect", {
      x: WIDTH - PLOT.right + 1,
      y: 0,
      width: PLOT.right - 8,
      height: 25,
      rx: 5,
      fill: COLORS.up,
    });
    const badgeText = svgElement("text", {
      x: WIDTH - PLOT.right / 2 - 2,
      y: 17,
      fill: "#101214",
      "font-size": 11,
      "font-weight": 700,
      "text-anchor": "middle",
    });
    badge.append(badgeRect, badgeText);
    svg.append(cursor, selectedPriceLine, selectedPoint, badge);

    const dateOutput = chart.querySelector("[data-chart-date]");
    const priceOutput = chart.querySelector("[data-chart-price]");
    const changeOutput = chart.querySelector("[data-chart-change]");

    function selectPoint(index) {
      const boundedIndex = Math.max(0, Math.min(points.length - 1, index));
      const point = points[boundedIndex];
      const coordinate = coordinates[boundedIndex];
      slider.value = String(boundedIndex);
      if (dateOutput) dateOutput.textContent = point.date;
      if (priceOutput) priceOutput.textContent = formatMoney(point.close);
      if (changeOutput) {
        if (boundedIndex === 0) {
          changeOutput.textContent = "First recorded sample date";
          changeOutput.className = "";
        } else {
          const previousClose = points[boundedIndex - 1].close;
          const difference = point.close - previousClose;
          const percent = previousClose ? (difference / previousClose) * 100 : 0;
          const direction = difference > 0 ? "Up" : difference < 0 ? "Down" : "Unchanged";
          const sign = difference > 0 ? "+" : "";
          changeOutput.textContent = `${direction} ${sign}${formatMoney(difference)} (${sign}${percent.toFixed(2)}%) vs previous sample date`;
          changeOutput.className = difference > 0 ? "market-chart-up" : difference < 0 ? "market-chart-down" : "";
        }
      }
      const color = pointColor(points, boundedIndex);
      cursor.setAttribute("x1", coordinate.x);
      cursor.setAttribute("x2", coordinate.x);
      cursor.setAttribute("visibility", "visible");
      selectedPriceLine.setAttribute("y1", coordinate.y);
      selectedPriceLine.setAttribute("y2", coordinate.y);
      selectedPriceLine.setAttribute("stroke", color);
      selectedPriceLine.setAttribute("visibility", "visible");
      selectedPoint.setAttribute("cx", coordinate.x);
      selectedPoint.setAttribute("cy", coordinate.y);
      selectedPoint.setAttribute("fill", color);
      selectedPoint.setAttribute("visibility", "visible");
      badge.setAttribute("transform", `translate(0 ${Math.max(PLOT.top, Math.min(bottom - 25, coordinate.y - 12.5))})`);
      badgeRect.setAttribute("fill", color);
      badgeText.textContent = formatMoney(point.close);
      badge.setAttribute("visibility", "visible");
      slider.setAttribute("aria-valuetext", `${point.date}, ${formatMoney(point.close)}`);
      svg.setAttribute("aria-label", `${point.date}: ${formatMoney(point.close)} sample value`);
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

    const defaultView = card.dataset.defaultView || "table";
    const viewButtons = card.querySelectorAll("[data-market-view]");
    if (table && viewButtons.length) {
      const showChart = defaultView === "chart";
      chart.hidden = !showChart;
      table.hidden = showChart;
      table.open = false;
      viewButtons.forEach((button) => {
        const selected = button.dataset.marketView === defaultView;
        button.classList.toggle("active", selected);
        button.setAttribute("aria-pressed", String(selected));
        button.addEventListener("click", () => {
          const chartSelected = button.dataset.marketView === "chart";
          chart.hidden = !chartSelected;
          table.hidden = chartSelected;
          table.open = chartSelected ? false : true;
          viewButtons.forEach((viewButton) => {
            const isSelected = viewButton === button;
            viewButton.classList.toggle("active", isSelected);
            viewButton.setAttribute("aria-pressed", String(isSelected));
          });
        });
      });
    } else if (chart) {
      chart.hidden = false;
    }

    selectPoint(points.length - 1);

    card.appendLivePoint = (point) => {
      const latestPoints = JSON.parse(dataElement.textContent);
      if (latestPoints[latestPoints.length - 1].date === point.date) return;
      latestPoints.push(point);
      dataElement.textContent = JSON.stringify(latestPoints);

      const currentSvg = card.querySelector(".market-price-chart");
      const replacementSvg = currentSvg.cloneNode(false);
      currentSvg.replaceWith(replacementSvg);
      const replacementSlider = slider.cloneNode();
      slider.replaceWith(replacementSlider);
      replacementSlider.max = String(latestPoints.length - 1);
      replacementSlider.value = String(latestPoints.length - 1);
      setupChart(card);
    };
  }

  document.querySelectorAll("[data-series-id]").forEach(setupChart);
  document.addEventListener("finovate:live-quotes", (event) => {
    document.querySelectorAll("[data-live-symbol]").forEach((card) => {
      const quote = event.detail.quotes[card.dataset.liveSymbol];
      if (quote && typeof card.appendLivePoint === "function") {
        card.appendLivePoint({ date: event.detail.label, close: quote.market_value });
      }
    });
    const portfolioCard = document.querySelector("[data-live-portfolio]");
    if (portfolioCard && event.detail.portfolioValue && typeof portfolioCard.appendLivePoint === "function") {
      portfolioCard.appendLivePoint({ date: event.detail.label, close: event.detail.portfolioValue });
    }
  });
  document.body.classList.add("has-market-chart-js");
})();
