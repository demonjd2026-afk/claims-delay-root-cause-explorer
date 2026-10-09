// Shared rendering helpers: DOM builder, formatters, bars, charts.

export const STAGE_COLOR = {
  intake: "#2a78d6", pre_adjudication: "#eb6834", adjudication: "#1baf7a", post_adjudication: "#eda100",
};
export const NEUTRAL = "#8792a1";
export const stageColor = (stage) => STAGE_COLOR[stage] ?? NEUTRAL;

export function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs ?? {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "style") Object.assign(node.style, value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const intFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const oneFmt = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
export const fmt = {
  int: (v) => (v === null || v === undefined ? "n/a" : intFmt.format(v)),
  one: (v) => (v === null || v === undefined ? "n/a" : oneFmt.format(v)),
  pct: (v, digits = 0) => (v === null || v === undefined ? "n/a" : `${(v * 100).toFixed(digits)}%`),
  money: (v) => {
    if (v === null || v === undefined) return "n/a";
    if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
    if (Math.abs(v) >= 1e4) return `$${Math.round(v / 1e3)}K`;
    return `$${intFmt.format(v)}`;
  },
  dateFull: (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }),
  date: (iso, withWeekday = false) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB",
    withWeekday ? { weekday: "short", day: "numeric", month: "short", year: "numeric" } : { day: "numeric", month: "short" }),
};

export function card(title, sub, ...content) {
  return h("section", { class: "card" },
    h("div", { class: "card-head" }, h("div", {}, h("h2", {}, title), sub && h("p", { class: "sub" }, sub))),
    ...content);
}

/** Card with a control (toggle or select) on the right of its heading. */
export function cardWith(title, sub, control, ...content) {
  const section = card(title, sub, ...content);
  section.querySelector(".card-head").append(control);
  return section;
}

export function kpi(label, value, foot, unit) {
  return h("div", { class: "kpi" },
    h("div", { class: "label" }, label),
    h("div", { class: "value num" }, value, unit && h("small", {}, ` ${unit}`)),
    foot && h("div", { class: "foot" }, foot));
}

export function stageChip(stage, name) {
  return h("span", { class: "stage-chip" }, h("i", { class: "swatch", style: { background: stageColor(stage) } }), name ?? "No single stage");
}

export function stageLegend(stages) {
  return h("div", { class: "legend" }, stages.map((s) => stageChip(s.key, s.name)));
}

export function segmented(options, current, onChange) {
  const group = h("div", { class: "seg", role: "group" });
  for (const [value, label] of options) {
    group.append(h("button", {
      type: "button", "aria-pressed": String(value === current),
      onclick: (event) => {
        group.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false"));
        event.currentTarget.setAttribute("aria-pressed", "true");
        onChange(value);
      },
    }, label));
  }
  return group;
}

/**
 * Horizontal bar list. rows: [{name, value, color, text, sub, under, title, onClick}]
 * `under` draws a lighter bar behind the main one (for "x of y").
 */
export function bars(rows, { max } = {}) {
  const top = max ?? Math.max(1e-9, ...rows.map((r) => Math.max(r.value ?? 0, r.under ?? 0)));
  return h("div", { class: "bars" }, rows.map((r) => h("div", {
    class: `bar-row${r.onClick ? " clickable" : ""}`, title: r.title, tabindex: r.onClick ? "0" : null,
    role: r.onClick ? "button" : null, onclick: r.onClick,
    onkeydown: r.onClick && ((e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); r.onClick(); } }),
  },
    h("div", { class: "bar-name" }, r.name),
    h("div", { class: "bar-track" },
      r.under !== undefined && h("div", { class: "bar-fill under", style: { width: `${(r.under / top) * 100}%`, background: r.color } }),
      h("div", { class: "bar-fill", style: { width: `${((r.value ?? 0) / top) * 100}%`, background: r.color } })),
    h("div", { class: "bar-val" }, r.text, r.sub && h("small", {}, ` ${r.sub}`)))));
}

// ------------------------------------------------------------------ charts
const live = new Set();
export function destroyCharts() { live.forEach((c) => c.destroy()); live.clear(); }

if (window.Chart) {
  const d = window.Chart.defaults;
  d.font.family = getComputedStyle(document.documentElement).getPropertyValue("--font").trim();
  d.font.size = 12;
  d.color = "#5a6777";
  d.animation = false;
  d.plugins.legend.display = false;
  d.plugins.tooltip.backgroundColor = "#12213b";
  d.plugins.tooltip.padding = 10;
  d.plugins.tooltip.cornerRadius = 6;
  d.plugins.tooltip.boxPadding = 4;
}

/** Chart.js needs the canvas in the document to size itself, so wait for the view to mount. */
function whenAttached(canvas, build, tries = 0) {
  requestAnimationFrame(() => {
    if (canvas.isConnected) build();
    else if (tries < 120) whenAttached(canvas, build, tries + 1);
  });
}

/**
 * One bar per calendar day. series: [{label, data, color}]. Stacked when more than one series.
 * Week starts are labelled on the axis; the tooltip gives the full date.
 */
