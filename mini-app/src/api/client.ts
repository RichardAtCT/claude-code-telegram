const BASE = '/api/rpg';

export async function fetchProfile(userId: number) {
  const res = await fetch(`${BASE}/profile?user_id=${userId}`);
  return res.json();
}

export async function fetchAchievements(userId: number) {
  const res = await fetch(`${BASE}/achievements?user_id=${userId}`);
  return res.json();
}

export async function fetchTimeline(userId: number, limit = 50) {
  const res = await fetch(`${BASE}/timeline?user_id=${userId}&limit=${limit}`);
  return res.json();
}

export async function fetchStatsChart(userId: number) {
  const res = await fetch(`${BASE}/stats/chart?user_id=${userId}`);
  return res.json();
}
