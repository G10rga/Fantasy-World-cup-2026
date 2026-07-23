const POSITION_LIMITS = { GK: 2, DEF: 5, MID: 5, FWD: 3 };
const SQUAD_SIZE = 15;
const STARTING_XI = 11;
const BENCH_SIZE = 4;
const BUDGET = 100.0;

/** formation key -> { DEF, MID, FWD } (GK always 1) */
const FORMATIONS = {
  '4-3-3': { DEF: 4, MID: 3, FWD: 3 },
  '4-4-2': { DEF: 4, MID: 4, FWD: 2 },
  '3-5-2': { DEF: 3, MID: 5, FWD: 2 },
  '3-4-3': { DEF: 3, MID: 4, FWD: 3 },
  '5-3-2': { DEF: 5, MID: 3, FWD: 2 },
  '5-2-3': { DEF: 5, MID: 2, FWD: 3 },
};

let formationKey = '4-3-3';
let squad = [];
let allPlayers = [];
let searchQuery = '';
/** @type {null | { kind: 'xi'|'bench', pos: string }} */
let activeSlot = null;

function formationSlots() {
  const f = FORMATIONS[formationKey];
  return { GK: 1, DEF: f.DEF, MID: f.MID, FWD: f.FWD };
}

function benchSlots() {
  const xi = formationSlots();
  return {
    GK: POSITION_LIMITS.GK - xi.GK,
    DEF: POSITION_LIMITS.DEF - xi.DEF,
    MID: POSITION_LIMITS.MID - xi.MID,
    FWD: POSITION_LIMITS.FWD - xi.FWD,
  };
}

function positionCount(pos) {
  return squad.filter((p) => p.position === pos).length;
}

function starters() {
  return squad.filter((p) => p.is_starting);
}

function bench() {
  return squad.filter((p) => !p.is_starting).sort((a, b) => (a.bench_order || 99) - (b.bench_order || 99));
}

function startersByPos() {
  const byPos = { GK: [], DEF: [], MID: [], FWD: [] };
  starters().forEach((p) => byPos[p.position]?.push(p));
  return byPos;
}

function benchByPos() {
  const byPos = { GK: [], DEF: [], MID: [], FWD: [] };
  bench().forEach((p) => byPos[p.position]?.push(p));
  return byPos;
}

function xiComplete() {
  if (starters().length !== STARTING_XI) return false;
  const need = formationSlots();
  const have = startersByPos();
  return ['GK', 'DEF', 'MID', 'FWD'].every((pos) => have[pos].length === need[pos]);
}

function benchComplete() {
  return bench().length === BENCH_SIZE && squad.length === SQUAD_SIZE;
}

function currentPhase() {
  return xiComplete() ? 'bench' : 'xi';
}

function squadCost() {
  return squad.reduce((sum, p) => sum + Number(p.price), 0);
}

function shortName(name) {
  if (!name) return '';
  const parts = name.trim().split(/\s+/);
  return (parts[parts.length - 1] || name).toUpperCase().slice(0, 10);
}

function reindexBench() {
  bench().forEach((p, i) => {
    p.bench_order = i + 1;
  });
  starters().forEach((p) => {
    p.bench_order = null;
  });
}

function setStatus(msg, isError) {
  const el = document.getElementById('save-msg');
  if (!msg) {
    el.textContent = '';
    el.className = '';
    return;
  }
  el.textContent = msg;
  el.className = isError ? 'error-msg' : 'success-msg';
}

function updatePhaseUi() {
  const phase = currentPhase();
  const xiN = starters().length;
  const benchN = bench().length;
  const phaseEl = document.getElementById('build-phase');
  const hintEl = document.getElementById('build-hint');

  if (phase === 'xi') {
    phaseEl.textContent = `STEP 1 · STARTING XI ${xiN}/${STARTING_XI}`;
    hintEl.textContent = `Fill every pitch slot for ${formationKey}. Bench stays locked until your XI is complete.`;
  } else if (!benchComplete()) {
    phaseEl.textContent = `STEP 2 · BENCH ${benchN}/${BENCH_SIZE}`;
    hintEl.textContent = 'XI locked in. Add your 4 bench players into the bench slots below.';
  } else {
    phaseEl.textContent = 'READY · 15/15';
    hintEl.textContent = 'Squad complete. Set captain & vice, then save.';
  }
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
  updatePhaseUi();
}

