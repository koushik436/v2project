const connectionChip = document.getElementById("connectionChip");
const timestampChip = document.getElementById("timestampChip");
const predictionChip = document.getElementById("predictionChip");
const confidenceChip = document.getElementById("confidenceChip");
const riskStateLabel = document.getElementById("riskStateLabel");
const riskScore = document.getElementById("riskScore");
const whyPrediction = document.getElementById("whyPrediction");
const streamBadge = document.getElementById("streamBadge");

const temperatureValue = document.getElementById("temperatureValue");
const currentValue = document.getElementById("currentValue");
const voltageValue = document.getElementById("voltageValue");
const espStatusValue = document.getElementById("espStatusValue");
const deviceIdValue = document.getElementById("deviceIdValue");
const packetsValue = document.getElementById("packetsValue");
const errorsValue = document.getElementById("errorsValue");
const ageValue = document.getElementById("ageValue");
const sequenceValue = document.getElementById("sequenceValue");
const relayValue = document.getElementById("relayValue");
const failsafeValue = document.getElementById("failsafeValue");

const tempTrend = document.getElementById("tempTrend");
const currentTrend = document.getElementById("currentTrend");
const voltageTrend = document.getElementById("voltageTrend");

const staleOverlay = document.getElementById("staleOverlay");
const overlayMessage = document.getElementById("overlayMessage");
const toastContainer = document.getElementById("toastContainer");
const timelineList = document.getElementById("timelineList");
const featureBars = document.getElementById("featureBars");
const messageText = document.getElementById("messageText");
const dataStatusBadge = document.getElementById("dataStatusBadge");
const runtimeModeValue = document.getElementById("runtimeModeValue");
const dataSourceValue = document.getElementById("dataSourceValue");
const modelVersionValue = document.getElementById("modelVersionValue");
const modelStatusValue = document.getElementById("modelStatusValue");
const uptimeValue = document.getElementById("uptimeValue");
const avgLatencyValue = document.getElementById("avgLatencyValue");
const failureRateValue = document.getElementById("failureRateValue");
const autoHealCountValue = document.getElementById("autoHealCountValue");

const tempSpark = document.getElementById("tempSpark");
const currentSpark = document.getElementById("currentSpark");
const voltageSpark = document.getElementById("voltageSpark");
const riskSpark = document.getElementById("riskSpark");

const chartCanvas = document.getElementById("telemetryChart");
const chartCtx = chartCanvas.getContext("2d");

const state = {
  maxPoints: 45,
  labels: [],
  temperature: [],
  current: [],
  voltage: [],
  risk: [],
  timeline: [],
  previousPrediction: "-",
  previousConnection: "starting",
  previousValues: null,
  lastRecoveryMessage: "",
};

function formatNum(value, decimals = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(decimals);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function pushSeriesPoint(series, value) {
  series.push(value);
  if (series.length > state.maxPoints) series.shift();
}

function addTimelineEvent(kind, text, timestamp = "-") {
  state.timeline.unshift({ kind, text, timestamp });
  if (state.timeline.length > 14) state.timeline.pop();

  timelineList.innerHTML = "";
  state.timeline.forEach((event) => {
    const item = document.createElement("li");
    item.innerHTML = `<span>${event.text}</span><span class="timeline-time">${event.timestamp}</span>`;
    timelineList.appendChild(item);
  });
}

function showToast(text) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = text;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 2800);
}

function drawSparkline(svgEl, values, color) {
  if (!svgEl) return;
  const width = 160;
  const height = 46;
  svgEl.innerHTML = "";

  if (values.length < 2) {
    return;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 4) - 2;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  poly.setAttribute("fill", "none");
  poly.setAttribute("stroke", color);
  poly.setAttribute("stroke-width", "2");
  poly.setAttribute("points", points);
  svgEl.appendChild(poly);
}

function computeRiskScore(prediction) {
  if (prediction === "CRITICAL") return 88;
  if (prediction === "WARNING") return 57;
  if (prediction === "NORMAL") return 19;
  return 0;
}

function computeContributions(data) {
  const temp = Number(data.temperature ?? 0);
  const current = Number(data.current ?? 0);
  const voltage = Number(data.voltage ?? 0);
  const disconnected = (data.esp_status ?? "").toUpperCase() === "DISCONNECTED";

  const tempScore = temp > 33 ? 1 : temp >= 29 ? 0.62 : clamp(temp / 29, 0, 0.5);
  const currentScore = current > 1.2 ? 1 : current >= 1.0 ? 0.65 : clamp(current / 1.0, 0, 0.55);
  const voltageScore = voltage < 3.5 ? 1 : voltage <= 3.7 ? 0.66 : clamp((3.95 - voltage) / 0.25, 0, 0.45);
  const statusScore = disconnected ? 0.82 : 0.14;

  const byFeature = [
    { label: "Temperature", value: tempScore },
    { label: "Current", value: currentScore },
    { label: "Voltage", value: voltageScore },
    { label: "ESP Status", value: statusScore },
  ];

  byFeature.sort((a, b) => b.value - a.value);
  const lead = byFeature[0];
  const confidence = clamp(Math.round((lead.value * 0.72 + byFeature[1].value * 0.28) * 100), 10, 99);

  return {
    byFeature,
    confidence,
    reason: `${lead.label} is the strongest risk driver`,
  };
}

