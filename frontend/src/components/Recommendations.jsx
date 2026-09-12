export default function Recommendations({ items = [] }) {
  return (
    <div className="glass-panel rounded-3xl p-4">
      <div className="mb-3 text-sm font-semibold text-slate-50">Action Recommendations</div>
      <div className="grid grid-cols-1 gap-2">
        {items.map((it, i) => (
          <div key={i} className="rounded-2xl border border-white/10 bg-white/5 p-3">
            <div className="font-semibold text-slate-50">{it.label}</div>
            <div className="text-xs text-slate-400">{it.rationale}</div>
            <div className="mt-2 text-sm">
              <button className="btn btn-sm mr-2">Do Now</button>
              <button className="btn btn-ghost btn-sm">Details</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
