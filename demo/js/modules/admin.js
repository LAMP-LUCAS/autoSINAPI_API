/** @file Módulo de Administração — População do Banco + Task Status */
export function createAdmin(config, state, dom, utils, api, toast) {
  function initVisibility() {
    const showAdmin = window.location.search.includes('admin=true');
    if (dom.adminSection) dom.adminSection.classList.toggle('hidden', !showAdmin);
    if (showAdmin) populateUfDropdown();
  }

  function populateUfDropdown() {
    if (!dom.adminUf || !state.filters.ufs.length) return;
    dom.adminUf.innerHTML = '<option value="">Todas as UFs</option>' +
      state.filters.ufs.map(uf => `<option value="${uf}">${uf}</option>`).join('');
  }

  async function triggerPopulation(e) {
    e.preventDefault();
    const year = parseInt(dom.adminYear?.value, 10);
    const month = parseInt(dom.adminMonth?.value, 10);
    const uf = dom.adminUf?.value || 'SP';

    if (!year || !month || month < 1 || month > 12) {
      toast.show('Informe ano e mês válidos.', 'warning');
      return;
    }

    if (dom.adminLoader) dom.adminLoader.classList.remove('hidden');
    if (dom.adminTaskStatus) dom.adminTaskStatus.classList.add('hidden');
    if (dom.adminTaskResult) dom.adminTaskResult.textContent = '';

    try {
      const result = await api.request(`${config.API_BASE}/../admin/populate-database`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ year, month, state: uf }),
      });

      state.admin.taskId = result.task_id;
      toast.show(`Carga iniciada! Task: ${result.task_id.substring(0, 8)}...`, 'success');
      if (dom.adminTaskStatus) dom.adminTaskStatus.classList.remove('hidden');
      if (dom.adminPollStatus) {
        dom.adminPollStatus.textContent = 'Task iniciada, aguardando processamento...';
      }
      startPolling();
    } catch (error) {
      toast.show(`Erro: ${error.message}`, 'error');
    } finally {
      if (dom.adminLoader) dom.adminLoader.classList.add('hidden');
    }
  }

  function startPolling() {
    stopPolling();
    state.admin.pollingInterval = setInterval(pollTaskStatus, 3000);
    pollTaskStatus();
  }

  function stopPolling() {
    if (state.admin.pollingInterval) {
      clearInterval(state.admin.pollingInterval);
      state.admin.pollingInterval = null;
    }
  }

  async function pollTaskStatus() {
    if (!state.admin.taskId) return;
    try {
      const status = await api.request(`${config.API_BASE}/../admin/tasks/${state.admin.taskId}`);
      if (dom.adminPollStatus) {
        dom.adminPollStatus.textContent = `Status: ${status.status}${status.ready ? ' (Concluído)' : ' (Processando...)'}`;
      }
      if (status.ready && dom.adminTaskResult) {
        dom.adminTaskResult.textContent = status.result || 'Tarefa concluída sem resultado adicional.';
        stopPolling();
      }
    } catch {
      if (dom.adminPollStatus) dom.adminPollStatus.textContent = 'Erro ao verificar status.';
      stopPolling();
    }
  }

  return { initVisibility, triggerPopulation, populateUfDropdown, stopPolling };
}