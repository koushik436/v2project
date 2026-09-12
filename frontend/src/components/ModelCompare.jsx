import { useEffect, useState } from 'react';

export default function ModelCompare() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/model/compare');
      const j = await res.json();
      setData(j);
    } catch (e) {
      setData({ error: String(e) });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const promote = async (candidate_dir) => {
    await fetch('/api/model/promote', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ candidate_dir }) });
    load();
  };

  const rollback = async () => {
    await fetch('/api/model/rollback', { method: 'POST' });
    load();
  };

  if (!data) return null;

  return (
    <div className="pointer-events-auto">
      {!expanded ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="glass-panel rounded-full px-4 py-2 text-xs font-semibold text-slate-100 shadow-lg transition hover:scale-[1.02] hover:text-white"
        >
          Model compare
        </button>
      ) : (
        <div className="glass-panel w-80 rounded-3xl p-4 shadow-2xl">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-[0.28em] text-sky-300/80">Trust</div>
              <div className="text-sm font-semibold text-slate-50">Model Compare</div>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span>{loading ? 'Loading...' : ''}</span>
              <button type="button" onClick={() => setExpanded(false)} className="rounded-full border border-white/10 px-2 py-1 text-slate-200 hover:border-white/20 hover:text-white">
                Close
              </button>
            </div>
          </div>

          <div className="mt-3 text-xs leading-5 text-slate-300">
            <div className="text-slate-500">Stable</div>
            <div className="break-words text-slate-100">{data.pointer?.stable_model_path || '-'}</div>
          </div>
          <div className="mt-2 text-xs leading-5 text-slate-300">
            <div className="text-slate-500">Previous</div>
            <div className="break-words text-slate-100">{data.pointer?.previous_model_path || '-'}</div>
          </div>

          <div className="mt-3 max-h-64 space-y-2 overflow-auto pr-1">
            {(data.candidates || []).map((c, i) => (
              <div key={i} className="rounded-2xl border border-white/10 bg-white/5 p-3">
                <div className="break-words text-sm font-medium text-slate-50">{c.candidate_dir}</div>
                <div className="mt-1 break-words text-xs text-slate-400">metrics: {JSON.stringify(c.metrics)}</div>
                <div className="mt-2 flex gap-2">
                  <button className="btn btn-sm" onClick={() => promote(c.candidate_dir)}>Promote</button>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 flex justify-end">
            <button className="btn btn-danger btn-sm" onClick={rollback}>Rollback</button>
          </div>
        </div>
      )}
    </div>
  );
}
