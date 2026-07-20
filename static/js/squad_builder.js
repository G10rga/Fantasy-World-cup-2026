const POSITION_LIMITS = { GK: 2, DEF: 5, MID: 5, FWD: 3 };
const SQUAD_SIZE = 15;
const STARTING_XI = 11;
const BUDGET = 100.0;

let squad = [];
let allPlayers = [];

function positionCount(pos) {
    return squad.filter(p => p.position === pos).length;
}

function squadCost() {
    return squad.reduce((sum, p) => sum + p.price, 0);
}

function updateBudget() {
    const remaining = BUDGET - squadCost();
    document.getElementById('budget-remaining').textContent = `$${remaining.toFixed(1)}m`;
    document.getElementById('squad-count').textContent = `${squad.length}/${SQUAD_SIZE}`;
    document.getElementById('budget-remaining').classList.toggle('over-budget', remaining < 0);
}

function renderPlayerCard(player) {
    const inSquad = squad.some(p => p.id === player.id);
    const scouting = player.scouting_bonus_eligible ? '<span class="badge scout">Scout</span>' : '';
    const avail = player.is_available
        ? `<span class="badge avail">${player.availability_status}</span>`
        : `<span class="badge unavail">${player.availability_status}</span>`;

    const formSpark = (player.form || []).map(v =>
        `<span class="spark-bar" style="height:${Math.max(v * 3, 2)}px" title="${v}pts"></span>`
    ).join('');

    return `
        <div class="player-card ${inSquad ? 'in-squad' : ''}" data-id="${player.id}">
            <img class="player-photo" src="${player.photo_url || '/static/img/placeholder.png'}"
                 alt="${player.name}" onerror="this.style.display='none'">
            ${player.country?.flag_url ? `<img class="flag" src="${player.country.flag_url}" alt="">` : ''}
            <span class="pos-badge ${player.position}">${player.position}</span>
            <h4>${player.name}</h4>
            <p class="price">$${player.price}m</p>
            <p class="pts">Total: ${player.total_pts} | MD: ${player.this_matchday_pts}</p>
            <p class="selected">${player.selected_by_pct}% selected</p>
            <div class="form-sparkline">${formSpark}</div>
            ${scouting} ${avail}
            <button class="btn btn-sm ${inSquad ? 'btn-remove' : 'btn-add'}"
                    onclick="${inSquad ? 'removePlayer' : 'addPlayer'}(${player.id})">
                ${inSquad ? 'Remove' : 'Add'}
            </button>
        </div>
    `;
}

function renderPlayerGrid(players) {
    document.getElementById('player-grid').innerHTML = players.map(renderPlayerCard).join('');
}

function renderPitch() {
    const starters = squad.filter(p => p.is_starting);
    const bench = squad.filter(p => !p.is_starting).sort((a, b) => a.bench_order - b.bench_order);

    const byPos = { GK: [], DEF: [], MID: [], FWD: [] };
    starters.forEach(p => byPos[p.position]?.push(p));

    const pitchHtml = ['GK', 'DEF', 'MID', 'FWD'].map(pos => `
        <div class="pitch-row pitch-${pos.toLowerCase()}">
            ${(byPos[pos] || []).map(p => pitchSlot(p)).join('')}
        </div>
    `).join('');

    document.getElementById('pitch-view').innerHTML = pitchHtml || '<p class="empty-pitch">Add players to build your squad</p>';
    document.getElementById('bench-view').innerHTML = bench.length
        ? `<h4>Bench</h4>${bench.map(p => pitchSlot(p, true)).join('')}`
        : '';

    updateCaptainSelects();
}

function pitchSlot(player, isBench = false) {
    return `
        <div class="pitch-player" data-id="${player.id}">
            <span class="pos-badge ${player.position}">${player.position}</span>
            <span>${player.name}</span>
            <span class="price">$${player.price}m</span>
            ${!isBench ? `<button class="btn-xs" onclick="toggleStarting(${player.id}, false)">To Bench</button>` : ''}
            ${isBench ? `<button class="btn-xs" onclick="toggleStarting(${player.id}, true)">To XI</button>` : ''}
        </div>
    `;
}

