/** @file Inicialização de event listeners — wiring entre DOM e módulos */
import { $, $$ } from './dom.js';

export function createEvents(dom, { search, abc, compare, theme, toast, state, utils, modal }) {
  const handlers = {
    theme() {
      dom.themeToggle?.addEventListener('click', () => theme.toggle());
    },

    mobileMenu() {
      dom.mobileMenuBtn?.addEventListener('click', () => {
        const isOpen = document.body.classList.toggle('menu-open');
        dom.mobileMenu?.classList.toggle('hidden', !isOpen);
        dom.mobileMenuBtn?.classList.toggle('active');
        dom.mobileMenuBtn?.setAttribute('aria-expanded', isOpen);

        const iconMenu = dom.mobileMenuBtn.querySelector('.icon-menu');
        const iconClose = dom.mobileMenuBtn.querySelector('.icon-close');
        if (iconMenu) iconMenu.style.display = isOpen ? 'none' : '';
        if (iconClose) iconClose.style.display = isOpen ? '' : 'none';
      });

      dom.mobileMenu?.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
          document.body.classList.remove('menu-open');
          dom.mobileMenu?.classList.add('hidden');
          dom.mobileMenuBtn?.classList.remove('active');
          dom.mobileMenuBtn?.setAttribute('aria-expanded', false);
          const iconMenu = dom.mobileMenuBtn?.querySelector('.icon-menu');
          const iconClose = dom.mobileMenuBtn?.querySelector('.icon-close');
          if (iconMenu) iconMenu.style.display = '';
          if (iconClose) iconClose.style.display = 'none';
        });
      });
    },

    heroExamples() {
      dom.exampleBtns.forEach(btn => {
        btn.addEventListener('click', () => {
          const query = btn.dataset.search;
          if (query && dom.searchInput) {
            dom.searchInput.value = query;
            btn.dataset.section && $(`#${btn.dataset.section}`)?.scrollIntoView({ behavior: 'smooth' });
            search.perform();
          }
        });
      });
    },

    search() {
      dom.searchBtn?.addEventListener('click', () => search.perform());
      dom.searchInput?.addEventListener('keypress', e => { if (e.key === 'Enter') search.perform(); });
      dom.sortSelect?.addEventListener('change', e => { state.search.sortBy = e.target.value; search.render(); });
      dom.btnGrid?.addEventListener('click', () => search.setView('grid'));
      dom.btnList?.addEventListener('click', () => search.setView('list'));
    },

    abc() {
      dom.abcBtn?.addEventListener('click', () => abc.perform());
      dom.btnAbcGrid?.addEventListener('click', () => abc.setView('grid'));
      dom.btnAbcList?.addEventListener('click', () => abc.setView('table'));
    },

    compare() {
      dom.compareBtn?.addEventListener('click', () => compare.perform());
      dom.stateChips?.addEventListener('click', e => {
        const chip = e.target.closest('.state-chip');
        chip && compare.toggleState(chip.dataset.uf);
      });
      dom.selectAllStates?.addEventListener('click', () => compare.selectAll());
      dom.clearAllStates?.addEventListener('click', () => compare.clearAll());
      dom.presetRegions?.addEventListener('click', () => compare.presetRegions());
    },

    copyCurl() {
      $$('[data-curl]').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          const curl = e.currentTarget.dataset.curl;
          if (curl && await utils.copyToClipboard(curl)) {
            toast.show('cURL copiado!', 'success');
          }
        });
      });
    },

    modal() {
      $('.modal-close', dom.detailModal)?.addEventListener('click', () => modal.close());
      dom.detailModal?.addEventListener('click', e => {
        if (e.target === dom.detailModal) modal.close();
      });
    },

    cardClicks() {
      // Event delegation para abrir o modal ao clicar em qualquer card (Search ou ABC)
      dom.resultsGrid?.addEventListener('click', (e) => {
        const card = e.target.closest('.card');
        if (card) {
          const { codigo, tipo } = card.dataset;
          modal.show(tipo, codigo);
        }
      });

      dom.abcGrid?.addEventListener('click', (e) => {
        const card = e.target.closest('.card');
        if (card) {
          const { codigo, tipo } = card.dataset;
          modal.show(tipo, codigo);
        }
      });
    },
  };

  return {
    init() {
      Object.values(handlers).forEach(h => h());
    },
  };
}