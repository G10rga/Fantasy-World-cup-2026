const POSITION_LIMITS = { GK: 2, DEF: 5, MID: 5, FWD: 3 };
const SQUAD_SIZE = 15;
const STARTING_XI = 11;
const BUDGET = 100.0;
// Must match backend VALID_FORMATIONS with the "at least 2 forwards" rule
const VALID_FORMATIONS = [
  [3, 4, 3],
  [3, 5, 2],
  [4, 3, 3],
  [4, 4, 2],
  [5, 2, 3],
  [5, 3, 2],
];

let squad = [];
let allPlayers = [];
let searchQuery = '';
let activeSlotPos = null;

function positionCount(pos) {
  return squad.filter((p) => p.position === pos).length;
}

function squadCost() {
  return squad.reduce((sum, p) => sum + Number(p.price), 0);
}

function shortName(name) {
  if (!name) return '';
  const parts = name.trim().split(/\s+/);
  return (parts[parts.length - 1] || name).toUpperCase().slice(0, 10);
}

function startersByPos() {
  const byPos = { GK: [], DEF: [], MID: [], FWD: [] };
  squad.filter((p) => p.is_starting).forEach((p) => byPos[p.position]?.push(p));
  return byPos;
}

function squadByPos() {
  const byPos = { GK: [], DEF: [], MID: [], FWD: [] };
  squad.forEach((p) => byPos[p.position]?.push(p));
  return byPos;
}

function preferKeepStarting(players) {
  return [...players].sort((a, b) => Number(b.is_starting) - Number(a.is_starting));
}

/** Pick a valid XI from the current 15 (or partial squad). */
function rebalanceStarting() {
  const byPos = squadByPos();
  for (const pos of Object.keys(byPos)) {
    byPos[pos] = preferKeepStarting(byPos[pos]);
  }

  let best = null;
  let bestScore = -1;
  for (const [d, m, f] of VALID_FORMATIONS) {
    if (byPos.GK.length < 1) continue;
    if (byPos.DEF.length < d || byPos.MID.length < m || byPos.FWD.length < f) continue;
    // Prefer formations that start more of our FWDs, then more players overall fit
    const score = f * 100 + d * 10 + m;
    if (score > bestScore) {
      bestScore = score;
      best = [d, m, f];
    }
  }

  const startIds = new Set();
  if (best) {
    const [d, m, f] = best;
    byPos.GK.slice(0, 1).forEach((p) => startIds.add(p.id));
    byPos.DEF.slice(0, d).forEach((p) => startIds.add(p.id));
    byPos.MID.slice(0, m).forEach((p) => startIds.add(p.id));
    byPos.FWD.slice(0, f).forEach((p) => startIds.add(p.id));
  } else {
    // Incomplete squad: greedy partial XI (1 GK, ≥2 FWD when possible, ≥3 DEF when possible)
    byPos.GK.slice(0, 1).forEach((p) => startIds.add(p.id));
    byPos.FWD.slice(0, Math.min(2, byPos.FWD.length)).forEach((p) => startIds.add(p.id));
    byPos.DEF.slice(0, Math.min(3, byPos.DEF.length)).forEach((p) => startIds.add(p.id));
    const rest = [...byPos.MID, ...byPos.DEF, ...byPos.FWD, ...byPos.GK]
      .filter((p) => !startIds.has(p.id));
    for (const p of rest) {
      if (startIds.size >= STARTING_XI) break;
      if (p.position === 'GK' && [...startIds].some((id) => squad.find((s) => s.id === id)?.position === 'GK')) {
        continue;
      }
      startIds.add(p.id);
    }
  }

  squad.forEach((p) => {
    p.is_starting = startIds.has(p.id);
  });
  reindexBench();
}

function reindexBench() {
  squad
    .filter((p) => !p.is_starting)
    .sort((a, b) => (a.bench_order || 99) - (b.bench_order || 99))
    .forEach((p, i) => {
      p.bench_order = i + 1;
    });
  squad.filter((p) => p.is_starting).forEach((p) => {
    p.bench_order = null;
  });
}

