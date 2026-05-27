const socket = io();

const ui = {
  levelOil: document.getElementById("level-oil"),
  levelSolid: document.getElementById("level-solid"),
  irFull: document.getElementById("ir-full"),
  lastUpdate: document.getElementById("last-update"),
  socketStatus: document.getElementById("socket-status"),
  oilChip: document.getElementById("oil-chip"),
  solidChip: document.getElementById("solid-chip"),
  totalOil: document.getElementById("total-oil-discards"),
  totalSolid: document.getElementById("total-solid-discards"),
  totalLiters: document.getElementById("total-oil-liters"),
  totalKg: document.getElementById("total-solid-kg"),
  alerts: document.getElementById("alerts-list"),
  discardFeed: document.getElementById("discard-feed"),
  ringOil: document.getElementById("ring-oil"),
  ringSolid: document.getElementById("ring-solid"),
};

const palette = {
  accent: "#3BFFC8",
  accentSecondary: "#C8FF3B",
  warm: "#EF9F27",
  surface: "#0E2E1F",
  text: "#F5F0E8",
};

const chartBase = {
  tickColor: "rgba(245, 240, 232, 0.6)",
  gridColor: "rgba(245, 240, 232, 0.15)",
};

const tooltipBase = {
  backgroundColor: palette.surface,
  borderColor: palette.warm,
  borderWidth: 1,
  titleColor: palette.text,
  bodyColor: palette.text,
  padding: 8,
  displayColors: false,
  titleFont: { family: "DM Mono", size: 12, weight: "400" },
  bodyFont: { family: "DM Mono", size: 12, weight: "400" },
};

function createAreaGradient(ctx, chartArea, color) {
  const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
  gradient.addColorStop(0, `${color}99`);
  gradient.addColorStop(1, `${color}00`);
  return gradient;
}

const levelChart = new Chart(document.getElementById("levelChart"), {
  type: "bar",
  data: {
    labels: ["Óleo", "Sólido"],
    datasets: [
      {
        label: "Nível (%)",
        data: [0, 0],
        borderRadius: { topLeft: 4, topRight: 4, bottomLeft: 0, bottomRight: 0 },
        backgroundColor: [palette.accent, palette.accentSecondary],
      },
    ],
  },
  options: {
    animation: { duration: 800, easing: "easeInCubic" },
    plugins: {
      legend: { labels: { color: chartBase.tickColor, font: { family: "DM Mono", size: 11 } } },
      tooltip: tooltipBase,
    },
    scales: {
      y: {
        min: 0,
        max: 100,
        ticks: { display: false },
        grid: { color: chartBase.gridColor, drawTicks: false },
        border: { display: false },
      },
      x: {
        ticks: { display: false },
        grid: { display: false },
        border: { display: false },
      },
    },
  },
});

const historyChart = new Chart(document.getElementById("historyChart"), {
  type: "line",
  data: {
    labels: [],
    datasets: [
      {
        label: "Óleo",
        data: [],
        borderColor: palette.accent,
        backgroundColor: (context) => {
          const { chart } = context;
          const { ctx, chartArea } = chart;
          if (!chartArea) return "rgba(59,255,200,0.2)";
          return createAreaGradient(ctx, chartArea, palette.accent);
        },
        fill: true,
        tension: 0.35,
        pointRadius: 0,
        borderWidth: 2,
      },
      {
        label: "Sólido",
        data: [],
        borderColor: palette.accentSecondary,
        backgroundColor: (context) => {
          const { chart } = context;
          const { ctx, chartArea } = chart;
          if (!chartArea) return "rgba(200,255,59,0.2)";
          return createAreaGradient(ctx, chartArea, palette.accentSecondary);
        },
        fill: true,
        tension: 0.35,
        pointRadius: 0,
        borderWidth: 2,
      },
    ],
  },
  options: {
    animation: { duration: 800, easing: "easeInCubic" },
    plugins: {
      legend: { labels: { color: chartBase.tickColor, font: { family: "DM Mono", size: 11 } } },
      tooltip: tooltipBase,
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: { display: false },
        grid: { color: chartBase.gridColor, drawTicks: false },
        border: { display: false },
      },
      x: {
        ticks: { display: false },
        grid: { display: false },
        border: { display: false },
      },
    },
  },
});

function formatTimestamp(ts) {
  if (!ts) return "-";
  const date = new Date(ts);
  return Number.isNaN(date.getTime()) ? ts : date.toLocaleString("pt-BR");
}

