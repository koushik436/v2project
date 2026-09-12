import { AlertTriangle, CheckCircle2, RefreshCcw, Wifi } from 'lucide-react';

const EVENT_ICONS = {
  recovery: RefreshCcw,
  state: AlertTriangle,
  connection: Wifi,
  info: CheckCircle2,
};

export default function StoryTimeline({ story = [] }) {
  return (
    <details className="glass-panel rounded-3xl p-4" open={false}>
      <summary className="cursor-pointer list-none text-sm font-semibold text-slate-50 outline-none transition hover:text-white">
        <span className="flex items-center justify-between gap-3">
          <span>Timeline</span>
          <span className="text-xs uppercase tracking-[0.24em] text-slate-500">Collapsed by default</span>
        </span>
      </summary>

      <div className="mt-4 space-y-2">
        {story.length === 0 && <div className="text-sm text-slate-500">No story events yet</div>}
        {story.map((s, i) => {
          const Icon = EVENT_ICONS[s.type] || CheckCircle2;
          return (
            <div key={i} className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/5 p-3">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-white/10 bg-slate-950/80 text-sky-300">
                <Icon className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm leading-6 text-slate-100">{s.text}</div>
                <div className="mt-1 text-[11px] uppercase tracking-[0.28em] text-slate-500">{s.timestamp}</div>
              </div>
            </div>
          );
        })}
      </div>
    </details>
  );
}
