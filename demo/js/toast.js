/** @file Notificações Toast */
export function createToast(dom, { TOAST_DURATION }) {
  return {
    show(message, type = 'info') {
      const el = dom.toast;
      if (!el) return;
      el.textContent = message;
      el.className = `toast toast-${type} show`;
      clearTimeout(el._timeout);
      el._timeout = setTimeout(() => this.dismiss(), TOAST_DURATION);

      // Dismiss on click/tap
      el.onclick = () => this.dismiss();
    },
    dismiss() {
      const el = dom.toast;
      if (!el) return;
      el.classList.remove('show');
      el.onclick = null;
      clearTimeout(el._timeout);
    },
  };
}