function updateBudget() {
  const remaining = BUDGET - squadCost();
  const spent = squadCost();
  const remEl = document.getElementById('budget-remaining');
  remEl.textContent = `$${remaining.toFixed(1)}m`;
  remEl.classList.toggle('over-budget', remaining < 0);
  document.getElementById('squad-count').textContent = `${squad.length} / ${SQUAD_SIZE}`;
  document.getElementById('squad-count-footer').textContent = `${squad.length} / ${SQUAD_SIZE}`;
  document.getElementById('budget-bar-label').textContent = `$${spent.toFixed(1)}m / $${BUDGET.toFixed(1)}m`;
  document.getElementById('budget-bar').style.width = `${Math.min(100, (spent / BUDGET) * 100)}%`;
}

function renderPlayerRow(player) {
  const inSquad = squad.some((p) => p.id === player.id);
  const code = (player.country?.fifa_code || player.country?.code || player.country?.name || '').toString().slice(0, 3).toUpperCase();
  const photo = player.photo_url || '';
  const sq = squad.find((p) => p.id === player.id);
  const role = sq ? (sq.is_starting ? 'XI' : 'Bench') : '';
  return `
    <div class="flex items-center justify-between p-3 rounded-xl ${inSquad ? 'bg-surface-elevated border border-primary/40' : 'bg-surface-container-low border border-transparent'} hover:border-outline-variant hover:bg-surface-elevated transition-colors mb-2 group">
      <div class="flex items-center gap-3 min-w-0">
        <div class="w-10 h-10 rounded-full bg-surface-variant border border-outline overflow-hidden flex-shrink-0 flex items-center justify-center">
          ${photo
            ? `<img alt="" class="w-full h-full object-cover" src="${photo}" onerror="this.parentElement.innerHTML='<span class=\\'material-symbols-outlined text-outline-variant\\'>person</span>'">`
            : `<span class="material-symbols-outlined text-outline-variant">person</span>`}
        </div>
        <div class="min-w-0">
          <div class="font-bold text-sm text-on-surface group-hover:text-primary transition-colors truncate">${player.name}</div>
          <div class="flex items-center gap-2 text-xs text-on-surface-variant mt-0.5">
            <span class="font-stat-md bg-surface-variant px-1 rounded">${player.position}</span>
            <span>${code}</span>
            ${role ? `<span class="text-primary">${role}</span>` : ''}
            ${player.scouting_bonus_eligible ? '<span class="text-tertiary">Scout</span>' : ''}
          </div>
        </div>
      </div>
      <div class="flex items-center gap-4 flex-shrink-0">
        <div class="text-right">
          <div class="font-stat-md text-primary font-bold text-sm">$${player.price}m</div>
          <div class="text-xs text-on-surface-variant">${player.total_pts} pts</div>
        </div>
        <button type="button" class="w-8 h-8 rounded ${inSquad ? 'bg-danger/20 text-danger hover:bg-danger/30' : 'bg-surface-variant hover:bg-primary-container hover:text-on-primary-container text-on-surface'} flex items-center justify-center transition-colors border border-outline-variant"
                onclick="${inSquad ? 'removePlayer' : 'addPlayer'}(${player.id})">
          <span class="material-symbols-outlined text-sm">${inSquad ? 'remove' : 'add'}</span>
        </button>
      </div>
    </div>`;
}

function renderPlayerGrid(players) {
  let list = players;
  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    list = list.filter((p) => p.name.toLowerCase().includes(q));
  }
  if (activeSlotPos) {
    list = [...list].sort((a, b) => {
      const aIn = squad.some((p) => p.id === a.id) ? 1 : 0;
      const bIn = squad.some((p) => p.id === b.id) ? 1 : 0;
      return aIn - bIn;
    });
  }
  const grid = document.getElementById('player-grid');
  if (!list.length) {
    grid.innerHTML = `<div class="text-center py-16 text-on-surface-variant font-body-sm">${activeSlotPos ? `No ${activeSlotPos} players found` : 'No players found'}</div>`;
    return;
  }
  const hint = activeSlotPos
    ? `<div class="px-2 py-2 mb-1 text-xs text-primary font-label-caps tracking-wide">Select a ${activeSlotPos} for your squad</div>`
    : '';
  grid.innerHTML = hint + list.map(renderPlayerRow).join('');
}

