import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BatteryCharging,
  Clock3,
  Gauge,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  Thermometer,
  TrendingUp,
  Wifi,
  Zap,
  Radio,
} from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import Card from './components/Card';
import MetricCard from './components/MetricCard';
import RiskGauge from './components/RiskGauge';
import SectionTitle from './components/SectionTitle';
import StatusBadge from './components/StatusBadge';
import GeminiChat from './components/GeminiChat';
import ExecutiveScorecard from './components/ExecutiveScorecard';
import StoryTimeline from './components/StoryTimeline';
import Recommendations from './components/Recommendations';
const ModelCompare = lazy(() => import('./components/ModelCompare'));

const MAX_POINTS = 28;

const fmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
const timeFmt = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

const DASHBOARD_TABS = [
  { id: 'overview', label: 'Overview', hint: 'Status, risk, and guidance' },
  { id: 'diagnostics', label: 'Diagnostics', hint: 'Connection, timeline, model compare' },
  { id: 'analytics', label: 'Analytics', hint: 'Trends, what-if, fleet view' },
  { id: 'health', label: 'System Health', hint: 'Uptime, latency, and reliability' },
];

function toNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function cap(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function formatTimestamp(raw) {
  if (!raw) return '—';
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return timeFmt.format(parsed);
}

function getRiskMeta(prediction) {
  if (prediction === 'CRITICAL') {
    return {
      label: 'Critical',
      variant: 'critical',
      accent: 'from-rose-500/15 to-rose-500/5',
      action: 'Open diagnostics',
    };
  }
  if (prediction === 'WARNING') {
    return {
      label: 'Warning',
      variant: 'warning',
      accent: 'from-amber-500/15 to-amber-500/5',
      action: 'Review guidance',
    };
  }
  return {
    label: 'Normal',
    variant: 'safe',
    accent: 'from-emerald-500/15 to-emerald-500/5',
    action: 'Review analytics',
  };
}

function predictScore(prediction, confidence = 0) {
  if (prediction === 'CRITICAL') return cap(78 + confidence * 18, 0, 100);
  if (prediction === 'WARNING') return cap(45 + confidence * 20, 0, 100);
  if (prediction === 'NORMAL') return cap(12 + confidence * 10, 0, 100);
  return cap(confidence * 100, 0, 100);
}

function trendSlope(values) {
  if (!values || values.length < 2) return 0;
  const recent = values.slice(-6);
  const first = recent[0];
  const last = recent[recent.length - 1];
  return (last - first) / Math.max(1, recent.length - 1);
}

function buildIncidentSummary(prediction, temperature, current, voltage) {
  const tempPart = temperature > 33 ? 'rising thermal variance' : temperature >= 29 ? 'elevated battery temperature' : 'stable thermal behavior';
  const currentPart = current > 1.2 ? 'high current draw' : current >= 1.0 ? 'moderate current stress' : 'normal current flow';
  const voltagePart = voltage < 3.5 ? 'voltage sag' : voltage <= 3.7 ? 'slight voltage compression' : 'stable voltage behavior';

  if (prediction === 'CRITICAL') {
    return `Pack health degraded due to ${tempPart}, ${currentPart}, and ${voltagePart} over the last 90s.`;
  }
  if (prediction === 'WARNING') {
    return `Early warning detected from ${tempPart} and ${voltagePart}; the system remains recoverable.`;
  }
  return `Pack is operating normally with ${tempPart}, ${currentPart}, and ${voltagePart}.`;
}

function computeAiInsights(data, normalized, history, previousPredictionValue = normalized.prediction) {
  const temperature = toNumber(data.temperature, 0);
  const current = toNumber(data.current, 0);
  const voltage = toNumber(data.voltage, 0);
  const tempSlope = trendSlope(history.temperature.map((point) => point.value));
  const currentSlope = trendSlope(history.current.map((point) => point.value));
  const voltageSlope = trendSlope(history.voltage.map((point) => point.value));

  const thermalRisk = cap((temperature - 25) * 4 + Math.max(0, tempSlope) * 12, 0, 100);
  const currentRisk = cap((current - 0.7) * 60 + Math.max(0, currentSlope) * 180, 0, 100);
  const voltageRisk = cap((3.95 - voltage) * 120 + Math.max(0, -voltageSlope) * 160, 0, 100);
  const anomaly = cap(Math.round(thermalRisk * 0.38 + currentRisk * 0.34 + voltageRisk * 0.28 + (normalized.connection === 'connected' ? 0 : 16)), 0, 100);

  const confidencePct = cap(Math.round(normalized.confidence * 100), 0, 100);
  const uncertainty = cap(Math.round((100 - confidencePct) * 0.8 + anomaly * 0.12), 6, 42);
  const uncertaintyLow = cap(confidencePct - uncertainty, 0, 100);
  const uncertaintyHigh = cap(confidencePct + uncertainty, 0, 100);
  const score = predictScore(normalized.prediction, normalized.confidence);
  const modelPrediction = String(data.model_prediction || normalized.prediction || 'UNKNOWN').toUpperCase();
  const ensemblePrediction = String(data.ensemble_prediction || normalized.prediction || 'UNKNOWN').toUpperCase();
  const ensembleScore = cap(toNumber(data.ensemble_score, score), 0, 100);
  const oodScore = cap(toNumber(data.ood_score, anomaly), 0, 100);
  const adaptiveSource = String(data.adaptive_threshold_source || 'training_baseline');
  const sensorFaultLabel = String(data.sensor_fault_label || 'battery_issue');
  const sensorFaultReason = String(data.sensor_fault?.reason || data.sensor_fault_reason || 'Sensor diagnosis unavailable.');
  const recoveryAction = String(data.recovery_action || data.recovery_policy?.action || 'isolate_sensor');
  const recoveryRationale = String(data.recovery_rationale || data.recovery_policy?.rationale || 'Continue monitoring.');
  const oodLabel = data.ood_flagged || oodScore >= 55 ? 'OOD alert active' : 'Within expected distribution';
  const priority3 = data.priority_3 || {};
  const rulForecast = priority3.rul_forecast || {};
  const whatIfScenarios = Array.isArray(priority3.what_if_scenarios) ? priority3.what_if_scenarios : [];
  const digitalTwin = priority3.digital_twin || {};
  const driftMonitoring = priority3.drift_monitoring || {};
  const fleetIntelligence = priority3.fleet_intelligence || {};

  const fallbackLeadMinutes = normalized.prediction === 'CRITICAL'
    ? cap(1.5 + (100 - score) / 28, 0.4, 6)
    : normalized.prediction === 'WARNING'
      ? cap(6 + (100 - score) / 14, 2, 18)
      : cap(18 + (100 - score) / 6, 8, 60);

  const rulMinutes = cap(toNumber(rulForecast.minutes, fallbackLeadMinutes), 4, 240);
  const leadMinutes = rulMinutes;
  const rulCycles = cap(toNumber(rulForecast.cycles, Math.round(rulMinutes * 1.8)), 8, 520);
  const healthIndex = cap(toNumber(rulForecast.health_index, cap(100 - anomaly * 0.7, 0, 100)), 0, 100);
  const twinAlignment = cap(toNumber(digitalTwin.alignment, 0), 0, 100);
  const driftScore = cap(toNumber(driftMonitoring.drift_score, 0), 0, 100);
  const retrainRecommended = Boolean(driftMonitoring.retrain_recommended);
  const fleetRankings = Array.isArray(fleetIntelligence.rankings) ? fleetIntelligence.rankings : [];

  const features = [
    { label: 'Temperature spike', value: thermalRisk, explanation: temperature > 33 ? 'Thermal headroom is shrinking quickly.' : temperature >= 29 ? 'Temperature is elevated versus a safe baseline.' : 'Temperature is within the safe envelope.' },
    { label: 'Voltage spread', value: voltageRisk, explanation: voltage < 3.5 ? 'Voltage is sagging and contributing to instability.' : voltage <= 3.7 ? 'Voltage is compressed and trending downward.' : 'Voltage is stable.' },
    { label: 'Current surge', value: currentRisk, explanation: current > 1.2 ? 'Current demand is high and pulling the pack harder.' : current >= 1.0 ? 'Current is elevated above the nominal band.' : 'Current draw remains steady.' },
    { label: 'Connectivity', value: normalized.connection === 'connected' ? 18 : 78, explanation: normalized.connection === 'connected' ? 'Telemetry is healthy and continuously updating.' : 'Stream health is reduced, increasing uncertainty.' },
  ].sort((a, b) => b.value - a.value);

  const topDriver = features[0];
  const transition = previousPredictionValue === normalized.prediction ? '' : ` State changed from ${previousPredictionValue} to ${normalized.prediction}.`;

  return {
    anomaly,
    modelPrediction,
    ensemblePrediction,
    ensembleScore,
    oodScore,
    adaptiveSource,
    sensorFaultLabel,
    sensorFaultReason,
    recoveryAction,
    recoveryRationale,
    oodLabel,
    rulMinutes,
    leadMinutes,
    confidencePct,
    uncertainty,
    uncertaintyLow,
    uncertaintyHigh,
    features,
    whyChanged: `${topDriver.label} is the strongest driver because ${topDriver.explanation}${transition}`,
    summary: buildIncidentSummary(normalized.prediction, temperature, current, voltage),
    plainPrediction: normalized.prediction === 'CRITICAL' ? 'Immediate action recommended.' : normalized.prediction === 'WARNING' ? 'Monitor closely and prepare to intervene.' : 'No immediate action required.',
    plainRul: `${rulMinutes} minute${rulMinutes === 1 ? '' : 's'} of estimated remaining useful life`,
    plainAnomaly: anomaly >= 75 ? 'High anomaly pressure detected.' : anomaly >= 45 ? 'Moderate anomaly pressure detected.' : 'Low anomaly pressure detected.',
    confidenceAlert: confidencePct < 70 || anomaly > 72 || oodScore > 60,
    confidenceLabel: confidencePct < 70 ? 'Low confidence - operator review recommended' : 'Calibrated confidence looks stable',
    safetyLayer: `Adaptive thresholds from ${adaptiveSource}; sensor diagnosis: ${sensorFaultLabel}.`,
    safetyDetail: `${sensorFaultReason} Recovery: ${recoveryAction} (${recoveryRationale}).`,
    distributionDetail: `${oodLabel} (${oodScore}/100). Ensemble score ${ensembleScore}/100 from ${ensemblePrediction}.`,
    priority3Summary: String(priority3.priority_3_summary || 'Advanced analytics unavailable.'),
    whatIfScenarios,
    twinAlignment,
    driftScore,
    retrainRecommended,
    fleetRankings,
    fleetMode: String(fleetIntelligence.mode || 'synthetic_demo'),
    digitalTwinNarrative: String(digitalTwin.narrative || 'Digital twin unavailable.'),
    rulCycles,
    healthIndex,
  };
}

function percentageDelta(current, previous) {
  if (!Number.isFinite(current) || !Number.isFinite(previous) || previous === 0) {
    return 0;
  }
  return ((current - previous) / Math.abs(previous)) * 100;
}

function riskTone(prediction) {
  if (prediction === 'CRITICAL') return 'danger';
  if (prediction === 'WARNING') return 'moderate';
  return 'safe';
}

function predictionTone(prediction) {
  if (prediction === 'CRITICAL') return 'critical';
  if (prediction === 'WARNING') return 'warning';
  return 'safe';
}

function deriveStatus(data = {}) {
  const connection = String(data.connection || 'unknown').toLowerCase();
  const prediction = String(data.prediction || 'unknown').toUpperCase();
  const dataStatus = String(data.data_status || 'unknown').toLowerCase();

  return {
    connection,
    prediction,
    dataStatus,
    runtimeMode: data.runtime_mode || '—',
    source: data.data_source || '—',
    modelVersion: data.model_version || '—',
    modelStatus: data.model_status || '—',
    confidence: cap(toNumber(data.confidence, 0), 0, 1),
  };
}

function seriesPoint(value) {
  return { value: Number(value.toFixed ? value.toFixed(3) : value) };
}

function addPoint(list, value) {
  const next = [...list, { value: Number(value) }];
  return next.slice(-MAX_POINTS);
}

function AnimatedValue({ value, suffix = '', prefix = '', className = '' }) {
  const [display, setDisplay] = useState(value);
  const previous = useRef(value);

  useEffect(() => {
    const start = previous.current;
    const end = value;
    const duration = 280;
    const startedAt = performance.now();
    let frame = 0;

    const step = (now) => {
      const progress = cap((now - startedAt) / duration, 0, 1);
      const next = start + (end - start) * progress;
      setDisplay(next);
      if (progress < 1) {
        frame = requestAnimationFrame(step);
      } else {
        previous.current = end;
      }
    };

    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return <span className={className}>{prefix}{fmt.format(display)}{suffix}</span>;
}

function App() {
  const [latest, setLatest] = useState(null);
  const [history, setHistory] = useState({ temperature: [], current: [], voltage: [], risk: [], connection: [] });
  const [timeline, setTimeline] = useState([
    { type: 'info', text: 'Waiting for telemetry stream...', timestamp: '—' },
  ]);
  const [toast, setToast] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('overview');
  const previousPrediction = useRef('');
  const previousConnection = useRef('');

  const updateTimeline = (type, text, timestamp) => {
    setTimeline((items) => [{ type, text, timestamp }, ...items].slice(0, 8));
  };

  const showToast = (message, tone = 'info') => {
    setToast({ message, tone, id: Date.now() });
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => setToast(null), 2600);
  };

  const fetchLatest = async () => {
    try {
      const response = await fetch('/api/latest', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const normalized = deriveStatus(data);

      setLatest(data);
      setError('');
      setIsLoading(false);

      setHistory((current) => ({
        temperature: addPoint(current.temperature, toNumber(data.temperature, 0)),
        current: addPoint(current.current, toNumber(data.current, 0)),
        voltage: addPoint(current.voltage, toNumber(data.voltage, 0)),
        risk: addPoint(current.risk, predictScore(normalized.prediction, normalized.confidence)),
        connection: addPoint(current.connection, normalized.connection === 'connected' ? 1 : normalized.connection === 'stale' ? 0.6 : normalized.connection === 'disconnected' ? 0.1 : 0.3),
      }));

      if (previousPrediction.current && previousPrediction.current !== normalized.prediction) {
        updateTimeline('state', `Prediction moved to ${normalized.prediction}`, formatTimestamp(data.timestamp));
        showToast(`Risk state: ${normalized.prediction}`, normalized.prediction === 'CRITICAL' ? 'danger' : normalized.prediction === 'WARNING' ? 'warning' : 'success');
      }

      if (previousConnection.current && previousConnection.current !== normalized.connection) {
        updateTimeline('connection', `Connection changed to ${normalized.connection}`, formatTimestamp(data.timestamp));
        if (normalized.connection === 'connected' && previousConnection.current !== 'connected') {
          showToast('Telemetry recovered', 'success');
        }
      }

      if (data.last_recovery_message) {
        updateTimeline('recovery', data.last_recovery_message, formatTimestamp(data.timestamp));
      }

      previousPrediction.current = normalized.prediction;
      previousConnection.current = normalized.connection;
    } catch (err) {
      setError(err.message);
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLatest();
    const timer = window.setInterval(fetchLatest, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const loadExtras = async () => {
      try {
        const s = await fetch('/api/story?n=8').then((r) => r.json());
        setStory(s.story || []);
      } catch (e) {
        setStory([]);
      }
      try {
        const r = await fetch('/api/recommendations').then((r) => r.json());
        setRecs(r.recommendations || []);
      } catch (e) {
        setRecs([]);
      }
    };
    loadExtras();
    const t = window.setInterval(loadExtras, 4000);
    return () => window.clearInterval(t);
  }, []);

  const data = latest || {};
  const normalized = deriveStatus(data);
  const riskScore = predictScore(normalized.prediction, normalized.confidence);
  const tone = riskTone(normalized.prediction);
  const aiInsights = computeAiInsights(data, normalized, history, previousPrediction.current);
  const riskMeta = getRiskMeta(normalized.prediction);
  const primaryAction = riskMeta.action;
  const riskCopy = normalized.prediction === 'CRITICAL'
    ? 'Critical thermal or electrical risk detected.'
    : normalized.prediction === 'WARNING'
      ? 'Early degradation signals are active.'
      : 'System operating in a stable safe zone.';

  const metricCards = [
    {
      title: 'Temperature',
      icon: Thermometer,
      value: toNumber(data.temperature, 0),
      unit: '°C',
      delta: percentageDelta(toNumber(data.temperature, 0), history.temperature[history.temperature.length - 2]?.value ?? toNumber(data.temperature, 0)),
      data: history.temperature,
      stroke: '#fbbf24',
      accent: 'from-amber-300 to-orange-300',
      format: (v) => fmt.format(v),
    },
    {
      title: 'Current',
      icon: Zap,
      value: toNumber(data.current, 0),
      unit: 'A',
      delta: percentageDelta(toNumber(data.current, 0), history.current[history.current.length - 2]?.value ?? toNumber(data.current, 0)),
      data: history.current,
      stroke: '#34d399',
      accent: 'from-emerald-300 to-teal-300',
      format: (v) => fmt.format(v),
    },
    {
      title: 'Voltage',
      icon: BatteryCharging,
      value: toNumber(data.voltage, 0),
      unit: 'V',
      delta: percentageDelta(toNumber(data.voltage, 0), history.voltage[history.voltage.length - 2]?.value ?? toNumber(data.voltage, 0)),
      data: history.voltage,
      stroke: '#60a5fa',
      accent: 'from-sky-300 to-blue-300',
      format: (v) => fmt.format(v),
    },
  ];

  const chartData = useMemo(
    () =>
      history.temperature.map((point, index) => ({
        tick: index,
        Temperature: point.value,
        Current: history.current[index]?.value ?? null,
        Voltage: history.voltage[index]?.value ?? null,
        Risk: history.risk[index]?.value ?? null,
      })),
    [history],
  );

  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [story, setStory] = useState([]);
  const [recs, setRecs] = useState([]);

  // Voice alerts for critical transitions
  useEffect(() => {
    if (!voiceEnabled) return;
    const prev = previousPrediction.current || '';
    if (prev !== normalized.prediction && normalized.prediction === 'CRITICAL') {
      const text = `Critical risk detected. ${aiInsights.summary || ''} Recommended action: ${aiInsights.recoveryAction || aiInsights.recoveryRationale || ''}`;
      try {
        if (window && window.speechSynthesis) {
          const utter = new SpeechSynthesisUtterance(text);
          window.speechSynthesis.cancel();
          window.speechSynthesis.speak(utter);
        }
      } catch (e) {
        // ignore speech errors
      }
    }
  }, [normalized.prediction, aiInsights, voiceEnabled]);

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none absolute inset-0 opacity-70">
        <div className="absolute -left-24 top-0 h-80 w-80 rounded-full bg-sky-500/10 blur-3xl" />
        <div className="absolute right-[-120px] top-24 h-96 w-96 rounded-full bg-fuchsia-500/10 blur-3xl" />
        <div className="absolute bottom-[-120px] left-1/3 h-96 w-96 rounded-full bg-emerald-500/10 blur-3xl" />
        <div className="absolute inset-0 grid-pattern opacity-25" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: 'easeOut' }}
        className="relative z-10 mx-auto flex min-h-screen w-full max-w-[1600px] flex-col px-4 pb-8 pt-4 sm:px-6 lg:px-8"
      >
        <header className="sticky top-3 z-30 mb-5 rounded-3xl border border-white/8 bg-slate-950/70 px-4 py-4 shadow-2xl shadow-black/20 backdrop-blur-2xl md:px-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-400 via-cyan-300 to-emerald-300 text-slate-950 shadow-lg shadow-sky-500/20">
                <Sparkles className="h-7 w-7" />
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-sky-300/80">EV Mission Control</p>
                <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-50 md:text-4xl">EV Battery Risk Intelligence</h1>
                <p className="mt-1 max-w-3xl text-sm text-slate-400 md:text-base">
                  Modern, production-grade monitoring for battery safety, fault detection, and AI-driven recovery.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge
                variant={normalized.connection === 'connected' ? 'connected' : normalized.connection === 'stale' ? 'warning' : 'critical'}
                label={`Connection: ${normalized.connection}`}
              />
              <StatusBadge
                variant={predictionTone(normalized.prediction)}
                label={`Prediction: ${normalized.prediction}`}
                tone={normalized.prediction === 'NORMAL' ? 'shadow-[0_0_18px_rgba(52,211,153,0.18)]' : ''}
              />
              <StatusBadge variant="neutral" label={`Updated: ${formatTimestamp(data.timestamp)}`} />
            </div>
          </div>
        </header>

        <Card className={`mb-5 overflow-hidden border-white/10 bg-gradient-to-br ${riskMeta.accent}`}>
          <div className="grid gap-5 lg:grid-cols-[1.12fr_0.88fr] lg:items-center">
            <div>
              <SectionTitle
                eyebrow="Status summary"
                title="Understand the system in 5 seconds"
                description="Risk, reason, and action are shown first so a new user can decide what matters immediately."
              />

              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-4">
                  <div className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Risk level</div>
                  <div className="mt-2 flex items-center gap-2">
                    <StatusBadge variant={riskMeta.variant} label={riskMeta.label} />
                  </div>
                  <div className="mt-3 text-3xl font-semibold text-slate-50">{fmt.format(riskScore)}</div>
                  <div className="mt-1 text-sm text-slate-400">out of 100</div>
                </div>

                <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-4 sm:col-span-2">
                  <div className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Key reason</div>
                  <p className="mt-2 text-base leading-7 text-slate-100 md:text-lg">{aiInsights.summary}</p>
                  <p className="mt-3 text-sm leading-6 text-slate-400">{aiInsights.whyChanged}</p>
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setActiveTab(riskMeta.variant === 'safe' ? 'analytics' : 'diagnostics')}
                      className="rounded-2xl bg-gradient-to-r from-sky-400 to-cyan-300 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:brightness-105"
                    >
                      {primaryAction}
                    </button>
                    <button
                      type="button"
                      onClick={() => setVoiceEnabled((v) => !v)}
                      className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-semibold text-slate-100 transition hover:border-white/20 hover:bg-white/10"
                    >
                      Voice alerts: {voiceEnabled ? 'On' : 'Off'}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-3xl border border-white/10 bg-slate-950/55 p-3 shadow-2xl shadow-black/20">
              <RiskGauge
                score={riskScore}
                label={normalized.prediction === 'CRITICAL' ? 'Danger' : normalized.prediction === 'WARNING' ? 'Moderate' : 'Safe'}
                tone={tone}
                subtitle="Live risk score"
              />
            </div>
          </div>
        </Card>

        <div className="mb-5 flex flex-wrap gap-2 rounded-3xl border border-white/10 bg-slate-950/50 p-2 backdrop-blur-xl">
          {DASHBOARD_TABS.map((tab) => {
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`flex min-w-[11rem] flex-1 flex-col rounded-2xl px-4 py-3 text-left transition ${active ? 'bg-sky-400/10 text-white ring-1 ring-sky-400/30' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'}`}
                aria-pressed={active}
              >
                <span className="text-sm font-semibold">{tab.label}</span>
                <span className="mt-1 text-xs leading-5 text-slate-500">{tab.hint}</span>
              </button>
            );
          })}
        </div>

        <main className="grid flex-1 gap-5">
          {error ? (
            <Card className="border-rose-500/20 bg-rose-500/10 text-rose-100" hover={false}>
              <div className="flex items-center gap-3">
                <AlertTriangle className="h-5 w-5" />
                <div>
                  <div className="font-semibold">Live fetch error</div>
                  <div className="text-sm text-rose-100/80">{error}</div>
                </div>
              </div>
            </Card>
          ) : null}

          {activeTab === 'overview' ? (
          <>
          <section className="mb-8">
            <Card>
              <SectionTitle
                eyebrow="AI Assistant"
                title="Diagnostic Chat"
                description="Ask questions about the current battery telemetry and get instant AI-driven analysis."
              />
              <GeminiChat />
            </Card>
          </section>

          <section className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
            <Card>
              <SectionTitle
                eyebrow="AI intelligence"
                title="Battery snapshot"
                description="A simple summary of risk, remaining life, and anomaly pressure in one place."
              />

              <div className="grid gap-4 md:grid-cols-3">
                {[
                  {
                    label: 'Battery risk class',
                    value: normalized.prediction,
                    toneClass: tone === 'danger' ? 'text-rose-100' : tone === 'moderate' ? 'text-amber-100' : 'text-emerald-100',
                    helper: aiInsights.plainPrediction,
                    accent: tone,
                  },
                  {
                    label: 'Remaining useful life',
                    value: `${aiInsights.rulMinutes} min`,
                    toneClass: 'text-sky-100',
                    helper: aiInsights.plainRul,
                    accent: 'safe',
                  },
                  {
                    label: 'Anomaly score',
                    value: `${aiInsights.anomaly}/100`,
                    toneClass: aiInsights.anomaly >= 75 ? 'text-rose-100' : aiInsights.anomaly >= 45 ? 'text-amber-100' : 'text-emerald-100',
                    helper: aiInsights.plainAnomaly,
                    accent: aiInsights.anomaly >= 75 ? 'danger' : aiInsights.anomaly >= 45 ? 'moderate' : 'safe',
                  },
                ].map((item) => (
                  <div key={item.label} className="rounded-2xl border border-white/10 bg-white/5 p-4 transition hover:border-white/20 hover:bg-white/8">
                    <div className="text-[11px] uppercase tracking-[0.3em] text-slate-500">{item.label}</div>
                    <div className={`mt-3 text-2xl font-semibold ${item.toneClass}`}>{item.value}</div>
                    <div className="mt-2 text-sm leading-6 text-slate-400">{item.helper}</div>
                  </div>
                ))}
              </div>

              <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-300">
                  <Sparkles className="h-4 w-4 text-sky-300" />
                  Natural language incident summary
                </div>
                <p className="text-sm leading-6 text-slate-200">{aiInsights.summary}</p>
              </div>
            </Card>

            <Card>
              <SectionTitle
                eyebrow="Trust"
                title="How sure is the model?"
                description="Confidence and uncertainty are shown together so the result is easier to trust and explain."
              />

              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-end justify-between gap-4">
                  <div>
                    <div className="text-sm text-slate-400">Calibrated confidence</div>
                    <div className="mt-1 text-4xl font-semibold text-slate-50">{aiInsights.confidencePct}%</div>
                  </div>
                  <div className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${aiInsights.confidenceAlert ? 'border-amber-500/25 bg-amber-500/10 text-amber-100' : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-100'}`}>
                    {aiInsights.confidenceAlert ? 'Low-confidence alert' : 'Confidence healthy'}
                  </div>
                </div>

                <div className="mt-4">
                  <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-[0.28em] text-slate-500">
                    <span>Uncertainty band</span>
                    <span>{aiInsights.uncertaintyLow}% - {aiInsights.uncertaintyHigh}%</span>
                  </div>
                  <div className="relative h-3 rounded-full bg-white/8">
                    <div className="absolute left-[var(--low)] right-[var(--high)] top-0 h-full rounded-full bg-gradient-to-r from-sky-400 via-cyan-300 to-emerald-300 shadow-[0_0_24px_rgba(56,189,248,0.35)]" style={{ '--low': `${100 - aiInsights.uncertaintyHigh}%`, '--high': `${100 - aiInsights.uncertaintyLow}%` }} />
                    <div className="absolute top-[-4px] h-5 w-1 rounded-full bg-slate-100" style={{ left: `${aiInsights.confidencePct}%` }} />
                  </div>
                </div>

                <div className="mt-4 grid gap-3 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                  <div className="flex items-center justify-between text-sm text-slate-300">
                    <span>Why this changed</span>
                    <span className="text-xs uppercase tracking-[0.24em] text-slate-500">Top driver</span>
                  </div>
                  <p className="text-sm leading-6 text-slate-200">{aiInsights.whyChanged}</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-300">
                      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Lead time</div>
                      <div className="mt-1 font-semibold text-slate-50">{aiInsights.leadMinutes.toFixed(1)} minutes before critical threshold</div>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-300">
                      <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Uncertainty band</div>
                      <div className="mt-1 font-semibold text-slate-50">±{aiInsights.uncertainty}% around confidence</div>
                    </div>
                  </div>
                </div>
              </div>
            </Card>
          </section>

          <section className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
            <Card className="overflow-hidden">
              <div className="grid gap-6 lg:grid-cols-[1fr_auto] lg:items-center">
                <div>
                  <div className="mb-4 flex items-center gap-2 text-sm font-medium text-slate-300">
                    <Gauge className="h-4 w-4 text-sky-300" />
                    Main risk view
                  </div>
                  <h2 className="max-w-xl text-3xl font-semibold tracking-tight text-slate-50 md:text-5xl">
                    <span className="text-gradient">{normalized.prediction}</span> risk, presented with clarity.
                  </h2>
                  <p className="mt-3 max-w-xl text-sm leading-6 text-slate-400 md:text-base">{riskCopy}</p>

                  <div className="mt-6 flex flex-wrap items-center gap-3">
                    <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-semibold ${tone === 'danger' ? 'border-rose-500/20 bg-rose-500/10 text-rose-100' : tone === 'moderate' ? 'border-amber-500/20 bg-amber-500/10 text-amber-100' : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-100'}`}>
                      {tone === 'danger' ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
                      <span className="mono">{fmt.format(riskScore)}</span>
                      <span className="opacity-75">/ 100</span>
                    </div>
                    <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-300">
                      <ShieldCheck className="h-4 w-4 text-emerald-300" />
                      Confidence {(normalized.confidence * 100).toFixed(0)}%
                    </div>
                    <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-300">
                      <TrendingUp className="h-4 w-4 text-sky-300" />
                      {normalized.dataStatus}
                    </div>
                  </div>
                </div>

                <RiskGauge
                  score={riskScore}
                  label={normalized.prediction === 'CRITICAL' ? 'Danger' : normalized.prediction === 'WARNING' ? 'Moderate' : 'Safe'}
                  tone={tone}
                  subtitle="Radial live risk score"
                />
              </div>
            </Card>

            <Card>
              <SectionTitle
                eyebrow="Control"
                title="Connection and recovery"
                description="See whether the data stream is healthy and use reconnect when the stream needs a refresh."
                action={
                  <button
                    type="button"
                    onClick={() => {
                      showToast('Reconnect requested', 'info');
                      fetchLatest();
                    }}
                    className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm font-medium text-slate-200 transition hover:border-sky-400/30 hover:bg-sky-400/10"
                  >
                    <RefreshCcw className="h-4 w-4" />
                    Reconnect
                  </button>
                }
              />

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="mb-2 flex items-center gap-2 text-sm text-slate-400"><Wifi className="h-4 w-4 text-emerald-300" /> ESP Status</div>
                  <div className="flex items-end justify-between gap-3">
                    <div>
                      <div className="text-xl font-semibold text-slate-50">{String(data.esp_status || '—')}</div>
                      <div className="mt-1 text-xs uppercase tracking-[0.28em] text-slate-500">device {String(data.device_id || '—')}</div>
                    </div>
                    <div className={`h-3 w-3 rounded-full ${String(data.esp_status || '').toUpperCase() === 'CONNECTED' ? 'animate-pulse bg-emerald-400 shadow-[0_0_20px_rgba(52,211,153,0.7)]' : 'bg-rose-400 shadow-[0_0_20px_rgba(251,113,133,0.55)]'}`} />
                  </div>
                  <div className="mt-4 h-20 rounded-2xl border border-white/5 bg-slate-950/40 p-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={history.connection.map((point, index) => ({ tick: index, value: point.value }))}>
                        <defs>
                          <linearGradient id="connFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#34d399" stopOpacity={0.35} />
                            <stop offset="100%" stopColor="#34d399" stopOpacity={0.02} />
                          </linearGradient>
                        </defs>
                        <Area type="monotone" dataKey="value" stroke="#34d399" fill="url(#connFill)" strokeWidth={2} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="mb-2 flex items-center gap-2 text-sm text-slate-400"><Clock3 className="h-4 w-4 text-sky-300" /> Runtime</div>
                  <div className="space-y-3 text-sm text-slate-300">
                    <div className="flex items-center justify-between"><span>Mode</span><span className="font-medium text-slate-50">{normalized.runtimeMode}</span></div>
                    <div className="flex items-center justify-between"><span>Source</span><span className="font-medium text-slate-50">{normalized.source}</span></div>
                    <div className="flex items-center justify-between"><span>Model</span><span className="font-medium text-slate-50">{normalized.modelVersion}</span></div>
                    <div className="flex items-center justify-between"><span>Status</span><span className="font-medium text-slate-50">{normalized.modelStatus}</span></div>
                  </div>
                </div>
              </div>
            </Card>
          </section>

          <section className="grid gap-5 md:grid-cols-3">
            {metricCards.map((card) => (
              <MetricCard
                key={card.title}
                icon={card.icon}
                title={card.title}
                value={card.value}
                unit={card.unit}
                delta={card.delta}
                data={card.data}
                stroke={card.stroke}
                accent={card.accent}
                formatValue={card.format}
              />
            ))}
          </section>
          </>
          ) : null}

          {activeTab === 'analytics' ? (
          <>
          <section className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
            <Card>
              <SectionTitle
                eyebrow="Telemetry"
                title="Live signal trends"
                description="A clean production chart with smooth transitions, responsive layout, and live updates from the backend API."
              />

              <div className="h-[320px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                    <defs>
                      <linearGradient id="tempGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#fbbf24" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#fbbf24" stopOpacity={0.02} />
                      </linearGradient>
                      <linearGradient id="currentGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#34d399" stopOpacity={0.32} />
                        <stop offset="100%" stopColor="#34d399" stopOpacity={0.02} />
                      </linearGradient>
                      <linearGradient id="voltageGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#60a5fa" stopOpacity={0.34} />
                        <stop offset="100%" stopColor="#60a5fa" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="rgba(148,163,184,0.12)" strokeDasharray="3 6" vertical={false} />
                    <XAxis dataKey="tick" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} width={36} />
                    <Tooltip
                      contentStyle={{
                        borderRadius: 16,
                        background: 'rgba(2,6,23,0.95)',
                        border: '1px solid rgba(148,163,184,0.18)',
                        boxShadow: '0 20px 40px rgba(2,6,23,0.4)',
                      }}
                      itemStyle={{ color: '#e2e8f0' }}
                      labelStyle={{ color: '#cbd5e1' }}
                    />
                    <ReferenceLine y={3.5} stroke="rgba(248,113,113,0.45)" strokeDasharray="4 4" />
                    <Area type="monotone" dataKey="Temperature" stroke="#fbbf24" fill="url(#tempGradient)" strokeWidth={2.5} />
                    <Area type="monotone" dataKey="Current" stroke="#34d399" fill="url(#currentGradient)" strokeWidth={2.5} />
                    <Area type="monotone" dataKey="Voltage" stroke="#60a5fa" fill="url(#voltageGradient)" strokeWidth={2.5} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <div className="grid gap-5">
              <Card>
                <SectionTitle
                  eyebrow="Advanced analytics"
                  title="RUL, what-if simulation, and digital twin"
                  description="Shows what could happen next, how long the pack may last, and whether the model should be retrained."
                />

                <div className="grid gap-3 md:grid-cols-3">
                  {[
                    {
                      label: 'RUL forecast',
                      value: `${aiInsights.rulMinutes} min`,
                      helper: `${aiInsights.rulCycles} cycles projected`,
                      tone: 'text-sky-100',
                    },
                    {
                      label: 'Health index',
                      value: `${aiInsights.healthIndex}/100`,
                      helper: 'Single score for demo storytelling',
                      tone: aiInsights.healthIndex >= 70 ? 'text-emerald-100' : aiInsights.healthIndex >= 40 ? 'text-amber-100' : 'text-rose-100',
                    },
                    {
                      label: 'Twin alignment',
                      value: `${aiInsights.twinAlignment}%`,
                      helper: aiInsights.digitalTwinNarrative,
                      tone: aiInsights.twinAlignment >= 80 ? 'text-emerald-100' : aiInsights.twinAlignment >= 55 ? 'text-amber-100' : 'text-rose-100',
                    },
                  ].map((item) => (
                    <div key={item.label} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <div className="text-[11px] uppercase tracking-[0.3em] text-slate-500">{item.label}</div>
                      <div className={`mt-3 text-2xl font-semibold ${item.tone}`}>{item.value}</div>
                      <div className="mt-2 text-sm leading-6 text-slate-400">{item.helper}</div>
                    </div>
                  ))}
                </div>

                <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                  <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-300">
                    <TrendingUp className="h-4 w-4 text-sky-300" />
                    Drift and retrain signal
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-sm text-slate-300">
                    <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">Drift score {aiInsights.driftScore}/100</span>
                    <span className={`rounded-full border px-3 py-1.5 ${aiInsights.retrainRecommended ? 'border-amber-500/20 bg-amber-500/10 text-amber-100' : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-100'}`}>
                      {aiInsights.retrainRecommended ? 'Retrain recommended' : 'Retrain not required'}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-400">{aiInsights.priority3Summary}</p>
                </div>

                <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-300">
                    <Sparkles className="h-4 w-4 text-emerald-300" />
                    What-if simulation sandbox
                  </div>
                  <div className="grid gap-2 md:grid-cols-2">
                    {aiInsights.whatIfScenarios.map((scenario) => (
                      <div key={scenario.name} className="rounded-xl border border-white/10 bg-slate-950/40 p-3">
                        <div className="text-sm font-semibold text-slate-50">{scenario.name}</div>
                        <div className="mt-1 text-xs uppercase tracking-[0.24em] text-slate-500">Projected {scenario.prediction} risk</div>
                        <div className="mt-2 text-sm text-slate-300">Risk score {scenario.risk_score}/100</div>
                      </div>
                    ))}
                  </div>
                </div>
              </Card>

              <Card>
                <SectionTitle
                  eyebrow="Fleet intelligence"
                  title="Synthetic fleet ranking"
                  description={`A small fleet view (${aiInsights.fleetMode}) that shows how risk compares across multiple assets.`}
                />

                <div className="space-y-3">
                  {aiInsights.fleetRankings.map((asset, index) => (
                    <div key={asset.name} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Rank {index + 1}</div>
                          <div className="mt-1 text-sm font-semibold text-slate-50">{asset.name}</div>
                        </div>
                        <div className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${asset.risk_score >= 70 ? 'border-rose-500/20 bg-rose-500/10 text-rose-100' : asset.risk_score >= 40 ? 'border-amber-500/20 bg-amber-500/10 text-amber-100' : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-100'}`}>
                          {asset.risk_score}/100
                        </div>
                      </div>
                      <div className="mt-2 text-sm leading-6 text-slate-400">
                        {asset.prediction} prediction with thermal {asset.components.thermal} / electrical {asset.components.electrical} / voltage {asset.components.voltage} pressure.
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </section>
          </>
          ) : null}

          {activeTab === 'health' ? (
          <section className="grid gap-5 md:grid-cols-2">
            <Card>
              <SectionTitle eyebrow="Packet health" title="Compact operational stats" />
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Packets', value: data.packets_received ?? 0, tone: 'text-sky-100' },
                  { label: 'Errors', value: data.parse_errors ?? 0, tone: 'text-rose-100' },
                  { label: 'Packet age', value: data.last_packet_age_seconds != null ? `${fmt.format(data.last_packet_age_seconds)}s` : '—', tone: 'text-slate-50' },
                  { label: 'Sequence', value: data.sequence_number ?? '—', tone: 'text-slate-50' },
                  { label: 'Relay', value: String(data.relay_state || '—'), tone: 'text-slate-50' },
                  { label: 'Fail-safe', value: data.fail_safe ? 'YES' : 'NO', tone: data.fail_safe ? 'text-rose-100' : 'text-emerald-100' },
                ].map((item) => (
                  <div key={item.label} className="rounded-2xl border border-white/10 bg-white/5 p-3.5 transition hover:border-white/20 hover:bg-white/8">
                    <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">{item.label}</div>
                    <div className={`mt-2 text-xl font-semibold ${item.tone}`}>{item.value}</div>
                  </div>
                ))}
              </div>
            </Card>

            <Card>
              <SectionTitle eyebrow="Health" title="System health" />
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  { icon: Clock3, label: 'Uptime', value: `${fmt.format(data.uptime_seconds ?? 0)} s` },
                  { icon: Gauge, label: 'Avg latency', value: `${fmt.format(data.inference_avg_latency_ms ?? 0)} ms` },
                  { icon: TrendingUp, label: 'Failure rate', value: `${fmt.format((data.inference_failure_rate ?? 0) * 100)}%` },
                  { icon: Radio, label: 'Auto-heal', value: `${data.auto_heal_count ?? 0}` },
                ].map((item) => {
                  const Icon = item.icon;
                  return (
                    <div key={item.label} className="rounded-2xl border border-white/10 bg-white/5 p-4 transition hover:border-sky-400/25 hover:bg-sky-400/8">
                      <div className="mb-3 flex items-center gap-2 text-slate-400"><Icon className="h-4 w-4 text-sky-300" /> {item.label}</div>
                      <div className="text-2xl font-semibold text-slate-50">{item.value}</div>
                    </div>
                  );
                })}
              </div>
            </Card>
          </section>
          ) : null}

          <section className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
            <Card>
              <SectionTitle
                eyebrow="Advanced analytics"
                title="RUL, what-if simulation, and digital twin"
                description="Shows what could happen next, how long the pack may last, and whether the model should be retrained."
              />

              <div className="grid gap-3 md:grid-cols-3">
                {[
                  {
                    label: 'RUL forecast',
                    value: `${aiInsights.rulMinutes} min`,
                    helper: `${aiInsights.rulCycles} cycles projected`,
                    tone: 'text-sky-100',
                  },
                  {
                    label: 'Health index',
                    value: `${aiInsights.healthIndex}/100`,
                    helper: 'Single score for demo storytelling',
                    tone: aiInsights.healthIndex >= 70 ? 'text-emerald-100' : aiInsights.healthIndex >= 40 ? 'text-amber-100' : 'text-rose-100',
                  },
                  {
                    label: 'Twin alignment',
                    value: `${aiInsights.twinAlignment}%`,
                    helper: aiInsights.digitalTwinNarrative,
                    tone: aiInsights.twinAlignment >= 80 ? 'text-emerald-100' : aiInsights.twinAlignment >= 55 ? 'text-amber-100' : 'text-rose-100',
                  },
                ].map((item) => (
                  <div key={item.label} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <div className="text-[11px] uppercase tracking-[0.3em] text-slate-500">{item.label}</div>
                    <div className={`mt-3 text-2xl font-semibold ${item.tone}`}>{item.value}</div>
                    <div className="mt-2 text-sm leading-6 text-slate-400">{item.helper}</div>
                  </div>
                ))}
              </div>

              <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-300">
                  <TrendingUp className="h-4 w-4 text-sky-300" />
                  Drift and retrain signal
                </div>
                <div className="flex flex-wrap items-center gap-3 text-sm text-slate-300">
                  <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">Drift score {aiInsights.driftScore}/100</span>
                  <span className={`rounded-full border px-3 py-1.5 ${aiInsights.retrainRecommended ? 'border-amber-500/20 bg-amber-500/10 text-amber-100' : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-100'}`}>
                    {aiInsights.retrainRecommended ? 'Retrain recommended' : 'Retrain not required'}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-400">{aiInsights.priority3Summary}</p>
              </div>

              <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-300">
                  <Sparkles className="h-4 w-4 text-emerald-300" />
                  What-if simulation sandbox
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  {aiInsights.whatIfScenarios.map((scenario) => (
                    <div key={scenario.name} className="rounded-xl border border-white/10 bg-slate-950/40 p-3">
                      <div className="text-sm font-semibold text-slate-50">{scenario.name}</div>
                      <div className="mt-1 text-xs uppercase tracking-[0.24em] text-slate-500">Projected {scenario.prediction} risk</div>
                      <div className="mt-2 text-sm text-slate-300">Risk score {scenario.risk_score}/100</div>
                    </div>
                  ))}
                </div>
              </div>
            </Card>

            <Card>
              <SectionTitle
                eyebrow="Fleet intelligence"
                title="Synthetic fleet ranking"
                description={`A small fleet view (${aiInsights.fleetMode}) that shows how risk compares across multiple assets.`}
              />

              <div className="space-y-3">
                {aiInsights.fleetRankings.map((asset, index) => (
                  <div key={asset.name} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Rank {index + 1}</div>
                        <div className="mt-1 text-sm font-semibold text-slate-50">{asset.name}</div>
                      </div>
                      <div className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${asset.risk_score >= 70 ? 'border-rose-500/20 bg-rose-500/10 text-rose-100' : asset.risk_score >= 40 ? 'border-amber-500/20 bg-amber-500/10 text-amber-100' : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-100'}`}>
                        {asset.risk_score}/100
                      </div>
                    </div>
                    <div className="mt-2 text-sm leading-6 text-slate-400">
                      {asset.prediction} prediction with thermal {asset.components.thermal} / electrical {asset.components.electrical} / voltage {asset.components.voltage} pressure.
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </section>

          {activeTab === 'diagnostics' ? (
          <section className="grid gap-5 xl:grid-cols-[1fr_0.95fr]">
            <Card>
              <SectionTitle eyebrow="Narrative" title="What happened recently" description="Recent state changes are collapsed into a readable timeline." />
              <StoryTimeline story={story} />
            </Card>

            <div className="grid gap-5">
              <Card className="overflow-hidden">
                <SectionTitle eyebrow="Decision support" title="What should I do now?" />
                <div className="grid gap-3 md:grid-cols-2">
                  {[
                    {
                      title: 'Why is risk high?',
                      text: aiInsights.whyChanged,
                      icon: AlertTriangle,
                      tone: 'text-rose-100',
                    },
                    {
                      title: 'Adaptive thresholding',
                      text: aiInsights.safetyLayer,
                      icon: TrendingUp,
                      tone: 'text-sky-100',
                    },
                    {
                      title: 'Sensor fault diagnosis',
                      text: `${aiInsights.sensorFaultLabel}: ${aiInsights.sensorFaultReason}`,
                      icon: ShieldCheck,
                      tone: 'text-amber-100',
                    },
                    {
                      title: 'Auto-heal policy',
                      text: `${aiInsights.recoveryAction} - ${aiInsights.recoveryRationale} ${aiInsights.distributionDetail}`,
                      icon: RefreshCcw,
                      tone: 'text-emerald-100',
                    },
                  ].map((item) => {
                    const Icon = item.icon;
                    return (
                      <div key={item.title} className="rounded-2xl border border-white/10 bg-white/5 p-4 transition hover:border-white/20 hover:bg-white/8">
                        <div className={`mb-2 flex items-center gap-2 text-sm font-semibold ${item.tone}`}><Icon className="h-4 w-4" /> {item.title}</div>
                        <p className="text-sm leading-6 text-slate-400">{item.text}</p>
                      </div>
                    );
                  })}
                </div>
              </Card>

              <Card>
                <SectionTitle eyebrow="Model operations" title="Compare and recover" description="Keep candidate model management one click away without floating over the whole dashboard." />
                <Suspense fallback={<div className="text-sm text-slate-400">Loading model tools...</div>}>
                  <ModelCompare />
                </Suspense>
              </Card>
            </div>
          </section>
          ) : null}
        </main>

        <AnimatePresence>
          {toast ? (
            <motion.div
              key={toast.id}
              initial={{ opacity: 0, y: 20, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.96 }}
              transition={{ duration: 0.22 }}
              className="fixed bottom-6 right-6 z-50 max-w-sm rounded-2xl border border-white/10 bg-slate-950/90 px-4 py-3 shadow-2xl shadow-black/40 backdrop-blur-xl"
            >
              <div className="text-sm font-semibold text-slate-50">{toast.message}</div>
              <div className="mt-1 text-[11px] uppercase tracking-[0.28em] text-slate-500">{toast.tone}</div>
            </motion.div>
          ) : null}
        </AnimatePresence>

        {isLoading ? (
          <div className="fixed inset-x-0 top-0 h-1 overflow-hidden bg-white/5">
            <div className="h-full w-1/2 animate-pulse bg-gradient-to-r from-sky-400 via-cyan-300 to-emerald-300" />
          </div>
        ) : null}
      </motion.div>
    </div>
  );
}

export default App;