function renderFeatureBars(featureData) {
  featureBars.innerHTML = "";
  featureData.forEach((feature) => {
    const row = document.createElement("div");
    row.className = "feature-row";

    const header = document.createElement("div");
    header.className = "feature-head";
    header.innerHTML = `<span>${feature.label}</span><strong>${Math.round(feature.value * 100)}%</strong>`;

    const track = document.createElement("div");
    track.className = "bar-track";

    const fill = document.createElement("div");
    fill.className = "bar-fill";
    fill.style.width = `${Math.round(feature.value * 100)}%`;

    let color = "var(--ok)";
    if (feature.value > 0.75) color = "var(--critical)";
    else if (feature.value > 0.5) color = "var(--warn)";
    fill.style.background = color;

    track.appendChild(fill);
    row.appendChild(header);
    row.appendChild(track);
    featureBars.appendChild(row);
  });
}

function drawTelemetryChart() {
  const width = chartCanvas.clientWidth;
  const height = chartCanvas.height;
  chartCanvas.width = width;

  chartCtx.clearRect(0, 0, width, height);

  const allValues = [...state.temperature, ...state.current.map((v) => v * 25), ...state.voltage.map((v) => v * 8)];
  if (!allValues.length) return;

  const min = Math.min(...allValues) - 1;
  const max = Math.max(...allValues) + 1;
  const range = max - min || 1;

  function yFor(value) {
    return height - ((value - min) / range) * (height - 24) - 12;
  }

  function drawLine(values, color, transform = (v) => v) {
    if (values.length < 2) return;
    chartCtx.beginPath();
    chartCtx.strokeStyle = color;
    chartCtx.lineWidth = 2;

    values.forEach((value, index) => {
      const x = (index / (state.maxPoints - 1)) * (width - 18) + 9;
      const y = yFor(transform(value));
      if (index === 0) chartCtx.moveTo(x, y);
      else chartCtx.lineTo(x, y);
    });
    chartCtx.stroke();
  }

  chartCtx.strokeStyle = "rgba(255,255,255,0.13)";
  chartCtx.lineWidth = 1;
  for (let i = 1; i <= 4; i++) {
    const gy = (height / 5) * i;
    chartCtx.beginPath();
    chartCtx.moveTo(0, gy);
    chartCtx.lineTo(width, gy);
    chartCtx.stroke();
  }

  drawLine(state.temperature, "#ffbe0b");
  drawLine(state.current, "#00d1b2", (v) => v * 25);
  drawLine(state.voltage, "#64a7ff", (v) => v * 8);
}

function trendText(currentValue, previousValue, unit) {
  if (currentValue === null || previousValue === null || previousValue === undefined) return "-";
  const diff = currentValue - previousValue;
  if (Math.abs(diff) < 0.001) return `flat (${currentValue.toFixed(2)} ${unit})`;
  const arrow = diff > 0 ? "up" : "down";
  return `${arrow} ${Math.abs(diff).toFixed(2)} ${unit}`;
}

function applyTheme(prediction) {
  document.body.classList.remove("theme-normal", "theme-warning", "theme-critical");

  if (prediction === "CRITICAL") {
    document.body.classList.add("theme-critical");
    riskStateLabel.textContent = "Critical State";
  } else if (prediction === "WARNING") {
    document.body.classList.add("theme-warning");
    riskStateLabel.textContent = "Warning State";
  } else {
    document.body.classList.add("theme-normal");
    riskStateLabel.textContent = "Normal State";
  }
}

function isDegraded(connection) {
  return ["stale", "reconnecting", "error"].includes((connection || "").toLowerCase());
}

function updateOverlay(data) {
  const degraded = isDegraded(data.connection);
  staleOverlay.classList.toggle("hidden", !degraded);
  overlayMessage.textContent = data.message || "Waiting for telemetry stream";

  if (state.previousConnection && isDegraded(state.previousConnection) && data.connection === "connected") {
    showToast("Telemetry stream recovered");
    addTimelineEvent("recovery", "Stream recovered", data.timestamp || "-");
  }
  state.previousConnection = data.connection;
}

