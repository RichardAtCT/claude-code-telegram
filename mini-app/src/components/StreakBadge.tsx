interface StreakBadgeProps {
  current: number;
  longest: number;
}

export default function StreakBadge({ current, longest }: StreakBadgeProps) {
  return (
    <div
      className="rounded-2xl p-4 flex items-center justify-between"
      style={{ background: 'var(--tg-theme-secondary-bg-color, #1c1c1e)' }}
    >
      <div className="flex items-center gap-3">
        <span className="text-3xl">🔥</span>
        <div>
          <div
            className="text-2xl font-bold leading-tight"
            style={{ color: '#f97316' }}
          >
            {current}
          </div>
          <div
            className="text-xs uppercase tracking-wide"
            style={{ color: 'var(--tg-theme-hint-color, #8e8e93)' }}
          >
            day streak
          </div>
        </div>
      </div>
      <div className="text-right">
        <div
          className="text-sm font-semibold"
          style={{ color: 'var(--tg-theme-hint-color, #8e8e93)' }}
        >
          best: {longest}
        </div>
      </div>
    </div>
  );
}
