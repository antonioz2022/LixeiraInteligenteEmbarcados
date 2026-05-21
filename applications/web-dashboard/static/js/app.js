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

const chartBase = {
  borderColor: "rgba(146, 191, 212, 0.3)",
  tickColor: "rgba(194, 223, 239, 0.88)",
  gridColor: "rgba(146, 191, 212, 0.16)",
};

const levelChart = new Chart(document.getElementById("levelChart"), {
  type: "bar",
  data: {
    labels: ["Óleo", "Sólido"],
    datasets: [
      {
        label: "Nível (%)",
        data: [0, 0],
        borderRadius: 12,
        backgroundColor: ["#29b6f6", "#7cd992"],
      },
    ],
  },
  options: {
    animation: { duration: 460, easing: "easeOutQuart" },
    plugins: {
      legend: { labels: { color: chartBase.tickColor } },
    },
    scales: {
      y: {
        min: 0,
        max: 100,
        ticks: { color: chartBase.tickColor },
        grid: { color: chartBase.gridColor },
      },
      x: {
        ticks: { color: chartBase.tickColor },
        grid: { color: "transparent" },
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
        borderColor: "#29b6f6",
        backgroundColor: "rgba(41,182,246,0.16)",
        fill: true,
        tension: 0.35,
      },
      {
        label: "Sólido",
        data: [],
        borderColor: "#7cd992",
        backgroundColor: "rgba(124,217,146,0.16)",
        fill: true,
        tension: 0.35,
      },
    ],
  },
  options: {
    animation: { duration: 460, easing: "easeOutQuart" },
    plugins: {
      legend: { labels: { color: chartBase.tickColor } },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: { color: chartBase.tickColor, precision: 0 },
        grid: { color: chartBase.gridColor },
      },
      x: {
        ticks: { color: chartBase.tickColor },
        grid: { color: chartBase.gridColor },
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
  if (level >= 85) return "Cheio";
  if (level >= 60) return "Atenção";
  return "Normal";
}

function updateState(data) {
  const oil = Number(data.level_oil || 0);
  const solid = Number(data.level_solid || 0);

  animateNumber(ui.levelOil, oil, "%", 1);
  animateNumber(ui.levelSolid, solid, "%", 1);

  ui.ringOil.style.setProperty("--value", `${Math.max(0, Math.min(100, oil))}`);
  ui.ringSolid.style.setProperty("--value", `${Math.max(0, Math.min(100, solid))}`);

  ui.irFull.textContent = data.ir_full ? "Sim" : "Não";
  ui.lastUpdate.textContent = formatTimestamp(data.timestamp);
  ui.oilChip.textContent = severityFromLevel(oil);
  ui.solidChip.textContent = severityFromLevel(solid);
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
