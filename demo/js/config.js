/** @file Configuração central e constantes */
export const CONFIG = Object.freeze({
  API_BASE: (() => {
    const origin = window.location.origin;
    return (origin === 'null' || origin.startsWith('file:'))
      ? 'https://autosinapi.lamp.local/api/v1/public'
      : '/api/v1/public';
  })(),
  TOAST_DURATION: 3000,
  DEBOUNCE_MS: 300,
  FALLBACK_UF: 'SP',
  FALLBACK_REGIME: 'NAO_DESONERADO',
});