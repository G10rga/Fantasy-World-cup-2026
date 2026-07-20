async function loadBudgetInfo() {
    const res = await fetch('/api/transfers/budget');
    const data = await res.json();
    if (!data.success) {
        document.getElementById('transfer-budget-info').innerHTML =
            '<p>Please <a href="/login">login</a> to manage transfers.</p>';
        return;
    }
    document.getElementById('transfer-budget-info').innerHTML = `
        <p>Budget: $${data.budget_remaining.toFixed(1)}m remaining (limit: $${data.budget_limit}m)</p>
        <p>Free transfers: ${data.free_transfers_remaining} of ${data.free_transfers}
           | Used: ${data.transfers_used} | Penalty: -${data.transfer_penalty}pts per extra</p>
        ${data.is_live_matchday ? '<p class="warning">Live matchday — transfers apply to next matchday</p>' : ''}
    `;
}

async function loadSquadPlayers() {
    const res = await fetch('/api/team');
    const data = await res.json();
    if (!data.success) return;

    const outSelect = document.getElementById('player-out');
    outSelect.innerHTML = '<option value="">-- Select --</option>';
    data.team.players.forEach(ftp => {
        const opt = document.createElement('option');
        opt.value = ftp.player_id;
        opt.textContent = `${ftp.player.name} (${ftp.player.position}) — $${ftp.player.price}m`;
        outSelect.appendChild(opt);
    });
}

async function loadAllPlayers() {
    const res = await fetch('/api/players?sort_by=price');
    const data = await res.json();
    if (!data.success) return;

    const inSelect = document.getElementById('player-in');
    inSelect.innerHTML = '<option value="">-- Select --</option>';
    data.players.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = `${p.name} (${p.position}) — $${p.price}m — ${p.total_pts}pts`;
        inSelect.appendChild(opt);
    });
}

async function loadTransferHistory() {
    const res = await fetch('/api/transfers');
    const data = await res.json();
    if (!data.success) return;

    document.querySelector('#transfer-table tbody').innerHTML = data.transfers.map(t => `
        <tr>
            <td>${t.player_out?.name || '—'}</td>
            <td>${t.player_in?.name || '—'}</td>
            <td>MD${t.matchday}</td>
            <td>${t.cost_in_points > 0 ? '-' + t.cost_in_points : 'Free'}</td>
            <td>${new Date(t.timestamp).toLocaleDateString()}</td>
        </tr>
    `).join('');
}

async function loadBoosters() {
    const res = await fetch('/api/boosters');
    const data = await res.json();
    if (!data.success) return;

    document.getElementById('boosters-list').innerHTML = data.boosters.map(b => `
        <div class="booster-card ${b.used ? 'used' : 'available'}">
            <h4>${b.type}</h4>
            <p>${b.description}</p>
            <p>Status: ${b.used ? `Used (MD${b.matchday_used})` : 'Available'}</p>
            ${!b.used ? `<button class="btn btn-sm activate-booster" data-type="${b.type}">Activate</button>` : ''}
        </div>
    `).join('');

    document.querySelectorAll('.activate-booster').forEach(btn => {
        btn.addEventListener('click', async () => {
            const type = btn.dataset.type;
            let extra_data = null;
            if (type === '12TH_MAN') {
                const playerId = prompt('Enter player ID for 12th Man:');
                if (!playerId) return;
                extra_data = { player_id: parseInt(playerId) };
            }
            const res = await fetch('/api/boosters/activate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type, extra_data }),
            });
            const result = await res.json();
            if (result.success) {
                loadBoosters();
            } else {
                alert(result.message);
            }
        });
    });
}

document.getElementById('confirm-transfer').addEventListener('click', async () => {
    const outId = document.getElementById('player-out').value;
    const inId = document.getElementById('player-in').value;
    const msg = document.getElementById('transfer-msg');

    if (!inId) { msg.textContent = 'Select a player to transfer in'; return; }

    const res = await fetch('/api/transfers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            player_out_id: outId ? parseInt(outId) : null,
            player_in_id: parseInt(inId),
        }),
    });
    const data = await res.json();
    if (data.success) {
        msg.textContent = 'Transfer completed!';
        msg.className = 'success-msg';
        loadBudgetInfo();
        loadSquadPlayers();
        loadTransferHistory();
    } else {
        msg.textContent = data.message;
        msg.className = 'error-msg';
    }
});

loadBudgetInfo();
loadSquadPlayers();
loadAllPlayers();
loadTransferHistory();
loadBoosters();