function animateNumber(el, value, suffix = "", decimals = 0) {
  const start = Number((el.dataset.value || "0").replace(",", ".")) || 0;
  const end = Number(value) || 0;
  const duration = 420;
  const startTs = performance.now();
  function frame(now) {
    const p = Math.min((now - startTs) / duration, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    const current = start + (end - start) * eased;
    el.textContent = `${current.toFixed(decimals)}${suffix}`;
    if (p < 1) requestAnimationFrame(frame);
  }
  el.dataset.value = String(end);
  requestAnimationFrame(frame);
}

function severityFromLevel(level) {
  if (level >= 85) return "CHEIO";
  if (level >= 60) return "ATENÇÃO";
  return "NORMAL";
}

function setBadgeState(el, state) {
  if (!el) return;
  el.textContent = state;
  el.dataset.state = state;
}

function updateState(data) {
  const oil = Number(data.level_oil || 0);
  const solid = Number(data.level_solid || 0);

  animateNumber(ui.levelOil, oil, "%", 1);
  animateNumber(ui.levelSolid, solid, "%", 1);

  ui.ringOil.style.setProperty("--value", `${Math.max(0, Math.min(100, oil))}`);
  ui.ringSolid.style.setProperty("--value", `${Math.max(0, Math.min(100, solid))}`);

  setBadgeState(ui.irFull, data.ir_full ? "CHEIO" : "VAZIO");
  ui.lastUpdate.textContent = formatTimestamp(data.timestamp);
  setBadgeState(ui.oilChip, severityFromLevel(oil));
  setBadgeState(ui.solidChip, severityFromLevel(solid));
}

function updateStats(stats) {
  historyChart.data.labels = stats.labels || [];
  historyChart.data.datasets[0].data = stats.oil_daily || [];
  historyChart.data.datasets[1].data = stats.solid_daily || [];
  historyChart.update();

  animateNumber(ui.totalOil, Number(stats.total_oil_discards || 0), "", 0);
  animateNumber(ui.totalSolid, Number(stats.total_solid_discards || 0), "", 0);
  animateNumber(ui.totalLiters, Number(stats.total_liters_oil || 0), " L", 2);
  animateNumber(ui.totalKg, Number(stats.total_kg_solid || 0), " kg", 2);
}

function renderAlerts(items) {
  if (!items || items.length === 0) {
    ui.alerts.innerHTML = "<li>Nenhum alerta até agora.</li>";
    return;
  }
  ui.alerts.innerHTML = "";
  items.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = `${item.message} (${formatTimestamp(item.timestamp)})`;
    ui.alerts.appendChild(li);
  });
}

function prependDiscardFeed(entry) {
  if (ui.discardFeed.children.length === 1 && ui.discardFeed.textContent.includes("Nenhum descarte")) {
    ui.discardFeed.innerHTML = "";
  }
  const li = document.createElement("li");
  const typeLabel = entry.waste_type === "oleo" ? "Óleo" : entry.waste_type === "solido" ? "Sólido" : "Outro";
  li.textContent = `${typeLabel} x${entry.quantity} • ${formatTimestamp(entry.timestamp)}`;
  ui.discardFeed.prepend(li);
  while (ui.discardFeed.children.length > 12) {
    ui.discardFeed.lastElementChild.remove();
  }
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Erro HTTP ${response.status}`);
  return response.json();
}

async function loadInitialData() {
  try {
    const [stateData, statsData, alertsData] = await Promise.all([
      fetchJson("/api/state"),
      fetchJson("/api/stats?days=7"),
      fetchJson("/api/alerts?limit=15"),
    ]);
    updateState(stateData);
    updateStats(statsData);
    renderAlerts(alertsData.items || []);

    const oil = Number(stateData.level_oil || 0);
    const solid = Number(stateData.level_solid || 0);
    levelChart.data.datasets[0].data = [oil, solid];
    levelChart.update();
  } catch (err) {
    console.error("Falha ao carregar dados iniciais:", err);
  }
}

socket.on("connect", () => {
  ui.socketStatus.textContent = "Conectado em tempo real";
  ui.socketStatus.classList.add("online");
  ui.socketStatus.classList.remove("offline");
});

socket.on("disconnect", () => {
  ui.socketStatus.textContent = "Sem conexão em tempo real";
  ui.socketStatus.classList.remove("online");
  ui.socketStatus.classList.add("offline");
});

socket.on("telemetry", (payload) => {
  updateState(payload);
  levelChart.data.datasets[0].data = [
    Number(payload.level_oil || 0),
    Number(payload.level_solid || 0),
  ];
  levelChart.update();
});

socket.on("stats", (payload) => {
  updateStats(payload);
});

socket.on("discard", (payload) => {
  prependDiscardFeed(payload);
});

socket.on("alert", async () => {
  try {
    const data = await fetchJson("/api/alerts?limit=15");
    renderAlerts(data.items || []);
  } catch (err) {
    console.error("Falha ao atualizar alertas:", err);
  }
});

loadInitialData();
