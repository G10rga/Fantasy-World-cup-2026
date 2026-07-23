let pollInterval = null;
let currentTeam = null;
let currentFormation = '4-3-3';
let pointsMap = {};

function shortName(name) {
  if (!name) return '—';
  const parts = name.trim().split(/\s+/);
  return (parts[parts.length - 1] || name).toUpperCase().slice(0, 10);
}

function formationCounts(f) {
  const map = {
    '4-3-3': { DEF: 4, MID: 3, FWD: 3 },
    '4-4-2': { DEF: 4, MID: 4, FWD: 2 },
    '3-5-2': { DEF: 3, MID: 5, FWD: 2 },
  };
  return map[f] || map['4-3-3'];
}

function playerChip(ftp, live = {}, opts = {}) {
  const p = ftp.player || {};
  const points = live.matchday_points ?? ftp.matchday_points ?? 0;
  const mult = live.multiplier || ftp.multiplier || 1;
  const isCap = opts.isCaptain;
  const isVice = opts.isVice;
  const border = isCap ? 'border-primary shadow-[0_0_15px_rgba(229,195,99,0.3)]' : 'border-[#1C2333]';
  const avatar = typeof playerAvatarHtml === 'function'
    ? playerAvatarHtml(p, 'w-12 h-12 md:w-16 md:h-16')
    : `<div class="w-12 h-12 md:w-16 md:h-16 rounded-full bg-surface-elevated flex items-center justify-center"><span class="material-symbols-outlined text-on-surface-variant">person</span></div>`;
  return `
    <div class="flex flex-col items-center relative group cursor-pointer" data-player-id="${ftp.player_id}">
      <div class="rounded-full border-2 ${border} shadow-lg overflow-hidden relative flex items-center justify-center">
        ${avatar}
        ${isCap ? '<div class="absolute inset-0 bg-gradient-to-b from-primary/30 to-transparent pointer-events-none"></div>' : ''}
      </div>
      ${isCap ? '<div class="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-primary-container text-on-primary-container flex items-center justify-center font-stat-md text-xs font-bold shadow-md z-10">C</div>' : ''}
      ${isVice ? '<div class="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-surface-bright text-text-primary flex items-center justify-center font-stat-md text-xs font-bold shadow-md z-10 border border-outline-variant">V</div>' : ''}
      <div class="mt-1 bg-surface-elevated/80 backdrop-blur-sm rounded border border-outline-variant/50 px-2 py-0.5 min-w-[72px] text-center">
        <div class="font-body-sm text-body-sm font-semibold text-text-primary truncate">${shortName(p.name)}</div>
      </div>
      <div class="bg-surface/90 px-2 rounded-b font-stat-md text-xs text-secondary mt-0.5 border border-t-0 border-outline-variant/50">
        ${points}pts${mult > 1 ? ` · ${mult}x` : ''}
      </div>
      <div class="absolute top-full mt-2 w-36 bg-surface-container-high rounded-lg shadow-xl border border-outline-variant/30 opacity-0 group-hover:opacity-100 transition-opacity z-20 hidden md:block">
        <div class="p-2 flex flex-col gap-1">
          <button type="button" class="text-left font-body-sm text-xs px-2 py-1 hover:bg-surface-elevated rounded text-text-primary set-captain-btn" data-id="${ftp.player_id}">Make Captain</button>
          <button type="button" class="text-left font-body-sm text-xs px-2 py-1 hover:bg-surface-elevated rounded text-text-primary set-vice-btn" data-id="${ftp.player_id}">Make Vice</button>
        </div>
      </div>
    </div>`;
}

function renderPitch(team) {
  const starters = team.players.filter((p) => p.is_starting);
  const byPos = { GK: [], DEF: [], MID: [], FWD: [] };
  starters.forEach((ftp) => {
    const pos = ftp.player?.position;
    if (pos && byPos[pos]) byPos[pos].push(ftp);
  });

  const counts = formationCounts(currentFormation);
  // Prefer matching formation counts if we have enough players; otherwise show all starters by position
  function take(pos, n) {
    return (byPos[pos] || []).slice(0, Math.max(n, (byPos[pos] || []).length));
  }

  const fwd = take('FWD', counts.FWD);
  const mid = take('MID', counts.MID);
  const def = take('DEF', counts.DEF);
  const gk = byPos.GK || [];

  const chip = (ftp) => playerChip(ftp, pointsMap[ftp.player_id] || {}, {
    isCaptain: ftp.player_id === team.captain_id,
    isVice: ftp.player_id === team.vice_captain_id,
  });

  const pitch = document.getElementById('team-pitch');
  pitch.innerHTML = `
    <div class="absolute inset-0 border-[2px] border-white/10 m-4 rounded-sm pointer-events-none"></div>
    <div class="absolute inset-x-0 top-1/2 h-[2px] bg-white/10 pointer-events-none"></div>
    <div class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-24 h-24 rounded-full border-[2px] border-white/10 pointer-events-none"></div>
    <div class="absolute inset-0 flex flex-col justify-between py-8 px-4 sm:px-12">
      <div class="flex justify-around items-center w-full">${fwd.map(chip).join('')}</div>
      <div class="flex justify-around items-center w-full px-4">${mid.map(chip).join('')}</div>
      <div class="flex justify-between items-center w-full">${def.map(chip).join('')}</div>
      <div class="flex justify-center items-center w-full">${gk.map(chip).join('')}</div>
    </div>`;

  pitch.querySelectorAll('.set-captain-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      setCaptain(parseInt(btn.dataset.id, 10), team.vice_captain_id);
    });
  });
  pitch.querySelectorAll('.set-vice-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      setCaptain(team.captain_id, parseInt(btn.dataset.id, 10));
    });
  });
}

