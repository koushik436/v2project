import { motion } from 'framer-motion';

export default function RiskGauge({ score, label, tone = 'safe', subtitle }) {
  const capped = Math.max(0, Math.min(100, score));
  const colorMap = {
    safe: ['#34d399', '#10b981'],
    moderate: ['#fbbf24', '#f59e0b'],
    danger: ['#fb7185', '#f43f5e'],
  };
  const [start, end] = colorMap[tone] ?? colorMap.safe;

  return (
    <div className="relative flex flex-col items-center justify-center gap-4 py-2">
      <div className="relative flex h-64 w-64 items-center justify-center md:h-72 md:w-72">
        <motion.div
          className="absolute inset-0 rounded-full ring-gradient"
          style={{
            background: `conic-gradient(from 180deg, ${end} 0%, ${start} ${capped}%, rgba(148,163,184,0.12) ${capped}%, rgba(148,163,184,0.12) 100%)`,
          }}
          initial={{ scale: 0.92, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.5 }}
        />
        <div className="absolute inset-[14px] rounded-full border border-white/10 bg-slate-950/85 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] backdrop-blur-xl" />
        <div className="relative z-10 text-center">
          <motion.div
            key={capped}
            initial={{ scale: 0.96, opacity: 0.4 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.35 }}
          >
            <div className="text-6xl font-extrabold tracking-tight text-gradient md:text-7xl">{capped}</div>
          </motion.div>
          <div className="mt-2 text-xs font-semibold uppercase tracking-[0.34em] text-slate-400">Risk Score / 100</div>
        </div>
      </div>

      <div className="text-center">
        <div className="text-sm font-medium text-slate-300">{label}</div>
        {subtitle ? <div className="mt-1 text-sm text-slate-400">{subtitle}</div> : null}
      </div>
    </div>
  );
}
