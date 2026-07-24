(function () {
  const logEl = document.getElementById('admin-log');

  function log(payload) {
    if (!logEl) return;
    logEl.textContent = typeof payload === 'string'
      ? payload
      : JSON.stringify(payload, null, 2);
  }

  async function api(url, options = {}) {
    const res = await fetch(url, {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    const data = await res.json().catch(() => ({ success: false, message: `HTTP ${res.status}` }));
    if (res.status === 403) {
      log(data);
      alert(data.message || 'Admin access required');
      window.location.href = '/';
      throw new Error('forbidden');
    }
    if (res.status === 401) {
      window.location.href = '/login';
      throw new Error('unauthenticated');
    }
    return data;
  }

  async function loadOverview() {
    const data = await api('/api/admin/overview');
    if (!data.success) {
      log(data);
      return;
    }
    document.getElementById('kpi-users').textContent = data.users ?? '—';
    document.getElementById('kpi-players').textContent = data.players ?? '—';
    const photos = data.photos || {};
    document.getElementById('kpi-photos').textContent = photos.with_photo ?? '—';
    document.getElementById('kpi-md').textContent = data.current_matchday ?? '—';
    const mdInput = document.getElementById('admin-matchday');
    if (mdInput && !mdInput.value && data.current_matchday) {
      mdInput.value = data.current_matchday;
    }
    const q = data.api_football_quota || {};
    document.getElementById('admin-quota').textContent =
      `API-Football: ${q.used ?? '—'}/${q.limit ?? '—'} used · ${q.remaining ?? '—'} left`;
    log({ overview: 'ok', photos, quota: q });
  }

  const actions = {
    async seed() {
      return api('/api/admin/seed-db', { method: 'POST' });
    },
    async 'sync-players'() {
      return api('/api/admin/sync/players', { method: 'POST' });
    },
    async 'sync-fixtures'() {
      return api('/api/admin/sync/fixtures', { method: 'POST' });
    },
    async 'sync-livescores'() {
      return api('/api/admin/sync/livescores', { method: 'POST' });
    },
    async recalculate() {
      const md = Number(document.getElementById('admin-matchday').value);
      if (!md) throw new Error('Enter a matchday number');
      return api(`/api/admin/recalculate/${md}`, { method: 'POST' });
    },
    async 'sync-stats'() {
      const id = Number(document.getElementById('admin-fixture-id').value);
      if (!id) throw new Error('Enter a fixture ID');
      return api(`/api/admin/sync/stats/${id}`, { method: 'POST' });
    },
    async 'photos-sync'() {
      return api('/api/photos/sync', { method: 'POST', body: '{}' });
    },
    async 'photos-apply-manual'() {
      return api('/api/admin/players/photos/apply-manual?only_missing=1', { method: 'POST' });
    },
    async 'photos-missing'() {
      const data = await api('/api/admin/players/missing-photos?limit=100');
      const box = document.getElementById('missing-photos');
      if (!data.success) return data;
      const list = data.players || [];
      box.classList.remove('hidden');
      if (!list.length) {
        box.innerHTML = '<p class="text-on-surface-variant">No missing photos in this sample.</p>';
      } else {
        box.innerHTML = list.map((p) => {
          const nation = p.country || '';
          return `<div class="flex justify-between gap-3 py-1 border-b border-outline-variant/40"><span>${p.id} · ${p.name}</span><span class="text-on-surface-variant">${nation} · ${p.position || ''}</span></div>`;
        }).join('');
      }
      return data;
    },
    async 'photo-set'() {
      const id = Number(document.getElementById('photo-player-id').value);
      const photo_url = document.getElementById('photo-url').value.trim();
      if (!id || !photo_url) throw new Error('Player ID and photo URL required');
      return api(`/api/admin/players/${id}/photo`, {
        method: 'PUT',
        body: JSON.stringify({ photo_url }),
      });
    },
  };

  document.querySelectorAll('[data-admin-action]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const key = btn.getAttribute('data-admin-action');
      const fn = actions[key];
      if (!fn) return;
      btn.disabled = true;
      log(`Running ${key}…`);
      try {
        const result = await fn();
        log(result);
        if (key !== 'photos-missing') await loadOverview();
      } catch (err) {
        if (err.message !== 'forbidden' && err.message !== 'unauthenticated') {
          log(String(err.message || err));
        }
      } finally {
        btn.disabled = false;
      }
    });
  });

  loadOverview().catch((err) => log(String(err.message || err)));
})();