export function dailyChart(dates, series, { height = 220, unit = "claims", marker, compact = false } = {}) {
  const canvas = h("canvas", { role: "img", "aria-label": `${series.map((s) => s.label).join(", ")} for each day` });
  const box = h("div", { class: "chart", style: { height: `${height}px` } }, canvas);
  const showAll = dates.length <= 21;
  const markerIndex = marker ? dates.indexOf(marker.date) : -1;
  whenAttached(canvas, () => {
    const chart = new window.Chart(canvas, {
      type: "bar",
      data: {
        labels: dates,
        datasets: series.map((s) => ({
          label: s.label, data: s.data, backgroundColor: s.color, borderRadius: series.length > 1 ? 0 : 2,
          barPercentage: 0.82, categoryPercentage: 1, borderColor: "#fff", borderWidth: series.length > 1 ? { top: 1 } : 0,
        })),
      },
      options: {
        maintainAspectRatio: false, responsive: true,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: {
            stacked: true, grid: { display: false }, border: { color: "#dde3ea" },
            ticks: {
              autoSkip: false, maxRotation: 0,
              callback(value) {
                const iso = this.getLabelForValue(value);
                const day = new Date(`${iso}T00:00:00`);
                if (compact) return day.getDate() === 1 ? day.toLocaleDateString("en-GB", { month: "short" }) : null;
                return showAll || day.getDay() === 1 ? fmt.date(iso) : null;
              },
            },
          },
          y: {
            stacked: true, beginAtZero: true, border: { display: false }, grid: { color: "#ebeff3" },
            ticks: { maxTicksLimit: compact ? 3 : 5, precision: 0 },
          },
        },
        plugins: {
          tooltip: {
            callbacks: {
              title: (items) => fmt.date(items[0].label, true),
              label: (item) => ` ${item.dataset.label}: ${fmt.int(item.parsed.y)} ${unit}`,
              footer: (items) => (items.length > 1 ? `Total: ${fmt.int(items.reduce((a, i) => a + i.parsed.y, 0))} ${unit}` : ""),
            },
          },
        },
      },
      plugins: markerIndex < 0 ? [] : [{
        id: "marker",
        afterDatasetsDraw(c) {
          const x = c.scales.x.getPixelForValue(markerIndex) - (c.scales.x.getPixelForValue(1) - c.scales.x.getPixelForValue(0)) / 2;
          const { top, bottom } = c.chartArea;
          const ctx = c.ctx;
          ctx.save();
          ctx.strokeStyle = "#c2302a"; ctx.lineWidth = 1.5; ctx.setLineDash([4, 3]);
          ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
          ctx.setLineDash([]); ctx.fillStyle = "#c2302a"; ctx.font = "600 12px " + window.Chart.defaults.font.family;
          ctx.textAlign = "right"; ctx.fillText(marker.label, x - 6, top + 12);
          ctx.restore();
        },
      }],
    });
    live.add(chart);
  });
  return box;
}

/** Stacked horizontal bars comparing a few rows across the four stages. */
export function stackedRows(labels, series, { height = 150, unit = "days" } = {}) {
  const canvas = h("canvas", { role: "img", "aria-label": `${labels.join(" versus ")} by stage` });
  const box = h("div", { class: "chart", style: { height: `${height}px` } }, canvas);
  whenAttached(canvas, () => {
    live.add(new window.Chart(canvas, {
      type: "bar",
      data: { labels, datasets: series.map((s) => ({ label: s.label, data: s.data, backgroundColor: s.color,
        borderColor: "#fff", borderWidth: { right: 2 }, barPercentage: 0.7 })) },
      options: {
        indexAxis: "y", maintainAspectRatio: false,
        scales: {
          x: { stacked: true, grid: { color: "#ebeff3" }, border: { display: false }, title: { display: true, text: `Average ${unit}` } },
          y: { stacked: true, grid: { display: false }, border: { color: "#dde3ea" } },
        },
        plugins: { tooltip: { callbacks: { label: (i) => ` ${i.dataset.label}: ${i.parsed.x.toFixed(2)} ${unit}` } } },
      },
    }));
  });
  return box;
}

/** Minimal, safe markdown: paragraphs, "- " bullets and **bold**. */
export function markdown(text) {
  const root = h("div");
  let list = null;
  const inline = (line) => line.split(/(\*\*[^*]+\*\*)/g).filter(Boolean)
    .map((part) => (part.startsWith("**") ? h("strong", {}, part.slice(2, -2)) : part));
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) { list = null; continue; }
    const bullet = /^([-*•]|\d+\.)\s+/.exec(line);
    if (bullet) {
      if (!list) { list = h("ul"); root.append(list); }
      list.append(h("li", {}, inline(line.slice(bullet[0].length))));
    } else {
      list = null;
      root.append(h("p", {}, inline(line)));
    }
  }
  return root;
}

export function loading() { return h("div", { class: "empty" }, "Loading…"); }
export function failure(error) { return h("div", { class: "error", role: "alert" }, error.message || "Something went wrong."); }
