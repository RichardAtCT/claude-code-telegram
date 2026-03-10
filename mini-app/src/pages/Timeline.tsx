import { useEffect, useState } from 'react';
import { fetchTimeline } from '../api/client';
import { useTelegram } from '../hooks/useTelegram';

interface TimelineEntry {
  user_id: number;
  xp_amount: number;
  stat_type: string | null;
  source: string;
  details: string | null;
  created_at: string;
}

const SOURCE_LABELS: Record<string, string> = {
  commit_feat: 'Feature commit',
  commit_fix: 'Bug fix',
  commit_refactor: 'Refactor',
  commit: 'Commit',
  test_run: 'Test run',
  tool_read: 'File read',
  tool_write: 'File edit',
  qa_pass: 'QA passed',
};

const SOURCE_ICONS: Record<string, string> = {
  commit_feat: '✨',
  commit_fix: '🐛',
  commit_refactor: '♻️',
  commit: '📝',
  test_run: '🧪',
  tool_read: '👁',
  tool_write: '✏️',
  qa_pass: '✅',
};

const STAT_COLORS: Record<string, string> = {
  str: 'bg-orange-500/20 text-orange-400',
  int: 'bg-blue-500/20 text-blue-400',
  dex: 'bg-green-500/20 text-green-400',
  con: 'bg-yellow-500/20 text-yellow-400',
  wis: 'bg-purple-500/20 text-purple-400',
};

function formatDateKey(dateStr: string): string {
  return dateStr.slice(0, 10); // YYYY-MM-DD
}

function formatDateHeader(dateKey: string): string {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);

  const todayKey = today.toISOString().slice(0, 10);
  const yesterdayKey = yesterday.toISOString().slice(0, 10);

  if (dateKey === todayKey) return 'Today';
  if (dateKey === yesterdayKey) return 'Yesterday';

  const date = new Date(dateKey + 'T00:00:00');
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatTime(createdAt: string): string {
  const date = new Date(createdAt);
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

interface DayGroup {
  dateKey: string;
  totalXp: number;
  entries: TimelineEntry[];
}

function groupByDay(entries: TimelineEntry[]): DayGroup[] {
  const map = new Map<string, TimelineEntry[]>();

  for (const entry of entries) {
    const key = formatDateKey(entry.created_at);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(entry);
  }

  return Array.from(map.entries())
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([dateKey, dayEntries]) => ({
      dateKey,
      totalXp: dayEntries.reduce((sum, e) => sum + e.xp_amount, 0),
      entries: dayEntries,
    }));
}

export default function Timeline() {
  const { user } = useTelegram();
  const [groups, setGroups] = useState<DayGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.id) return;

    setLoading(true);
    fetchTimeline(user.id)
      .then((data) => {
        const entries: TimelineEntry[] = data?.entries ?? [];
        setGroups(groupByDay(entries));
      })
      .catch(() => setError('Failed to load timeline'))
      .finally(() => setLoading(false));
  }, [user?.id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 text-white/40 text-sm">
        Loading timeline…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center p-12 text-red-400 text-sm">
        {error}
      </div>
    );
  }

  if (groups.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 gap-2">
        <span className="text-3xl">📭</span>
        <p className="text-white/40 text-sm">No XP events yet. Start coding!</p>
      </div>
    );
  }

  return (
    <div className="p-4 flex flex-col gap-6">
      {groups.map((group) => (
        <div key={group.dateKey}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-white/50">
              {formatDateHeader(group.dateKey)}
            </span>
            <span className="text-xs font-bold text-emerald-400">+{group.totalXp} XP</span>
          </div>

          <div className="flex flex-col gap-1 rounded-xl overflow-hidden bg-white/5 divide-y divide-white/5">
            {group.entries.map((entry, idx) => {
              const icon = SOURCE_ICONS[entry.source] ?? '⚡';
              const label = SOURCE_LABELS[entry.source] ?? entry.source;
              const statColor = entry.stat_type ? STAT_COLORS[entry.stat_type] : null;

              return (
                <div
                  key={idx}
                  className="flex items-center gap-3 px-3 py-2"
                >
                  <span className="text-base w-5 text-center shrink-0">{icon}</span>

                  <div className="flex-1 min-w-0">
                    <span className="text-sm text-white/80 truncate block">{label}</span>
                  </div>

                  {statColor && (
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase shrink-0 ${statColor}`}>
                      {entry.stat_type}
                    </span>
                  )}

                  <span className="text-xs font-semibold text-emerald-400 shrink-0">
                    +{entry.xp_amount} XP
                  </span>

                  <span className="text-[11px] text-white/30 shrink-0 w-10 text-right">
                    {formatTime(entry.created_at)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
