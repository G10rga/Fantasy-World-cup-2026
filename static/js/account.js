(function () {
  async function loadProfile() {
    const res = await fetch('/api/auth/me', { credentials: 'same-origin' });
    const data = await res.json().catch(() => ({ success: false }));
    if (!data.success) {
      window.location.href = '/login';
      return;
    }
    const u = data.user;
    document.getElementById('acc-username').textContent = u.username || '—';
    document.getElementById('acc-email').textContent = u.email || '—';
    document.getElementById('acc-points').textContent = u.total_points ?? '—';
    document.getElementById('acc-role').textContent = u.is_admin ? 'Admin' : 'Manager';
  }

  document.getElementById('delete-account-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('delete-error');
    errEl.classList.add('hidden');
    errEl.textContent = '';

    const password = document.getElementById('delete-password').value;
    const confirm = document.getElementById('delete-confirm').value.trim();
    if (confirm.toUpperCase() !== 'DELETE') {
      errEl.textContent = 'Type DELETE exactly to confirm.';
      errEl.classList.remove('hidden');
      return;
    }
    if (!window.confirm('Delete your account permanently? This cannot be undone.')) {
      return;
    }

    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    try {
      const res = await fetch('/api/auth/account', {
        method: 'DELETE',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password, confirm: 'DELETE' }),
      });
      const data = await res.json().catch(() => ({ success: false, message: 'Request failed' }));
      if (!data.success) {
        errEl.textContent = data.message || 'Could not delete account';
        errEl.classList.remove('hidden');
        btn.disabled = false;
        return;
      }
      window.location.href = '/';
    } catch (_) {
      errEl.textContent = 'Network error — try again.';
      errEl.classList.remove('hidden');
      btn.disabled = false;
    }
  });

  loadProfile();
})();