function renderBench(team) {
  const bench = team.players.filter((p) => !p.is_starting)
    .sort((a, b) => (a.bench_order || 99) - (b.bench_order || 99));
  let benchPts = 0;
  document.getElementById('team-bench').innerHTML = bench.map((ftp) => {
    const live = pointsMap[ftp.player_id] || {};
    benchPts += live.matchday_points || 0;
    const p = ftp.player || {};
    return `
      <div class="flex flex-col items-center min-w-[72px]">
        <div class="w-12 h-12 rounded-full overflow-hidden flex items-center justify-center">
          ${typeof playerAvatarHtml === 'function' ? playerAvatarHtml(p, 'w-12 h-12') : `<span class="material-symbols-outlined text-outline-variant text-sm">${p.position || '?'}</span>`}
        </div>
        <span class="text-[10px] font-bold mt-2 text-on-surface">${shortName(p.name)}</span>
        <span class="text-[10px] font-stat-md text-on-surface-variant">${p.position}</span>
      </div>`;
  }).join('') || '<span class="text-on-surface-variant font-body-sm">No substitutes</span>';
  document.getElementById('bench-points').textContent = benchPts;
}

async function setCaptain(captainId, viceId) {
  if (!captainId) return;
  const res = await fetch('/api/team/captain', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      captain_id: captainId,
      vice_captain_id: viceId || undefined,
    }),
  });
  const data = await res.json();
  if (data.success) {
    await refreshLivePoints();
  } else {
    alert(data.message || 'Could not update captain');
  }
}

async function loadTeam() {
  const res = await fetch('/api/team', { credentials: 'same-origin' });
  const data = await res.json().catch(() => ({ success: false }));
  if (!data.success) {
    document.querySelector('.max-w-7xl').innerHTML =
      '<div class="text-center py-20 text-on-surface-variant">Please <a class="text-primary underline" href="/login">login</a> to view your team.</div>';
    return null;
  }
  return data.team;
}

async function loadBoosters() {
  const box = document.getElementById('boosters-list');
  try {
    const res = await fetch('/api/boosters');
    const data = await res.json();
    if (!data.success) {
      box.innerHTML = '<p>Sign in to view boosters</p>';
      return;
    }
    const list = data.boosters || data;
    const items = Array.isArray(list) ? list : Object.entries(list).map(([type, info]) => ({ type, ...(info || {}) }));
    if (!items.length) {
      box.innerHTML = '<p>No boosters</p>';
      return;
    }
    box.innerHTML = items.map((b) => {
      const type = b.type || b.name || 'Booster';
      const available = b.available !== false && b.status !== 'used' && !b.used;
      return `
        <button type="button" class="w-full flex items-center justify-between p-3 rounded-lg border ${available ? 'border-primary/40 hover:bg-surface-elevated' : 'border-outline-variant opacity-60'} transition-colors booster-btn"
                data-type="${type}" ${available ? '' : 'disabled'}>
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-primary text-sm">${available ? 'star' : 'lock'}</span>
            <span class="font-body-sm font-bold text-on-surface">${type.replace(/_/g, ' ')}</span>
          </div>
          <span class="font-label-caps text-[10px] ${available ? 'text-tertiary' : 'text-on-surface-variant'}">${available ? 'Available' : 'Used'}</span>
        </button>`;
    }).join('');

    box.querySelectorAll('.booster-btn:not([disabled])').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const type = btn.dataset.type;
        let extra_data = {};
        if (type === '12TH_MAN' || type === '12th_man') {
          const pid = prompt('Enter player ID for 12th Man:');
          if (!pid) return;
          extra_data = { player_id: parseInt(pid, 10) };
        }
        if (!confirm(`Activate ${type}?`)) return;
        const r = await fetch('/api/boosters/activate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type, extra_data }),
        });
        const d = await r.json();
        alert(d.message || (d.success ? 'Activated' : 'Failed'));
        loadBoosters();
      });
    });
  } catch (_) {
    box.innerHTML = '<p>Unable to load boosters</p>';
  }
}

