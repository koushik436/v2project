export default function SectionTitle({ eyebrow, title, description, action }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div>
        {eyebrow ? <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.32em] text-sky-300/80">{eyebrow}</p> : null}
        <h2 className="text-lg font-semibold text-slate-50 md:text-xl">{title}</h2>
        {description ? <p className="mt-1 max-w-2xl text-sm text-slate-400">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}
