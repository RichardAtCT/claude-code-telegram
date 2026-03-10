import { useEffect, useState } from 'react';
import { fetchProfile } from '../api/client';
import { useTelegram } from './useTelegram';

export function useProfile() {
  const { user } = useTelegram();
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user?.id) return;
    fetchProfile(user.id)
      .then(setProfile)
      .finally(() => setLoading(false));
  }, [user?.id]);

  return { profile, loading };
}
