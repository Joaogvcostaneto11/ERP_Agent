export function renderChart(block) {
  const wrap = document.createElement("div");
  const title = document.createElement("div");
  title.className = "status";
  title.textContent = block.title;
  const chart = document.createElement("div");
  chart.className = "chart";
  wrap.append(title, chart);
  queueMicrotask(() => {
    window.Plotly.newPlot(chart, block.plotly.data || [], block.plotly.layout || {}, { responsive: true });
  });
  return wrap;
}