function updateFormationPills() {
  document.querySelectorAll('.formation-btn').forEach((btn) => {
    const on = btn.dataset.f === formationKey;
    btn.classList.toggle('bg-primary-container', on);
    btn.classList.toggle('text-on-primary-container', on);
    btn.classList.toggle('bg-surface-variant', !on);
    btn.classList.toggle('text-on-surface-variant', !on);
  });
}

function applyFormation(key) {
  if (!FORMATIONS[key]) return;
  const prev = formationSlots();
  formationKey = key;
  const next = formationSlots();

  // Keep players; demote any starters that no longer fit the new shape
  ['DEF', 'MID', 'FWD'].forEach((pos) => {
    const list = startersByPos()[pos];
    const keep = next[pos];
    list.slice(keep).forEach((p) => {
      p.is_starting = false;
    });
  });
  // GK: only 1 starter
  startersByPos().GK.slice(1).forEach((p) => {
    p.is_starting = false;
  });

  // If we demoted people before XI was complete, they sit as "orphan" bench early —
  // move orphans out of squad? Better: if XI incomplete, remove demoted from squad
  // so user isn't confused. Or keep them and if !xiComplete treat non-starters as invalid.
  if (!xiComplete()) {
    // Drop anyone not starting while still building XI (formation change mid-pick)
    const orphanIds = new Set(bench().map((p) => p.id));
    if (orphanIds.size) {
      squad = squad.filter((p) => p.is_starting);
      setStatus(`Formation set to ${key}. Extra players were cleared — refill the new pitch slots.`, true);
    } else {
      setStatus('');
    }
  }

  // If somehow over bench quotas after formation change on complete XI, trim bench overflow
  if (xiComplete()) {
    const quotas = benchSlots();
    const bPos = benchByPos();
    ['GK', 'DEF', 'MID', 'FWD'].forEach((pos) => {
      bPos[pos].slice(quotas[pos]).forEach((p) => {
        squad = squad.filter((s) => s.id !== p.id);
      });
    });
  }

  reindexBench();
  activeSlot = null;
  updateFormationPills();
  refresh();
}

function detectFormationFromStarters() {
  const s = startersByPos();
  if (s.GK.length !== 1) return null;
  for (const [key, f] of Object.entries(FORMATIONS)) {
    if (s.DEF.length === f.DEF && s.MID.length === f.MID && s.FWD.length === f.FWD) {
      return key;
    }
  }
  return null;
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
  if (activeSlot) {
    list = list.filter((p) => p.position === activeSlot.pos);
    list = [...list].sort((a, b) => {
      const aIn = squad.some((p) => p.id === a.id) ? 1 : 0;
      const bIn = squad.some((p) => p.id === b.id) ? 1 : 0;
      return aIn - bIn;
    });
  }
  const grid = document.getElementById('player-grid');
  if (!list.length) {
    grid.innerHTML = '<div class="text-center py-16 text-on-surface-variant font-body-sm">No players found</div>';
    return;
  }
  let hint = '';
  if (activeSlot?.kind === 'xi') {
    hint = `<div class="px-2 py-2 mb-1 text-xs text-primary font-label-caps tracking-wide">Pick a ${activeSlot.pos} for your starting XI</div>`;
  } else if (activeSlot?.kind === 'bench') {
    hint = `<div class="px-2 py-2 mb-1 text-xs text-primary font-label-caps tracking-wide">Pick a ${activeSlot.pos} for the bench</div>`;
  } else if (currentPhase() === 'xi') {
    hint = `<div class="px-2 py-2 mb-1 text-xs text-on-surface-variant">Tap an empty pitch slot, or use + to fill your ${formationKey} XI (${starters().length}/${STARTING_XI})</div>`;
  } else {
    hint = `<div class="px-2 py-2 mb-1 text-xs text-on-surface-variant">Tap an empty bench slot to add reserves (${bench().length}/${BENCH_SIZE})</div>`;
  }
  grid.innerHTML = hint + list.map(renderPlayerRow).join('');
}

function emptyXiSlot(pos) {
  const active = activeSlot?.kind === 'xi' && activeSlot.pos === pos;
  return `
    <button type="button" class="flex flex-col items-center group" onclick="selectXiSlot('${pos}')" title="Add starting ${pos}">
      <div class="w-14 h-14 md:w-16 md:h-16 rounded-full bg-surface-elevated border-2 border-dashed ${active ? 'border-primary bg-primary/10' : 'border-outline-variant group-hover:border-primary'} flex items-center justify-center shadow-lg transition-colors">
        <span class="material-symbols-outlined ${active ? 'text-primary' : 'text-outline-variant group-hover:text-primary'}">add</span>
      </div>
      <span class="text-xs font-medium mt-3 ${active ? 'text-primary' : 'text-outline-variant'}">${pos}</span>
    </button>`;
}

