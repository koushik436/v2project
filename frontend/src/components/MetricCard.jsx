import { motion } from 'framer-motion';
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts';
import Card from './Card';
import AnimatedNumber from './AnimatedNumber';

export default function MetricCard({ icon, title, value, unit, delta, data = [], stroke = '#38bdf8', accent = 'from-sky-400 to-cyan-300', formatValue = (next) => next }) {
  const Icon = icon;
  const positive = delta >= 0;

  return (
    <Card className="relative overflow-hidden">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className={`flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br ${accent} text-slate-950 shadow-lg shadow-sky-500/10`}>
            <Icon className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-300">{title}</p>
            <div className="mt-1 flex items-baseline gap-2">
              <AnimatedNumber value={value} format={formatValue} className="text-2xl font-semibold text-slate-50 md:text-3xl" />
              {unit ? <span className="text-sm text-slate-400">{unit}</span> : null}
            </div>
          </div>
        </div>

        <div className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${positive ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-200' : 'border-rose-500/20 bg-rose-500/10 text-rose-200'}`}>
          {positive ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}%
        </div>
      </div>

      <div className="h-16">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 0, left: 0, bottom: 0 }}>
            <Tooltip
              cursor={{ stroke: 'rgba(148,163,184,0.18)' }}
              contentStyle={{
                borderRadius: 16,
                background: 'rgba(2,6,23,0.92)',
                border: '1px solid rgba(148,163,184,0.18)',
                color: '#e2e8f0',
                boxShadow: '0 20px 40px rgba(2,6,23,0.35)',
              }}
              labelStyle={{ color: '#cbd5e1', fontSize: 12 }}
              itemStyle={{ color: '#e2e8f0', fontSize: 12 }}
            />
            <Line type="monotone" dataKey="value" stroke={stroke} strokeWidth={2.5} dot={false} fillOpacity={1} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