function updateMissionControl(data) {
  const prediction = (data.prediction || "-").toUpperCase();
  const connection = (data.connection || "unknown").toLowerCase();
  const dataStatus = (data.data_status || "unknown").toLowerCase();

  connectionChip.textContent = `Connection: ${connection}`;
  timestampChip.textContent = `Updated: ${data.timestamp || "-"}`;
  predictionChip.textContent = `Prediction: ${prediction}`;
  streamBadge.textContent = `Stream: ${connection}`;
  dataStatusBadge.textContent = `data: ${dataStatus}`;

  temperatureValue.textContent = formatNum(data.temperature, 2);
  currentValue.textContent = formatNum(data.current, 3);
  voltageValue.textContent = formatNum(data.voltage, 3);
  espStatusValue.textContent = (data.esp_status || "-").toUpperCase();
  deviceIdValue.textContent = `device: ${data.device_id || "-"}`;

  packetsValue.textContent = String(data.packets_received ?? 0);
  errorsValue.textContent = String(data.parse_errors ?? 0);
  ageValue.textContent = data.last_packet_age_seconds != null ? `${formatNum(data.last_packet_age_seconds, 2)} s` : "-";
  sequenceValue.textContent = data.sequence_number != null ? String(data.sequence_number) : "-";
  relayValue.textContent = data.relay_state || "-";
  failsafeValue.textContent = data.fail_safe ? "YES" : "NO";

  const explain = computeContributions(data);
  const confidencePct = typeof data.confidence === "number" ? Math.round(data.confidence * 100) : explain.confidence;
  confidenceChip.textContent = `Confidence: ${confidencePct}%`;
  whyPrediction.textContent = `Why: ${explain.reason}`;
  renderFeatureBars(explain.byFeature);

  runtimeModeValue.textContent = data.runtime_mode || "-";
  dataSourceValue.textContent = data.data_source || "-";
  modelVersionValue.textContent = data.model_version || "-";
  modelStatusValue.textContent = data.model_status || "-";
  uptimeValue.textContent = data.uptime_seconds != null ? `${formatNum(data.uptime_seconds, 1)} s` : "-";
  avgLatencyValue.textContent = `${formatNum(data.inference_avg_latency_ms ?? 0, 2)} ms`;
  failureRateValue.textContent = `${formatNum((data.inference_failure_rate ?? 0) * 100, 2)}%`;
  autoHealCountValue.textContent = String(data.auto_heal_count ?? 0);

  const score = computeRiskScore(prediction);
  riskScore.textContent = `${score}`;

  applyTheme(prediction);

  if (typeof data.temperature === "number") {
    pushSeriesPoint(state.temperature, data.temperature);
    pushSeriesPoint(state.current, data.current ?? 0);
    pushSeriesPoint(state.voltage, data.voltage ?? 0);
    pushSeriesPoint(state.risk, score);
    pushSeriesPoint(state.labels, data.timestamp || "-");

    drawSparkline(tempSpark, state.temperature, "#ffbe0b");
    drawSparkline(currentSpark, state.current, "#00d1b2");
    drawSparkline(voltageSpark, state.voltage, "#64a7ff");
    drawSparkline(riskSpark, state.risk, prediction === "CRITICAL" ? "#ff476f" : prediction === "WARNING" ? "#ff8f3d" : "#36d399");
    drawTelemetryChart();
  }

  tempTrend.textContent = trendText(data.temperature, state.previousValues?.temperature ?? null, "C");
  currentTrend.textContent = trendText(data.current, state.previousValues?.current ?? null, "A");
  voltageTrend.textContent = trendText(data.voltage, state.previousValues?.voltage ?? null, "V");

  if (state.previousPrediction !== prediction && prediction !== "-") {
    addTimelineEvent("state", `State changed to ${prediction}`, data.timestamp || "-");
    showToast(`Risk state is now ${prediction}`);
  }

  if (data.last_recovery_message && data.last_recovery_message !== state.lastRecoveryMessage) {
    showToast(data.last_recovery_message);
    addTimelineEvent("recovery", data.last_recovery_message, data.timestamp || "-");
    state.lastRecoveryMessage = data.last_recovery_message;
  }

  if (data.fail_safe) {
    addTimelineEvent("failsafe", "Fail-safe mode active", data.timestamp || "-");
  }

  state.previousPrediction = prediction;
  state.previousValues = {
    temperature: typeof data.temperature === "number" ? data.temperature : null,
    current: typeof data.current === "number" ? data.current : null,
    voltage: typeof data.voltage === "number" ? data.voltage : null,
  };

  messageText.textContent = data.message || "Live mission control ready";
  updateOverlay(data);
}

async function fetchLatest() {
  try {
    const response = await fetch("/api/latest", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    updateMissionControl(data);
  } catch (error) {
    updateOverlay({ connection: "error", message: `API error: ${error.message}` });
    connectionChip.textContent = "Connection: error";
    messageText.textContent = `API error: ${error.message}`;
  }
}

window.addEventListener("resize", drawTelemetryChart);

fetchLatest();
setInterval(fetchLatest, 1000);
