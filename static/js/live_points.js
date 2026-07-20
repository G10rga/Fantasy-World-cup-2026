let pollInterval = null;

function renderPitchPlayer(player, points, multiplier, live = {}) {
    const multBadge = multiplier > 1 ? `<span class="mult-badge">${multiplier}x</span>` : '';
    const ptsBadge = `<span class="pts-badge">${points}pts</span>`;
    const mins = live.minutes_played > 0 ? `<span class="mins-badge">${live.minutes_played}'</span>` : '';
    const goals = live.goals > 0 ? `<span class="goals-badge">⚽${live.goals}</span>` : '';
    return `
        <div class="pitch-player">
            <span class="pos-badge ${player.position}">${player.position}</span>
            <span>${player.name}</span>
            ${mins} ${goals} ${multBadge} ${ptsBadge}
        </div>
    `;
}

async function loadTeam() {
    const res = await fetch('/api/team');
    const data = await res.json();
    if (!data.success) {
        document.querySelector('.my-team-layout').innerHTML =
            '<p>Please <a href="/login">login</a> to view your team.</p>';
        return;
    }
    return data.team;
}

async function refreshLivePoints() {
    const res = await fetch('/api/live/points');
    const data = await res.json();
    if (!data.success) return;

    document.getElementById('md-points').textContent = data.total_points;
    const liveBadge = document.getElementById('live-indicator');
    liveBadge.style.display = data.is_live ? 'inline-block' : 'none';

    const team = await loadTeam();
    if (!team) return;

    const pointsMap = {};
    data.players.forEach(p => { pointsMap[p.player_id] = p; });

    const starters = team.players.filter(p => p.is_starting);
    const bench = team.players.filter(p => !p.is_starting)
        .sort((a, b) => (a.bench_order || 99) - (b.bench_order || 99));

    const byPos = { GK: [], DEF: [], MID: [], FWD: [] };
    starters.forEach(ftp => {
        const pos = ftp.player?.position;
        if (pos) byPos[pos].push(ftp);
    });

    const pitchHtml = ['GK', 'DEF', 'MID', 'FWD'].map(pos => `
        <div class="pitch-row pitch-${pos.toLowerCase()}">
            ${(byPos[pos] || []).map(ftp => {
                const live = pointsMap[ftp.player_id] || {};
                return renderPitchPlayer(
                    ftp.player,
                    live.matchday_points || ftp.matchday_points || 0,
                    live.multiplier || ftp.multiplier || 1,
                    live
                );
            }).join('')}
        </div>
    `).join('');

    document.getElementById('team-pitch').innerHTML = pitchHtml;
    document.getElementById('team-bench').innerHTML = bench.length
        ? `<h4>Bench</h4>${bench.map(ftp => {
            const live = pointsMap[ftp.player_id] || {};
            return renderPitchPlayer(ftp.player, live.matchday_points || 0, 1, live);
        }).join('')}`
        : '';

    const capWidget = document.getElementById('captain-widget');
    const captain = team.players.find(p => p.player_id === team.captain_id);
    const vice = team.players.find(p => p.player_id === team.vice_captain_id);
    capWidget.innerHTML = `
        <p>Captain: <strong>${captain?.player?.name || '—'}</strong></p>
        <p>Vice: <strong>${vice?.player?.name || '—'}</strong></p>
        <button class="btn btn-sm" id="change-captain-btn">Change Captain</button>
    `;

    document.getElementById('live-points-list').innerHTML = data.players
        .filter(p => p.is_starting)
        .sort((a, b) => b.matchday_points - a.matchday_points)
        .map(p => {
            const extras = [];
            if (p.minutes_played > 0) extras.push(`${p.minutes_played}'`);
            if (p.goals > 0) extras.push(`${p.goals}G`);
            if (p.assists > 0) extras.push(`${p.assists}A`);
            const statStr = extras.length ? ` [${extras.join(', ')}]` : '';
            return `<li>${p.name} (${p.position}): ${p.matchday_points}pts${statStr} ${p.multiplier > 1 ? `(${p.multiplier}x)` : ''}</li>`;
        })
        .join('');
}

async function init() {
    await refreshLivePoints();
    pollInterval = setInterval(refreshLivePoints, 60000);
}

init();
