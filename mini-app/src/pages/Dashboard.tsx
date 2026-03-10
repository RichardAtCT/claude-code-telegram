import { useProfile } from '../hooks/useProfile';
import AvatarCard from '../components/AvatarCard';
import XpProgressBar from '../components/XpProgressBar';
import StatBar from '../components/StatBar';
import StreakBadge from '../components/StreakBadge';

const STATS = ['str', 'int', 'dex', 'con', 'wis'] as const;
const STAT_LABELS: Record<string, string> = {
  str: 'STR', int: 'INT', dex: 'DEX', con: 'CON', wis: 'WIS',
};

export default function Dashboard() {
  const { profile, loading } = useProfile();
  if (loading) return <div className="p-6 text-center opacity-50">Loading...</div>;
  if (!profile) return <div className="p-6 text-center">No profile yet</div>;

  return (
    <div className="p-4 space-y-4 max-w-md mx-auto">
      <AvatarCard level={profile.level} title={profile.title} />
      <XpProgressBar
        current={profile.total_xp - profile.xp_for_current_level}
        max={profile.xp_for_next_level - profile.xp_for_current_level}
        totalXp={profile.total_xp}
      />
      <div className="space-y-2">
        {STATS.map((s) => (
          <StatBar key={s} label={STAT_LABELS[s]} value={profile[`${s}_points`]} />
        ))}
      </div>
      <StreakBadge current={profile.current_streak} longest={profile.longest_streak} />
    </div>
  );
}
