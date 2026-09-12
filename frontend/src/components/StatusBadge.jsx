import { CheckCircle2, AlertTriangle, Wifi, ShieldCheck } from 'lucide-react';

const badgeMap = {
  connected: { icon: Wifi, className: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-200', pulse: true },
  safe: { icon: ShieldCheck, className: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-100', pulse: false },
  warning: { icon: AlertTriangle, className: 'border-amber-500/25 bg-amber-500/10 text-amber-100', pulse: false },
  critical: { icon: AlertTriangle, className: 'border-rose-500/25 bg-rose-500/10 text-rose-100', pulse: false },
  neutral: { icon: CheckCircle2, className: 'border-slate-500/30 bg-slate-500/10 text-slate-100', pulse: false },
};

export default function StatusBadge({ label, variant = 'neutral', tone = '' }) {
  const config = badgeMap[variant] ?? badgeMap.neutral;
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold tracking-wide ${config.className} ${tone}`}>
      <span className={`inline-flex h-2.5 w-2.5 rounded-full ${config.pulse ? 'animate-pulse bg-emerald-400' : 'bg-current'}`} />
      <Icon className="h-3.5 w-3.5" />
      {label}
    </span>
  );
}
