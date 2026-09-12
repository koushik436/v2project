export default function ExecutiveScorecard({ aiInsights = {}, normalized = {} }) {
  const safety = Math.round((aiInsights.healthIndex || 0) * 0.6 + (aiInsights.ensembleScore || 0) * 0.4);
  const reliability = Math.round(100 - (aiInsights.driftScore || 0));
  const costSaved = Math.round(((aiInsights.healthIndex || 50) / 100) * 1200); // simple heuristic

  return (
    <div className="glass-panel mb-3 w-full rounded-3xl p-4">
      <div className="flex items-center justify-between gap-4">
        <div className="flex gap-6">
          <div>
            <div className="text-[11px] uppercase tracking-[0.26em] text-slate-500">Safety Score</div>
            <div className="mt-1 text-2xl font-semibold text-slate-50">{safety}</div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-[0.26em] text-slate-500">Reliability</div>
            <div className="mt-1 text-2xl font-semibold text-slate-50">{reliability}%</div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-[0.26em] text-slate-500">Est. Cost Saved</div>
            <div className="mt-1 text-2xl font-semibold text-slate-50">${costSaved}</div>
          </div>
        </div>
        <div className="text-sm text-slate-300">Model: {normalized.modelVersion || normalized.modelVersion === 0 ? normalized.modelVersion : normalized.modelVersion || '-'}</div>
      </div>
    </div>
  );
}