async function refreshLivePoints() {
  try {
    const res = await fetch('/api/live/points', { credentials: 'same-origin' });
    const data = await res.json().catch(() => ({ success: false }));

    const team = await loadTeam();
    if (!team) return;
    currentTeam = team;
    document.getElementById('team-status')?.classList.remove('hidden');

    pointsMap = {};
    if (data.success) {
      document.getElementById('md-points').textContent = data.total_points;
      const liveBadge = document.getElementById('live-indicator');
      if (data.is_live) {
        liveBadge.classList.remove('hidden');
        liveBadge.classList.add('flex');
      } else {
        liveBadge.classList.add('hidden');
        liveBadge.classList.remove('flex');
      }
      data.players.forEach((p) => { pointsMap[p.player_id] = p; });
    } else if (res.status === 401) {
      document.querySelector('.max-w-7xl').innerHTML =
        '<div class="text-center py-20 text-on-surface-variant">Please <a class="text-primary underline" href="/login">login</a> to view your team.</div>';
      return;
    }

    const prices = team.players.map((p) => p.player?.price || 0);
    const avg = prices.length ? prices.reduce((a, b) => a + b, 0) / prices.length : 0;
    document.getElementById('avg-value').textContent = `$${avg.toFixed(1)}m`;

    renderPitch(team);
    renderBench(team);

    const captain = team.players.find((p) => p.player_id === team.captain_id);
    const vice = team.players.find((p) => p.player_id === team.vice_captain_id);
    document.getElementById('captain-widget').innerHTML = `
    <p class="mb-1">Captain: <strong class="text-primary">${captain?.player?.name || '—'}</strong></p>
    <p class="mb-3">Vice: <strong class="text-on-surface">${vice?.player?.name || '—'}</strong></p>
    <button type="button" class="w-full border border-primary text-primary font-label-caps text-label-caps py-2 rounded-lg hover:bg-primary/10" id="change-captain-btn">Change Captain</button>
  `;
    document.getElementById('change-captain-btn')?.addEventListener('click', openCaptainModal);

    if (data.success) {
      document.getElementById('live-points-list').innerHTML = data.players
        .filter((p) => p.is_starting)
        .sort((a, b) => b.matchday_points - a.matchday_points)
        .map((p) => {
          const extras = [];
          if (p.minutes_played > 0) extras.push(`${p.minutes_played}'`);
          if (p.goals > 0) extras.push(`${p.goals}G`);
          if (p.assists > 0) extras.push(`${p.assists}A`);
          const statStr = extras.length ? ` · ${extras.join(', ')}` : '';
          return `<li class="flex justify-between gap-2"><span class="truncate">${p.name}</span><span class="font-stat-md text-primary flex-shrink-0">${p.matchday_points}pts${p.multiplier > 1 ? ` (${p.multiplier}x)` : ''}</span></li><li class="text-[11px] text-on-surface-variant -mt-1 mb-1">${p.position}${statStr}</li>`;
        })
        .join('') || '<li>No live data</li>';
    }
  } catch (e) {
    console.error('refreshLivePoints', e);
  }
}

function openCaptainModal() {
  if (!currentTeam) return;
  const starters = currentTeam.players.filter((p) => p.is_starting);
  const cap = document.getElementById('modal-captain');
  const vice = document.getElementById('modal-vice');
  const opts = starters.map((p) => `<option value="${p.player_id}">${p.player?.name}</option>`).join('');
  cap.innerHTML = opts;
  vice.innerHTML = opts;
  cap.value = currentTeam.captain_id;
  vice.value = currentTeam.vice_captain_id;
  document.getElementById('captain-modal').style.display = 'flex';
}

document.getElementById('cancel-captain')?.addEventListener('click', () => {
  document.getElementById('captain-modal').style.display = 'none';
});
document.getElementById('confirm-captain')?.addEventListener('click', async () => {
  const captainId = parseInt(document.getElementById('modal-captain').value, 10);
  const viceId = parseInt(document.getElementById('modal-vice').value, 10);
  await setCaptain(captainId, viceId);
  document.getElementById('captain-modal').style.display = 'none';
});

document.querySelectorAll('.formation-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    currentFormation = btn.dataset.f;
    document.querySelectorAll('.formation-btn').forEach((b) => {
      b.classList.remove('text-primary', 'bg-surface-bright');
      b.classList.add('text-text-secondary');
    });
    btn.classList.add('text-primary', 'bg-surface-bright');
    btn.classList.remove('text-text-secondary');
    if (currentTeam) renderPitch(currentTeam);
  });
});

async function init() {
  await refreshLivePoints();
  loadBoosters();
  pollInterval = setInterval(refreshLivePoints, 60000);
}

init();
