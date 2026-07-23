async function loadBudgetInfo() {
    const el = document.getElementById('transfer-budget-info');
    const res = await fetch('/api/transfers/budget');
    const data = await res.json();
    if (!data.success) {
        el.innerHTML = 'Please <a class="text-primary underline" href="/login">login</a> to manage transfers.';
        return;
    }
    el.innerHTML = `
        <div class="flex flex-wrap gap-x-6 gap-y-1">
            <span>Remaining: <strong class="text-primary font-stat-md">$${data.budget_remaining.toFixed(1)}m</strong> / $${data.budget_limit}m</span>
            <span>Free transfers: <strong class="text-on-surface">${data.free_transfers_remaining}</strong> of ${data.free_transfers}</span>
            <span>Penalty: <strong class="text-danger">-${data.transfer_penalty}pts</strong></span>
            ${data.is_live_matchday ? '<span class="text-danger font-bold">Live MD — applies next</span>' : ''}
        </div>
    `;
    const hdr = document.getElementById('hdr-remaining');
    if (hdr) hdr.textContent = data.budget_remaining.toFixed(1);
}

async function loadSquadPlayers() {
    const res = await fetch('/api/team');
    const data = await res.json();
    if (!data.success) return;

    const outSelect = document.getElementById('player-out');
    outSelect.innerHTML = '<option value="">— Select player to remove —</option>';
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
    inSelect.innerHTML = '<option value="">— Select replacement —</option>';
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

    const rows = data.transfers || [];
    document.querySelector('#transfer-table tbody').innerHTML = rows.length
        ? rows.map(t => `
            <tr>
                <td>${t.player_out?.name || '—'}</td>
                <td>${t.player_in?.name || '—'}</td>
                <td style="text-align:center">MD${t.matchday}</td>
                <td style="text-align:center">${t.cost_in_points > 0 ? '-' + t.cost_in_points : 'Free'}</td>
                <td>${new Date(t.timestamp).toLocaleDateString()}</td>
            </tr>
        `).join('')
        : '<tr><td colspan="5" style="text-align:center;color:#9CA3AF;padding:40px">No transfers yet</td></tr>';
}

async function loadBoosters() {
    const res = await fetch('/api/boosters');
    const data = await res.json();
    if (!data.success) return;

    document.getElementById('boosters-list').innerHTML = data.boosters.map(b => `
        <div class="rounded-xl border ${b.used ? 'border-outline-variant opacity-70' : 'border-primary/40'} bg-surface-container-low p-4">
            <div class="flex items-start justify-between gap-3">
                <div>
                    <h4 class="font-headline-md text-lg text-on-surface">${b.type.replace(/_/g, ' ')}</h4>
                    <p class="font-body-sm text-body-sm text-on-surface-variant mt-1">${b.description || ''}</p>
                    <p class="font-label-caps text-label-caps mt-2 ${b.used ? 'text-on-surface-variant' : 'text-tertiary'}">
                        ${b.used ? `Used (MD${b.matchday_used})` : 'Available'}
                    </p>
                </div>
                ${!b.used ? `<button type="button" class="activate-booster flex-shrink-0 bg-primary-container text-on-primary-container font-label-caps text-label-caps px-3 py-2 rounded-lg hover:brightness-110" data-type="${b.type}">Activate</button>` : '<span class="material-symbols-outlined text-outline-variant">lock</span>'}
            </div>
        </div>
    `).join('') || '<p class="text-on-surface-variant font-body-sm">No boosters</p>';

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

    if (!inId) { msg.textContent = 'Select a player to transfer in'; msg.className = 'error-msg'; return; }

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
