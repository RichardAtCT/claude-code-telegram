const STAT_COLORS: Record<string, string> = {
  STR: '#ef4444',
  INT: '#3b82f6',
  DEX: '#22c55e',
  CON: '#f97316',
  WIS: '#a855f7',
};

const DEFAULT_COLOR = '#6366f1';
const MAX_STAT = 100;

interface StatBarProps {
  label: string;
  value: number;
}

export default function StatBar({ label, value }: StatBarProps) {
  const color = STAT_COLORS[label] ?? DEFAULT_COLOR;
  const pct = Math.min(100, Math.round((value / MAX_STAT) * 100));

  return (
    <div
      className="rounded-xl px-4 py-3 flex items-center gap-3"
      style={{ background: 'var(--tg-theme-secondary-bg-color, #1c1c1e)' }}
    >
      <span
        className="w-10 text-xs font-bold uppercase"
        style={{ color }}
      >
        {label}
      </span>
      <div
        className="flex-1 rounded-full overflow-hidden"
        style={{ height: '6px', background: 'var(--tg-theme-bg-color, #000)' }}
      >
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span
        className="w-8 text-right text-sm font-semibold"
        style={{ color: 'var(--tg-theme-text-color, #fff)' }}
      >
        {value}
      </span>
    </div>
  );
}
