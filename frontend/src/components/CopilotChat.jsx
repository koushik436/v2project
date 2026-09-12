import { useState } from 'react';

const PROMPTS = [
  'What is the current battery risk and why?',
  'Summarize the latest telemetry changes.',
  'What action should the operator take now?',
  'Are any sensors out of range right now?',
  'What changed in the last minute?',
];

export default function CopilotChat() {
  const [question, setQuestion] = useState('');

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-sky-400/15 bg-gradient-to-r from-slate-950/60 via-slate-900/40 to-slate-950/60 p-5">
        <div className="text-xs uppercase tracking-[0.28em] text-sky-300/80">Live hardware copilot</div>
        <p className="mt-2 text-sm leading-6 text-slate-200">
          Ask about live battery telemetry, warnings, and recommended actions. Responses are grounded in the most recent device data.
        </p>
      </div>

      <div>
        <div className="text-xs uppercase tracking-[0.28em] text-slate-500">Example queries</div>
        <div className="mt-3 flex flex-wrap gap-2">
          {PROMPTS.map((prompt) => (
            <span
              key={prompt}
              className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-200"
            >
              {prompt}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