function emptyBenchSlot(pos, locked) {
  const active = !locked && activeSlot?.kind === 'bench' && activeSlot.pos === pos;
  if (locked) {
    return `
      <div class="flex flex-col items-center opacity-40" title="Finish starting XI first">
        <div class="w-12 h-12 rounded-full bg-surface-elevated border-2 border-dashed border-outline-variant flex items-center justify-center">
          <span class="material-symbols-outlined text-outline-variant text-sm">lock</span>
        </div>
        <span class="text-[10px] mt-2 text-outline-variant">${pos}</span>
      </div>`;
  }
  return `
    <button type="button" class="flex flex-col items-center group" onclick="selectBenchSlot('${pos}')" title="Add bench ${pos}">
      <div class="w-12 h-12 rounded-full bg-surface-elevated border-2 border-dashed ${active ? 'border-primary bg-primary/10' : 'border-outline-variant group-hover:border-primary'} flex items-center justify-center transition-colors">
        <span class="material-symbols-outlined text-sm ${active ? 'text-primary' : 'text-outline-variant'}">add</span>
      </div>
      <span class="text-[10px] mt-2 ${active ? 'text-primary' : 'text-outline-variant'}">${pos}</span>
    </button>`;
}

function filledSlot(player) {
  const photo = player.photo_url || '';
  return `
    <button type="button" class="flex flex-col items-center" onclick="removePlayer(${player.id})" title="Remove ${player.name}">
      <div class="w-14 h-14 md:w-16 md:h-16 rounded-full bg-surface-elevated border-2 border-primary flex items-center justify-center shadow-lg relative hover:scale-105 transition-transform overflow-hidden">
        ${photo
          ? `<img src="${photo}" class="w-full h-full object-cover" alt="" onerror="this.remove()">`
          : `<span class="material-symbols-outlined text-primary">person</span>`}
        <div class="absolute -bottom-2 bg-surface px-2 py-0.5 rounded text-[10px] font-stat-md border border-outline-variant text-primary">$${player.price}</div>
      </div>
      <span class="text-xs font-bold mt-3 bg-surface/80 px-2 py-1 rounded">${shortName(player.name)}</span>
    </button>`;
}

function filledBenchSlot(player) {
  const photo = player.photo_url || '';
  return `
    <button type="button" class="flex flex-col items-center" onclick="removePlayer(${player.id})" title="Remove ${player.name}">
      <div class="w-12 h-12 rounded-full bg-surface-elevated border-2 border-primary/60 flex items-center justify-center relative overflow-hidden hover:border-danger transition-colors">
        ${photo
          ? `<img src="${photo}" class="w-full h-full object-cover" alt="" onerror="this.remove()">`
          : `<span class="material-symbols-outlined text-primary text-sm">person</span>`}
      </div>
      <span class="text-[10px] font-bold mt-2 text-on-surface-variant">${shortName(player.name)}</span>
      <span class="text-[9px] text-outline-variant">${player.position}</span>
    </button>`;
}

function rowSlots(pos, filled, total, emptyFn) {
  const slots = filled.map((p) => (emptyFn === emptyBenchSlot ? filledBenchSlot(p) : filledSlot(p)));
  const empties = Math.max(0, total - filled.length);
  for (let i = 0; i < empties; i++) {
    slots.push(emptyFn(pos));
  }
  return slots;
}

