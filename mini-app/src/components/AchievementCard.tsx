import { rarityStyles, rarityColors } from '../styles/rarity';

interface AchievementCardProps {
  name: string;
  description: string;
  icon: string;
  rarity: string;
  unlocked: boolean;
  unlockedAt?: string;
}

export default function AchievementCard({
  name,
  description,
  icon,
  rarity,
  unlocked,
  unlockedAt,
}: AchievementCardProps) {
  const borderStyle = rarityStyles[rarity] ?? rarityStyles.common;
  const rarityColor = rarityColors[rarity] ?? rarityColors.common;

  return (
    <div
      className={`relative rounded-xl border-2 bg-white/5 p-3 transition-all ${borderStyle} ${
        unlocked ? '' : 'opacity-50'
      }`}
    >
      <span
        className={`absolute top-2 right-2 text-[10px] font-semibold uppercase tracking-wide ${rarityColor}`}
      >
        {rarity}
      </span>

      <div className="flex flex-col items-center gap-2 text-center">
        <div className={`text-3xl ${unlocked ? '' : 'grayscale'}`}>
          {unlocked ? icon : '🔒'}
        </div>

        <div className="space-y-1">
          <p className={`text-sm font-semibold leading-tight ${unlocked ? '' : 'text-white/40'}`}>
            {name}
          </p>
          <p className="text-xs text-white/40 leading-tight">
            {unlocked ? description : '???'}
          </p>
        </div>

        {unlocked && unlockedAt && (
          <p className="text-[10px] text-white/25 mt-1">
            {new Date(unlockedAt).toLocaleDateString()}
          </p>
        )}
      </div>
    </div>
  );
}
