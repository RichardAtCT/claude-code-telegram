import { useEffect, useState } from 'react';
import { fetchAchievements } from '../api/client';
import { useTelegram } from '../hooks/useTelegram';
import AchievementCard from '../components/AchievementCard';

interface AchievementDef {
  id: string;
  name: string;
  description: string;
  icon: string;
  rarity: string;
}

interface AchievementUnlocked {
  achievement_id: string;
  unlocked_at: string;
}

type Filter = 'all' | 'unlocked' | 'locked';

const RARITY_ORDER: Record<string, number> = {
  legendary: 0,
  epic: 1,
  rare: 2,
  common: 3,
};

export default function Achievements() {
  const { user } = useTelegram();
  const [definitions, setDefinitions] = useState<AchievementDef[]>([]);
  const [unlockedMap, setUnlockedMap] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>('all');

  useEffect(() => {
    if (!user?.id) return;
    fetchAchievements(user.id)
      .then((data) => {
        setDefinitions(data.definitions ?? []);
        const map: Record<string, string> = {};
        for (const u of (data.unlocked ?? []) as AchievementUnlocked[]) {
          map[u.achievement_id] = u.unlocked_at;
        }
        setUnlockedMap(map);
      })
      .finally(() => setLoading(false));
  }, [user?.id]);

  const sorted = [...definitions].sort((a, b) => {
    const aUnlocked = a.id in unlockedMap;
    const bUnlocked = b.id in unlockedMap;
    if (aUnlocked !== bUnlocked) return aUnlocked ? -1 : 1;
    return (RARITY_ORDER[a.rarity] ?? 99) - (RARITY_ORDER[b.rarity] ?? 99);
  });

  const filtered = sorted.filter((def) => {
    if (filter === 'unlocked') return def.id in unlockedMap;
    if (filter === 'locked') return !(def.id in unlockedMap);
    return true;
  });

  const unlockedCount = definitions.filter((d) => d.id in unlockedMap).length;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40">
        <p className="text-white/40 text-sm">Loading achievements...</p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">
          Achievements{' '}
          <span className="text-white/40 font-normal text-sm">
            ({unlockedCount}/{definitions.length})
          </span>
        </h1>
      </div>

      <div className="flex gap-2">
        {(['all', 'unlocked', 'locked'] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded-full text-xs capitalize transition-all ${
              filter === f
                ? 'bg-white/20 font-semibold'
                : 'bg-white/5 text-white/50 hover:bg-white/10'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <p className="text-center text-white/30 text-sm py-8">No achievements here yet.</p>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {filtered.map((def) => (
            <AchievementCard
              key={def.id}
              name={def.name}
              description={def.description}
              icon={def.icon}
              rarity={def.rarity}
              unlocked={def.id in unlockedMap}
              unlockedAt={unlockedMap[def.id]}
            />
          ))}
        </div>
      )}
    </div>
  );
}
