import WebApp from '@twa-dev/sdk';

export function useTelegram() {
  const user = WebApp.initDataUnsafe?.user;
  const colorScheme = WebApp.colorScheme;
  const themeParams = WebApp.themeParams;

  return { user, colorScheme, themeParams, WebApp };
}