function renderPitch() {
  const need = formationSlots();
  const have = startersByPos();
  const bNeed = benchSlots();
  const bHave = benchByPos();
  const lockedBench = !xiComplete();

  function xiRow(pos) {
    const slots = [];
    have[pos].forEach((p) => slots.push(filledSlot(p)));
    for (let i = have[pos].length; i < need[pos]; i++) slots.push(emptyXiSlot(pos));
    return `<div class="flex justify-center gap-2 md:gap-3 w-full flex-wrap">${slots.join('')}</div>`;
  }

  // Bench empties in a stable order: GK, DEF, MID, FWD
  const benchBits = [];
  ['GK', 'DEF', 'MID', 'FWD'].forEach((pos) => {
    bHave[pos].forEach((p) => benchBits.push(filledBenchSlot(p)));
    for (let i = bHave[pos].length; i < bNeed[pos]; i++) {
      benchBits.push(emptyBenchSlot(pos, lockedBench));
    }
  });

  document.getElementById('pitch-view').innerHTML = `
    ${xiRow('FWD')}
    ${xiRow('MID')}
    ${xiRow('DEF')}
    ${xiRow('GK')}
    <div class="w-full mt-1 pt-3 border-t border-white/10">
      <div class="text-[10px] font-label-caps ${lockedBench ? 'text-outline-variant' : 'text-primary'} mb-2 text-center tracking-wider">
        ${lockedBench ? 'BENCH · LOCKED UNTIL XI IS FULL' : 'BENCH · TAP + TO ADD'}
      </div>
      <div class="flex justify-center gap-3 flex-wrap">${benchBits.join('')}</div>
    </div>
  `;

  updateCaptainSelects();
}

