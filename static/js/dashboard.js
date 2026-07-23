function shortName(name) {
  if (!name) return '—';
  const parts = name.trim().split(/\s+/);
  return (parts[parts.length - 1] || name).toUpperCase().slice(0, 12);
}

function teamCode(team) {
  if (!team) return 'TBD';
  return (team.fifa_code || team.code || team.name || 'TBD').toString().slice(0, 3).toUpperCase();
}

function formatCountdown(ms) {
  if (ms <= 0) return '0D 0H';
  const d = Math.floor(ms / 86400000);
  const h = Math.floor((ms % 86400000) / 3600000);
  if (d > 0) return `${d}D ${h}H`;
  const m = Math.floor((ms % 3600000) / 60000);
  return `${h}H ${m}M`;
}

async function loadHeroAndFixtures() {
  const res = await fetch('/api/fixtures');
  const data = await res.json();
  if (!data.success) return;
  const fixtures = data.fixtures || [];

  const upcoming = fixtures
    .filter((f) => f.kickoff_utc)
    .filter((f) => f.status !== 'FINISHED' && f.status !== 'FT')
    .sort((a, b) => new Date(a.kickoff_utc) - new Date(b.kickoff_utc));

  const next = upcoming[0];
  if (next) {
    document.getElementById('hero-md-badge').textContent = `Matchday ${next.matchday ?? '—'}`;
    document.getElementById('hero-stage').textContent = next.stage || 'Group Stage';
    const home = next.home_team?.name || 'TBD';
    const away = next.away_team?.name || 'TBD';
    document.getElementById('hero-blurb').textContent =
      `Finalize your squad before ${home} vs ${away} kicks off.`;

    const tick = () => {
      const ms = new Date(next.kickoff_utc).getTime() - Date.now();
      document.getElementById('hero-deadline').innerHTML =
        `${formatCountdown(ms)} <span class="text-primary text-opacity-80">UNTIL DEADLINE</span>`;
    };
    tick();
    setInterval(tick, 60000);
  }

  const live = fixtures.filter((f) => f.status === 'LIVE' || f.status === 'IN_PLAY' || f.status === '1H' || f.status === '2H');
  const show = [...live, ...upcoming.filter((f) => !live.includes(f))].slice(0, 8);
  const ticker = document.getElementById('match-ticker');
  if (!show.length) {
    ticker.innerHTML = '<div class="min-w-[240px] bg-surface rounded-xl p-4 border border-outline-variant text-on-surface-variant font-body-sm">No fixtures yet</div>';
    return;
  }
  ticker.innerHTML = show.map((f) => {
    const isLive = live.includes(f);
    const timeLabel = f.kickoff_utc
      ? new Date(f.kickoff_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : '—';
    return `
      <div class="min-w-[240px] bg-surface rounded-xl p-4 border border-outline-variant flex flex-col gap-3 relative ${isLive ? 'glow-primary' : 'opacity-80'}">
        <div class="absolute top-0 right-0 ${isLive ? 'bg-danger text-white animate-pulse' : 'bg-surface-container-high text-text-secondary'} font-label-caps text-[10px] px-2 py-0.5 rounded-bl-lg rounded-tr-xl flex items-center gap-1">
          ${isLive ? '<div class="w-1.5 h-1.5 bg-white rounded-full"></div> LIVE' : timeLabel}
        </div>
        <div class="flex justify-between items-center mt-2">
          <span class="font-stat-lg text-stat-lg">${teamCode(f.home_team)}</span>
          <span class="font-stat-lg text-stat-lg font-bold ${isLive ? 'text-primary' : 'text-on-surface-variant'}">${f.home_score ?? '—'}</span>
        </div>
        <div class="flex justify-between items-center">
          <span class="font-stat-lg text-stat-lg text-on-surface-variant">${teamCode(f.away_team)}</span>
          <span class="font-stat-lg text-stat-lg font-bold text-on-surface-variant">${f.away_score ?? '—'}</span>
        </div>
      </div>`;
  }).join('');
}

function renderMiniPitch(players) {
  const pitch = document.getElementById('dash-pitch');
  const starters = (players || []).filter((p) => p.is_starting);
  if (!starters.length) {
    pitch.innerHTML = '<div class="flex-1 flex items-center justify-center text-on-surface-variant font-body-sm">No squad yet — <a class="text-primary ml-1 underline" href="/squad">build one</a></div>';
    document.getElementById('hero-edit-btn').href = '/squad';
    return;
  }
  document.getElementById('hero-edit-btn').href = '/my-team';
  const byPos = { FWD: [], MID: [], DEF: [], GK: [] };
  starters.forEach((ftp) => {
    const pos = ftp.player?.position;
    if (byPos[pos]) byPos[pos].push(ftp);
  });
  const chip = (ftp, border = 'border-on-surface') => {
    const p = ftp.player || {};
    const label = posLabel(p.position);
    return `
      <div class="flex flex-col items-center">
        <div class="w-8 h-8 rounded-full bg-surface-elevated border-2 ${border} flex items-center justify-center font-stat-md text-xs">${label}</div>
        <span class="bg-surface-elevated/80 px-1 mt-1 rounded text-[10px] font-stat-md">${shortName(p.name)}</span>
      </div>`;
  };
  const row = (items, extraClass = '') =>
    `<div class="flex justify-center gap-4 relative z-10 ${extraClass}">${items.map((ftp) => chip(ftp, ftp.player?.position === 'GK' ? 'border-tertiary' : 'border-on-surface')).join('')}</div>`;

  pitch.innerHTML = `
    <div class="absolute inset-0 pointer-events-none opacity-20 border-2 border-white/30 m-4 rounded-lg"></div>
    <div class="absolute inset-x-0 top-1/2 h-0.5 bg-white/30 pointer-events-none"></div>
    <div class="absolute left-1/2 top-1/2 w-16 h-16 border-2 border-white/30 rounded-full -translate-x-1/2 -translate-y-1/2 pointer-events-none"></div>
    ${row(byPos.FWD, 'pt-2')}
    ${row(byPos.MID, 'px-4 justify-between')}
    ${row(byPos.DEF)}
    ${row(byPos.GK, 'pb-2')}
  `;
}

function posLabel(pos) {
  return { GK: 'GK', DEF: 'DF', MID: 'MD', FWD: 'FW' }[pos] || pos || '?';
}

async function loadTeamKpis() {
  try {
    const [meRes, teamRes, liveRes, budgetRes] = await Promise.all([
      fetch('/api/auth/me'),
      fetch('/api/team'),
      fetch('/api/live/points'),
      fetch('/api/transfers/budget'),
    ]);
    const me = await meRes.json();
    const team = await teamRes.json();
    const live = await liveRes.json();
    const budget = await budgetRes.json();

    if (me.success) {
      document.getElementById('kpi-points').textContent = me.user.total_points ?? 0;
      if (me.user.overall_rank != null) {
        document.getElementById('kpi-rank').textContent = Number(me.user.overall_rank).toLocaleString();
      } else {
        document.getElementById('kpi-rank').textContent = '—';
      }
    } else {
      document.getElementById('kpi-points').textContent = '—';
      document.getElementById('dash-pitch').innerHTML =
        '<div class="flex-1 flex items-center justify-center text-on-surface-variant font-body-sm"><a class="text-primary underline" href="/login">Sign in</a>&nbsp;to view your squad</div>';
    }

    if (live.success) {
      document.getElementById('kpi-md').textContent = live.total_points ?? '—';
    }

    if (budget.success) {
      const rem = budget.budget_remaining;
      if (rem != null) document.getElementById('kpi-budget').textContent = `$${Number(rem).toFixed(1)}m`;
      const ft = budget.free_transfers_remaining ?? window.__freeTransfers;
      if (ft != null) {
        document.getElementById('transfer-reminder').innerHTML =
          `You have <strong class="text-primary font-bold">${ft} free transfer${ft === 1 ? '' : 's'}</strong> remaining. Unused transfers may carry over.`;
      }
    }

    if (team.success) {
      renderMiniPitch(team.team.players);
    }
  } catch (_) { /* guest */ }
}

async function loadLeagueWidget() {
  const box = document.getElementById('league-standings');
  try {
    const res = await fetch('/api/leagues');
    const data = await res.json();
    if (!data.success || !data.leagues?.length) {
      box.innerHTML = '<div class="p-6 text-center text-on-surface-variant font-body-sm">Join or create a mini league to see standings here.</div>';
      return;
    }
    const league = data.leagues[0];
    document.getElementById('league-widget-title').textContent = league.name;
    const stRes = await fetch(`/api/leagues/${league.id}/standings`);
    const st = await stRes.json();
    const rows = (st.standings || []).slice(0, 5);
    if (!rows.length) {
      box.innerHTML = '<div class="p-6 text-center text-on-surface-variant font-body-sm">No standings yet</div>';
      return;
    }
    box.innerHTML = rows.map((s, i) => {
      const initials = (s.username || '?').slice(0, 2).toUpperCase();
      const bg = i % 2 === 0 ? 'bg-surface-container-lowest' : 'bg-surface';
      return `
        <div class="flex items-center justify-between p-3 ${bg}">
          <div class="flex items-center gap-3">
            <span class="font-stat-md text-stat-md ${i === 0 ? 'text-primary' : 'text-on-surface'} w-4">${s.rank || i + 1}</span>
            <div class="w-8 h-8 rounded-full bg-surface-elevated border border-outline-variant flex items-center justify-center text-xs">${initials}</div>
            <div class="flex flex-col">
              <span class="font-body-sm text-body-sm font-bold text-on-surface">${s.username}</span>
            </div>
          </div>
          <span class="font-stat-md text-stat-md ${i === 0 ? 'text-primary' : ''}">${s.points ?? 0}</span>
        </div>`;
    }).join('');
  } catch (_) {
    box.innerHTML = '<div class="p-6 text-center text-on-surface-variant font-body-sm">Unable to load leagues</div>';
  }
}

loadHeroAndFixtures();
loadTeamKpis();
loadLeagueWidget();
