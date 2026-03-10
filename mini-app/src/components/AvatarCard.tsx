interface AvatarCardProps {
  level: number;
  title: string;
}

export default function AvatarCard({ level, title }: AvatarCardProps) {
  return (
    <div
      className="rounded-2xl p-5 flex flex-col items-center gap-2"
      style={{ background: 'var(--tg-theme-secondary-bg-color, #1c1c1e)' }}
    >
      <div
        className="w-20 h-20 rounded-full flex items-center justify-center text-3xl font-bold"
        style={{
          background: 'linear-gradient(135deg, #6366f1, #a855f7)',
          color: '#fff',
          boxShadow: '0 4px 20px rgba(168, 85, 247, 0.4)',
        }}
      >
        {level}
      </div>
      <p
        className="text-xs uppercase tracking-widest font-semibold"
        style={{ color: 'var(--tg-theme-hint-color, #8e8e93)' }}
      >
        Level {level}
      </p>
      <p
        className="text-base italic"
        style={{ color: 'var(--tg-theme-text-color, #fff)' }}
      >
        {title}
      </p>
    </div>
  );
}