function updateCaptainSelects() {
  const list = starters();
  const capSel = document.getElementById('captain-select');
  const viceSel = document.getElementById('vice-select');
  const capVal = capSel.value;
  const viceVal = viceSel.value;
  const opts = list.map((p) => `<option value="${p.id}">${p.name}</option>`).join('') || '<option value="">— Select —</option>';
  capSel.innerHTML = opts;
  viceSel.innerHTML = opts;
  if (capVal && list.some((p) => String(p.id) === String(capVal))) capSel.value = capVal;
  if (viceVal && list.some((p) => String(p.id) === String(viceVal))) viceSel.value = viceVal;
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

function scrollToPlayers() {
  const panel = document.getElementById('player-grid');
  if (panel && window.matchMedia('(max-width: 1023px)').matches) {
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

window.selectXiSlot = function (pos) {
  if (startersByPos()[pos].length >= formationSlots()[pos]) return;
  activeSlot = { kind: 'xi', pos };
  updatePosChips(pos);
  loadPlayers().then(() => {
    renderPlayerGrid(allPlayers);
  });
  setStatus('');
  renderPitch();
  scrollToPlayers();
};

window.selectBenchSlot = function (pos) {
  if (!xiComplete()) {
    setStatus('Finish your starting XI before picking the bench.', true);
    return;
  }
  if (benchByPos()[pos].length >= benchSlots()[pos]) return;
  activeSlot = { kind: 'bench', pos };
  updatePosChips(pos);
  loadPlayers().then(() => {
    renderPlayerGrid(allPlayers);
  });
  setStatus('');
  renderPitch();
  scrollToPlayers();
};

window.addPlayer = function (id) {
  const player = allPlayers.find((p) => p.id === id);
  if (!player) return;
  if (squad.some((p) => p.id === id)) return;
  if (squad.length >= SQUAD_SIZE) {
    setStatus('Squad is full (15 players).', true);
    return;
  }
  if (positionCount(player.position) >= POSITION_LIMITS[player.position]) {
    setStatus(`Maximum ${POSITION_LIMITS[player.position]} ${player.position} players.`, true);
    return;
  }
  const countryCount = squad.filter((p) => p.country_id === player.country_id).length;
  if (countryCount >= 3) {
    setStatus('Maximum 3 players from the same country.', true);
    return;
  }

  const phase = currentPhase();
  const pos = player.position;

  // If user focused a slot, honor that kind
  if (activeSlot) {
    if (activeSlot.pos !== pos) {
      setStatus(`That slot needs a ${activeSlot.pos}.`, true);
      return;
    }
    if (activeSlot.kind === 'xi') {
      if (startersByPos()[pos].length >= formationSlots()[pos]) {
        setStatus(`${formationKey} only starts ${formationSlots()[pos]} ${pos}.`, true);
        return;
      }
      squad.push({ ...player, is_starting: true, bench_order: null });
    } else {
      if (!xiComplete()) {
        setStatus('Finish your starting XI before picking the bench.', true);
        return;
      }
      if (benchByPos()[pos].length >= benchSlots()[pos]) {
        setStatus(`No bench slots left for ${pos}.`, true);
        return;
      }
      squad.push({ ...player, is_starting: false, bench_order: bench().length + 1 });
    }
  } else if (phase === 'xi') {
    if (startersByPos()[pos].length >= formationSlots()[pos]) {
      setStatus(
        `${formationKey} only starts ${formationSlots()[pos]} ${pos}. Fill other XI slots first — extras go on the bench after.`,
        true
      );
      return;
    }
    if (starters().length >= STARTING_XI) {
      setStatus('Starting XI is full. Add remaining players to the bench.', true);
      return;
    }
    squad.push({ ...player, is_starting: true, bench_order: null });
  } else {
    // Bench phase
    if (benchByPos()[pos].length >= benchSlots()[pos]) {
      setStatus(`No bench slots left for ${pos} in ${formationKey}.`, true);
      return;
    }
    if (bench().length >= BENCH_SIZE) {
      setStatus('Bench is full (4 players).', true);
      return;
    }
    squad.push({ ...player, is_starting: false, bench_order: bench().length + 1 });
  }

  reindexBench();

  // Clear active slot once that row/bench quota for the pos is filled
  if (activeSlot) {
    const filled =
      activeSlot.kind === 'xi'
        ? startersByPos()[activeSlot.pos].length >= formationSlots()[activeSlot.pos]
        : benchByPos()[activeSlot.pos].length >= benchSlots()[activeSlot.pos];
    if (filled) activeSlot = null;
  }

  setStatus('');
  refresh();
};

window.removePlayer = function (id) {
  const wasStarter = squad.find((p) => p.id === id)?.is_starting;
  squad = squad.filter((p) => p.id !== id);

  // If we broke the XI, anyone left on "bench" while XI incomplete must be cleared
  // (bench is locked until XI is done — orphans shouldn't linger)
  if (wasStarter && !xiComplete()) {
    const orphans = bench();
    if (orphans.length) {
      squad = squad.filter((p) => p.is_starting);
      setStatus('Starting XI changed — bench was cleared. Refill the XI, then the bench.', true);
    }
  }

  reindexBench();
  refresh();
};

function refresh() {
  updateBudget();
  renderPlayerGrid(allPlayers);
  renderPitch();
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
      const detected = detectFormationFromStarters();
      if (detected) {
        formationKey = detected;
      } else if (data.team.formation && FORMATIONS[data.team.formation]) {
        formationKey = data.team.formation;
      }
      // If saved XI doesn't match a formation, keep players but force into default by demoting overflow
      if (!detectFormationFromStarters()) {
        applyFormation(formationKey);
        return;
      }
      updateFormationPills();
      if (data.team.captain_id) document.getElementById('captain-select').value = data.team.captain_id;
      if (data.team.vice_captain_id) document.getElementById('vice-select').value = data.team.vice_captain_id;
      refresh();
    }
  } catch (_) { /* guest */ }
}

document.querySelectorAll('.formation-btn').forEach((btn) => {
  btn.addEventListener('click', () => applyFormation(btn.dataset.f));
});

document.getElementById('filter-apply').addEventListener('click', loadPlayers);
document.getElementById('filter-sort').addEventListener('change', loadPlayers);
document.getElementById('filter-country').addEventListener('change', loadPlayers);

document.querySelectorAll('.pos-chip').forEach((btn) => {
  btn.addEventListener('click', () => {
    const pos = btn.dataset.pos || '';
    activeSlot = pos
      ? { kind: currentPhase() === 'bench' ? 'bench' : 'xi', pos }
      : null;
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
  if (squad.length !== SQUAD_SIZE) {
    setStatus(`Squad must have exactly 15 players (have ${squad.length}).`, true);
    return;
  }
  if (!xiComplete()) {
    setStatus(`Complete your ${formationKey} starting XI first (${starters().length}/${STARTING_XI}).`, true);
    return;
  }
  if (bench().length !== BENCH_SIZE) {
    setStatus(`Add all 4 bench players (${bench().length}/${BENCH_SIZE}).`, true);
    return;
  }
  const captainId = parseInt(document.getElementById('captain-select').value, 10);
  const viceId = parseInt(document.getElementById('vice-select').value, 10);
  if (!captainId || !viceId) {
    setStatus('Select a captain and vice captain.', true);
    return;
  }
  if (captainId === viceId) {
    setStatus('Captain and vice captain must be different.', true);
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
      setStatus('Squad saved successfully!', false);
    } else {
      setStatus(data.message || (res.status === 401 ? 'Please log in first' : 'Save failed'), true);
    }
  } catch (_) {
    setStatus('Network error', true);
  }
});

updateFormationPills();
loadCountries();
loadPlayers();
loadExistingTeam();
refresh();