function emptySlot(pos) {
  const active = activeSlotPos === pos;
  return `
    <button type="button" class="flex flex-col items-center group" onclick="selectSlot('${pos}')" title="Add ${pos}">
      <div class="w-14 h-14 md:w-16 md:h-16 rounded-full bg-surface-elevated border-2 border-dashed ${active ? 'border-primary bg-primary/10' : 'border-outline-variant group-hover:border-primary'} flex items-center justify-center shadow-lg cursor-pointer transition-colors">
        <span class="material-symbols-outlined ${active ? 'text-primary' : 'text-outline-variant group-hover:text-primary'}">add</span>
      </div>
      <span class="text-xs font-medium mt-3 ${active ? 'text-primary' : 'text-outline-variant'}">${pos}</span>
    </button>`;
}

function filledSlot(player) {
  const photo = player.photo_url || '';
  return `
    <button type="button" class="flex flex-col items-center cursor-pointer" onclick="benchPlayer(${player.id})" title="Move ${player.name} to bench">
      <div class="w-14 h-14 md:w-16 md:h-16 rounded-full bg-surface-elevated border-2 border-primary flex items-center justify-center shadow-lg relative hover:scale-105 transition-transform overflow-hidden">
        ${photo
          ? `<img src="${photo}" class="w-full h-full object-cover" alt="" onerror="this.remove()">`
          : `<span class="material-symbols-outlined text-primary">person</span>`}
        <div class="absolute -bottom-2 bg-surface px-2 py-0.5 rounded text-[10px] font-stat-md border border-outline-variant text-primary">$${player.price}</div>
      </div>
      <span class="text-xs font-bold mt-3 bg-surface/80 px-2 py-1 rounded">${shortName(player.name)}</span>
    </button>`;
}

function benchSlot(player) {
  const photo = player.photo_url || '';
  return `
    <button type="button" class="flex flex-col items-center cursor-pointer" onclick="promotePlayer(${player.id})" title="Start ${player.name}">
      <div class="w-12 h-12 rounded-full bg-surface-elevated border-2 border-outline-variant flex items-center justify-center shadow relative hover:border-primary transition-colors overflow-hidden">
        ${photo
          ? `<img src="${photo}" class="w-full h-full object-cover" alt="" onerror="this.remove()">`
          : `<span class="material-symbols-outlined text-outline-variant text-sm">person</span>`}
      </div>
      <span class="text-[10px] font-bold mt-2 text-on-surface-variant">${shortName(player.name)}</span>
      <span class="text-[9px] text-outline-variant">${player.position}</span>
    </button>`;
}

function renderPitch() {
  const starters = startersByPos();
  const maxShow = {
    FWD: Math.min(POSITION_LIMITS.FWD, Math.max(2, starters.FWD.length)),
    MID: Math.min(POSITION_LIMITS.MID, Math.max(starters.MID.length, 2)),
    DEF: Math.min(POSITION_LIMITS.DEF, Math.max(3, starters.DEF.length)),
    GK: 1,
  };
  // Leave an empty add-slot while that position still has room in the 15
  for (const pos of ['FWD', 'MID', 'DEF']) {
    if (positionCount(pos) < POSITION_LIMITS[pos] && starters[pos].length >= maxShow[pos]) {
      maxShow[pos] = Math.min(POSITION_LIMITS[pos], starters[pos].length + 1);
    }
  }

  function row(pos, max) {
    const filled = starters[pos] || [];
    const slots = filled.map((p) => filledSlot(p));
    const empties = Math.max(0, max - filled.length);
    for (let i = 0; i < empties; i++) slots.push(emptySlot(pos));
    if (!slots.length) return '';
    return `<div class="flex justify-center gap-2 md:gap-3 w-full flex-wrap">${slots.join('')}</div>`;
  }

  const bench = squad
    .filter((p) => !p.is_starting)
    .sort((a, b) => (a.bench_order || 99) - (b.bench_order || 99));

  const benchHtml = bench.length
    ? `<div class="w-full mt-1 pt-3 border-t border-white/10">
        <div class="text-[10px] font-label-caps text-outline-variant mb-2 text-center tracking-wider">BENCH · tap to start</div>
        <div class="flex justify-center gap-3 flex-wrap">${bench.map(benchSlot).join('')}</div>
      </div>`
    : (squad.length
      ? `<div class="w-full mt-1 pt-3 border-t border-white/10 text-center text-[10px] text-outline-variant">All selected players are in your XI</div>`
      : '');

  document.getElementById('pitch-view').innerHTML = `
    ${row('FWD', maxShow.FWD)}
    ${row('MID', maxShow.MID)}
    ${row('DEF', maxShow.DEF)}
    ${row('GK', maxShow.GK)}
    ${benchHtml}
  `;

  updateCaptainSelects();
}

