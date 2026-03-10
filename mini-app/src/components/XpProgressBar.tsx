interface XpProgressBarProps {
  current: number;
  max: number;
  totalXp: number;
}

export default function XpProgressBar({ current, max, totalXp }: XpProgressBarProps) {
  const pct = max > 0 ? Math.min(100, Math.round((current / max) * 100)) : 0;

  return (
    <div
      className="rounded-2xl p-4 space-y-2"
      style={{ background: 'var(--tg-theme-secondary-bg-color, #1c1c1e)' }}
    >
      <div className="flex justify-between text-xs font-medium" style={{ color: 'var(--tg-theme-hint-color, #8e8e93)' }}>
        <span>XP to next level</span>
        <span>Total: {totalXp.toLocaleString()}</span>
      </div>
      <div
        className="w-full rounded-full overflow-hidden"
        style={{ height: '10px', background: 'var(--tg-theme-bg-color, #000)' }}
      >
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${pct}%`,
            background: 'linear-gradient(90deg, #6366f1, #a855f7)',
          }}
        />
      </div>
      <div
        className="text-right text-xs"
        style={{ color: 'var(--tg-theme-hint-color, #8e8e93)' }}
      >
        {current.toLocaleString()} / {max.toLocaleString()} XP ({pct}%)
      </div>
    </div>
  );
}
