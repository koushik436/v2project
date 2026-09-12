import { useEffect, useRef, useState } from 'react';

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export default function AnimatedNumber({ value, format = (next) => next, duration = 320, className = '' }) {
  const [display, setDisplay] = useState(value);
  const previous = useRef(value);

  useEffect(() => {
    const start = previous.current;
    const end = value;
    const startedAt = performance.now();
    let frame = 0;

    const step = (now) => {
      const progress = clamp((now - startedAt) / duration, 0, 1);
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
  }, [value, duration]);

  return <span className={className}>{format(display)}</span>;
}