function updateCaptainSelects() {
  const starters = squad.filter((p) => p.is_starting);
  const capSel = document.getElementById('captain-select');
  const viceSel = document.getElementById('vice-select');
  const capVal = capSel.value;
  const viceVal = viceSel.value;
  const opts = starters.map((p) => `<option value="${p.id}">${p.name}</option>`).join('') || '<option value="">— Select —</option>';
  capSel.innerHTML = opts;
  viceSel.innerHTML = opts;
  if (capVal && starters.some((p) => String(p.id) === String(capVal))) capSel.value = capVal;
  if (viceVal && starters.some((p) => String(p.id) === String(viceVal))) viceSel.value = viceVal;
}

function updatePosChips(pos) {
  document.querySelectorAll('.pos-chip').forEach((b) => {
    const selected = (b.dataset.pos || '') === (pos || '');
    b.classList.toggle('bg-primary-container', selected);
    b.classList.toggle('text-on-primary-container', selected);
    b.classList.toggle('bg-surface-variant', !selected);
    b.classList.toggle('text-on-surface', !selected);
    b.classList.toggle('border', !selected);
    b.classList.toggle('border-outline-variant', !selected);
  });
  document.getElementById('filter-position').value = pos || '';
}

window.selectSlot = function (pos) {
  activeSlotPos = pos;
  updatePosChips(pos);
  loadPlayers();
  const panel = document.getElementById('player-grid');
  if (panel && window.matchMedia('(max-width: 1023px)').matches) {
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  renderPitch();
};

window.addPlayer = function (id) {
  const player = allPlayers.find((p) => p.id === id);
  if (!player) return;
  if (squad.length >= SQUAD_SIZE) { alert('Squad is full (15 players)'); return; }
  if (positionCount(player.position) >= POSITION_LIMITS[player.position]) {
    alert(`Maximum ${POSITION_LIMITS[player.position]} ${player.position} players`);
    return;
  }
  const countryCount = squad.filter((p) => p.country_id === player.country_id).length;
  if (countryCount >= 3) { alert('Maximum 3 players from same country'); return; }

  squad.push({
    ...player,
    is_starting: true, // rebalanceStarting will place them correctly
    bench_order: null,
  });
  rebalanceStarting();

  if (activeSlotPos === player.position) {
    const filled = squad.filter((p) => p.is_starting && p.position === player.position).length;
    const need = player.position === 'FWD' ? 2 : player.position === 'DEF' ? 3 : player.position === 'GK' ? 1 : 3;
    if (filled >= need && positionCount(player.position) >= POSITION_LIMITS[player.position]) {
      activeSlotPos = null;
    }
  }
  refresh();
};

window.removePlayer = function (id) {
  squad = squad.filter((p) => p.id !== id);
  rebalanceStarting();
  refresh();
};

/** Move a starter to the bench (swaps with a bench player when XI must stay at 11). */
window.benchPlayer = function (id) {
  const player = squad.find((p) => p.id === id);
  if (!player || !player.is_starting) return;
  const bench = squad.filter((p) => !p.is_starting);
  // Prefer promoting a bench player of the same position, else any outfield/GK as needed
  let swap = bench.find((p) => p.position === player.position);
  if (!swap) swap = bench[0];
  player.is_starting = false;
  if (swap) swap.is_starting = true;
  rebalanceStarting();
  refresh();
};

/** Promote a bench player into the XI. */
window.promotePlayer = function (id) {
  const player = squad.find((p) => p.id === id);
  if (!player || player.is_starting) return;
  player.is_starting = true;
  // If over 11, demote someone else (prefer same position excess, else last added starter of overloaded pos)
  const starters = squad.filter((p) => p.is_starting);
  if (starters.length > STARTING_XI) {
    const demote = starters
      .filter((p) => p.id !== player.id)
      .sort((a, b) => {
        // Prefer demoting a different position that has surplus vs formation needs
        if (a.position === player.position && b.position !== player.position) return 1;
        if (b.position === player.position && a.position !== player.position) return -1;
        return 0;
      })[0];
    if (demote) demote.is_starting = false;
  }
  rebalanceStarting();
  refresh();
};

function refresh() {
  updateBudget();
  renderPlayerGrid(allPlayers);
  renderPitch();
}

function formationOk() {
  const s = startersByPos();
  if (s.GK.length !== 1) return false;
  return VALID_FORMATIONS.some(
    ([d, m, f]) => s.DEF.length === d && s.MID.length === m && s.FWD.length === f
  );
}

async function loadPlayers() {
  const pos = document.getElementById('filter-position').value;
  const country = document.getElementById('filter-country').value;
  const price = document.getElementById('filter-price').value;
  const sort = document.getElementById('filter-sort').value;

  let url = `/api/players?sort_by=${sort}`;
  if (pos) url += `&position=${pos}`;
  if (country) url += `&country=${country}`;
  if (price) url += `&max_price=${price}`;

  const res = await fetch(url);
  const data = await res.json();
  if (data.success) {
    allPlayers = data.players;
    renderPlayerGrid(allPlayers);
  }
}

async function loadCountries() {
  const res = await fetch('/api/countries');
  const data = await res.json();
  const select = document.getElementById('filter-country');
  if (data.success) {
    data.countries.forEach((c) => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name;
      select.appendChild(opt);
    });
  }
}

