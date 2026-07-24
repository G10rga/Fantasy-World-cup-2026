(function () {
  const path = window.location.pathname;

  function setActiveNav() {
    document.querySelectorAll('.nav-item').forEach((a) => {
      const href = a.getAttribute('data-nav') || a.getAttribute('href');
      let active = href === path || (href !== '/' && path.startsWith(href.split('#')[0]));
      if (href === '/' && (path === '/' || path === '/dashboard')) active = true;
      a.classList.toggle('nav-link-active', active);
      a.classList.toggle('nav-link-idle', !active);
      const icon = a.querySelector('.material-symbols-outlined');
      if (icon) icon.classList.toggle('filled', active);
    });
    document.querySelectorAll('.mobile-nav').forEach((a) => {
      const href = a.getAttribute('data-nav') || a.getAttribute('href');
      let active = href === path || (href !== '/' && path.startsWith(href));
      if (href === '/' && (path === '/' || path === '/dashboard')) active = true;
      a.classList.toggle('mobile-nav-active', active);
      a.classList.toggle('text-on-surface-variant', !active);
      const icon = a.querySelector('.material-symbols-outlined');
      if (icon) icon.classList.toggle('filled', active);
    });
  }

  async function checkAuth() {
    try {
      const res = await fetch('/api/auth/me', { credentials: 'same-origin' });
      const data = await res.json().catch(() => ({ success: false }));
      if (data.success) {
        const u = data.user;
        const label = `${u.username} · ${u.total_points} pts`;
        const userInfo = document.getElementById('user-info');
        if (userInfo) {
          userInfo.textContent = label;
          userInfo.classList.remove('hidden');
        }
        const sidebarUser = document.getElementById('sidebar-user');
        if (sidebarUser) {
          sidebarUser.textContent = label;
          sidebarUser.classList.remove('hidden');
        }
        document.getElementById('logout-btn')?.classList.remove('hidden');
        document.getElementById('guest-links')?.classList.add('hidden');
        if (u.overall_rank != null) {
          const rankEl = document.getElementById('sidebar-rank');
          if (rankEl) rankEl.textContent = `Global Rank: #${Number(u.overall_rank).toLocaleString()}`;
        }
        if (u.is_admin) {
          const navAdmin = document.getElementById('nav-admin');
          if (navAdmin) {
            navAdmin.classList.remove('hidden');
            navAdmin.classList.add('flex');
          }
          const moreAdmin = document.getElementById('more-admin');
          if (moreAdmin) {
            moreAdmin.classList.remove('hidden');
            moreAdmin.classList.add('flex');
          }
        }
      }
    } catch (_) { /* guest */ }
  }

  async function loadBudgetHeader() {
    try {
      const res = await fetch('/api/transfers/budget', { credentials: 'same-origin' });
      const data = await res.json().catch(() => ({ success: false }));
      if (!data.success) return;
      const limit = data.budget_limit ?? 100;
      const remaining = data.budget_remaining;
      document.getElementById('hdr-budget').textContent = Number(limit).toFixed(1);
      if (remaining != null) {
        document.getElementById('hdr-remaining').textContent = Number(remaining).toFixed(1);
      }
      if (data.free_transfers_remaining != null) {
        window.__freeTransfers = data.free_transfers_remaining;
      }
    } catch (_) { /* ignore */ }
  }

  async function loadDeadline() {
    try {
      const res = await fetch('/api/fixtures');
      const data = await res.json();
      if (!data.success || !data.fixtures?.length) return;
      const upcoming = data.fixtures
        .filter((f) => f.status === 'SCHEDULED' || f.status === 'TIMED' || (!f.status || f.status === 'NS'))
        .filter((f) => f.kickoff_utc)
        .sort((a, b) => new Date(a.kickoff_utc) - new Date(b.kickoff_utc));
      const next = upcoming[0] || data.fixtures.find((f) => f.kickoff_utc);
      if (!next?.kickoff_utc) return;
      const deadlineEl = document.getElementById('hdr-deadline');
      const textEl = document.getElementById('hdr-deadline-text');
      if (!deadlineEl || !textEl) return;
      deadlineEl.classList.remove('hidden');
      window.__nextKickoff = new Date(next.kickoff_utc).getTime();
      window.__nextFixture = next;
      tickDeadline();
      setInterval(tickDeadline, 1000);
    } catch (_) { /* ignore */ }
  }

  function tickDeadline() {
    const textEl = document.getElementById('hdr-deadline-text');
    if (!textEl || !window.__nextKickoff) return;
    const diff = window.__nextKickoff - Date.now();
    if (diff <= 0) {
      textEl.textContent = 'DEADLINE PASSED';
      return;
    }
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    if (h >= 48) {
      const d = Math.floor(h / 24);
      textEl.textContent = `DEADLINE: ${d}D ${h % 24}H`;
    } else {
      textEl.textContent = `DEADLINE: ${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
  }

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login';
  }

  document.getElementById('logout-btn')?.addEventListener('click', logout);
  document.getElementById('more-logout')?.addEventListener('click', logout);

  const moreBtn = document.getElementById('more-menu-btn');
  const moreSheet = document.getElementById('more-sheet');
  moreBtn?.addEventListener('click', () => moreSheet?.classList.remove('hidden'));
  document.getElementById('more-sheet-backdrop')?.addEventListener('click', () => moreSheet?.classList.add('hidden'));

  fetch('/api/meta').then((r) => r.json()).then((d) => {
    if (d.data_delayed) {
      const banner = document.getElementById('data-delayed-banner');
      if (banner) banner.style.display = 'block';
    }
  }).catch(() => {});

  setActiveNav();
  checkAuth();
  loadBudgetHeader();
  loadDeadline();
})();