function updateCaptainSelects() {
    const starters = squad.filter(p => p.is_starting);
    const capSel = document.getElementById('captain-select');
    const viceSel = document.getElementById('vice-select');
    const capVal = capSel.value;
    const viceVal = viceSel.value;

    capSel.innerHTML = starters.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
    viceSel.innerHTML = starters.map(p => `<option value="${p.id}">${p.name}</option>`).join('');

    if (capVal) capSel.value = capVal;
    if (viceVal) viceSel.value = viceVal;
}

window.addPlayer = function(id) {
    const player = allPlayers.find(p => p.id === id);
    if (!player) return;
    if (squad.length >= SQUAD_SIZE) { alert('Squad is full (15 players)'); return; }
    if (positionCount(player.position) >= POSITION_LIMITS[player.position]) {
        alert(`Maximum ${POSITION_LIMITS[player.position]} ${player.position} players`);
        return;
    }
    const countryCount = squad.filter(p => p.country_id === player.country_id).length;
    if (countryCount >= 3) { alert('Maximum 3 players from same country'); return; }

    const isStarting = squad.filter(p => p.is_starting).length < STARTING_XI;
    squad.push({
        ...player,
        is_starting: isStarting,
        bench_order: isStarting ? null : squad.filter(p => !p.is_starting).length + 1,
    });
    refresh();
};

window.removePlayer = function(id) {
    squad = squad.filter(p => p.id !== id);
    reindexBench();
    refresh();
};

window.toggleStarting = function(id, toStarting) {
    const player = squad.find(p => p.id === id);
    if (!player) return;

    if (toStarting) {
        if (squad.filter(p => p.is_starting).length >= STARTING_XI) {
            alert('Starting XI is full'); return;
        }
        player.is_starting = true;
        player.bench_order = null;
    } else {
        player.is_starting = false;
        player.bench_order = squad.filter(p => !p.is_starting).length + 1;
    }
    reindexBench();
    refresh();
};

function reindexBench() {
    squad.filter(p => !p.is_starting)
        .sort((a, b) => (a.bench_order || 99) - (b.bench_order || 99))
        .forEach((p, i) => { p.bench_order = i + 1; });
}

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
        data.countries.forEach(c => {
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
            squad = data.team.players.map(ftp => ({
                ...ftp.player,
                is_starting: ftp.is_starting,
                bench_order: ftp.bench_order,
            }));
            if (data.team.captain_id) {
                document.getElementById('captain-select').value = data.team.captain_id;
            }
            if (data.team.vice_captain_id) {
                document.getElementById('vice-select').value = data.team.vice_captain_id;
            }
            refresh();
        }
    } catch (e) { /* not logged in */ }
}

document.getElementById('filter-apply').addEventListener('click', loadPlayers);

document.getElementById('save-squad').addEventListener('click', async () => {
    if (squad.length !== SQUAD_SIZE) {
        document.getElementById('save-msg').textContent = 'Squad must have exactly 15 players';
        return;
    }
    const payload = {
        squad: squad.map(p => ({
            player_id: p.id,
            is_starting: p.is_starting,
            bench_order: p.bench_order,
        })),
        captain_id: parseInt(document.getElementById('captain-select').value),
        vice_captain_id: parseInt(document.getElementById('vice-select').value),
    };
    const res = await fetch('/api/team/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    const data = await res.json();
    const msg = document.getElementById('save-msg');
    if (data.success) {
        msg.textContent = 'Squad saved successfully!';
        msg.className = 'success-msg';
    } else {
        msg.textContent = data.message;
        msg.className = 'error-msg';
    }
});

loadCountries();
loadPlayers();
loadExistingTeam();
