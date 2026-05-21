/** @file Notificações Toast */
export function createToast(dom, { TOAST_DURATION }) {
  return {
    show(message, type = 'info') {
      const el = dom.toast;
      if (!el) return;
      el.textContent = message;
      el.className = `toast toast-${type} show`;
      setTimeout(() => el.classList.remove('show'), TOAST_DURATION);
    },
  };
}