async function loadExistingTeam() {
  try {
    const res = await fetch('/api/team');
    const data = await res.json();
    if (data.success && data.team.players.length) {
      squad = data.team.players.map((ftp) => ({
        ...ftp.player,
        is_starting: ftp.is_starting,
        bench_order: ftp.bench_order,
      }));
      // Fix broken XI (e.g. 0 FWDs starting while FWDs sit on bench)
      if (squad.length && !formationOk()) {
        rebalanceStarting();
      }
      if (data.team.captain_id) document.getElementById('captain-select').value = data.team.captain_id;
      if (data.team.vice_captain_id) document.getElementById('vice-select').value = data.team.vice_captain_id;
      refresh();
    }
  } catch (_) { /* not logged in */ }
}

document.getElementById('filter-apply').addEventListener('click', loadPlayers);
document.getElementById('filter-sort').addEventListener('change', loadPlayers);
document.getElementById('filter-country').addEventListener('change', loadPlayers);

document.querySelectorAll('.pos-chip').forEach((btn) => {
  btn.addEventListener('click', () => {
    const pos = btn.dataset.pos || '';
    activeSlotPos = pos || null;
    updatePosChips(pos);
    loadPlayers();
    renderPitch();
  });
});

let searchTimer;
document.getElementById('player-search').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    searchQuery = e.target.value;
    renderPlayerGrid(allPlayers);
  }, 150);
});

document.getElementById('save-squad').addEventListener('click', async () => {
  const msg = document.getElementById('save-msg');
  if (squad.length !== SQUAD_SIZE) {
    msg.textContent = 'Squad must have exactly 15 players';
    msg.className = 'error-msg';
    return;
  }
  rebalanceStarting();
  refresh();
  const starters = squad.filter((p) => p.is_starting);
  if (starters.length !== STARTING_XI) {
    msg.textContent = `Starting XI must have exactly ${STARTING_XI} players (currently ${starters.length})`;
    msg.className = 'error-msg';
    return;
  }
  if (!formationOk()) {
    msg.textContent = 'Invalid starting formation. Need 1 GK and a valid DEF-MID-FWD (min 2 FWD).';
    msg.className = 'error-msg';
    return;
  }
  const captainId = parseInt(document.getElementById('captain-select').value, 10);
  const viceId = parseInt(document.getElementById('vice-select').value, 10);
  if (!captainId || !viceId) {
    msg.textContent = 'Select a captain and vice captain';
    msg.className = 'error-msg';
    return;
  }
  if (captainId === viceId) {
    msg.textContent = 'Captain and vice captain must be different players';
    msg.className = 'error-msg';
    return;
  }
  const payload = {
    squad: squad.map((p) => ({
      player_id: p.id,
      is_starting: p.is_starting,
      bench_order: p.bench_order,
    })),
    captain_id: captainId,
    vice_captain_id: viceId,
  };
  try {
    const res = await fetch('/api/team/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({ success: false, message: 'Server error' }));
    if (data.success) {
      msg.textContent = 'Squad saved successfully!';
      msg.className = 'success-msg';
    } else {
      msg.textContent = data.message || (res.status === 401 ? 'Please log in first' : 'Save failed');
      msg.className = 'error-msg';
    }
  } catch (_) {
    msg.textContent = 'Network error';
    msg.className = 'error-msg';
  }
});

loadCountries();
loadPlayers();
loadExistingTeam();
