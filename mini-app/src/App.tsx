import { useState } from 'react';
import Dashboard from './pages/Dashboard';
import Achievements from './pages/Achievements';
import Timeline from './pages/Timeline';

type Page = 'dashboard' | 'achievements' | 'timeline';

export default function App() {
  const [page, setPage] = useState<Page>('dashboard');

  return (
    <div className="min-h-screen bg-[var(--tg-theme-bg-color,#1a1a2e)] text-[var(--tg-theme-text-color,#e0e0e0)]">
      <nav className="flex gap-2 p-3 border-b border-white/10">
        {(['dashboard', 'achievements', 'timeline'] as Page[]).map((p) => (
          <button
            key={p}
            onClick={() => setPage(p)}
            className={`px-3 py-1 rounded text-sm capitalize ${
              page === p ? 'bg-white/20 font-bold' : 'opacity-60'
            }`}
          >
            {p}
          </button>
        ))}
      </nav>
      {page === 'dashboard' && <Dashboard />}
      {page === 'achievements' && <Achievements />}
      {page === 'timeline' && <Timeline />}
    </div>
  );
}
