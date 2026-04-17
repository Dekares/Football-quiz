// Multiplayer istemcisi — Socket.IO + lobby/game/gameover ekranları.

const multiState = {
    socket: null,
    code: null,
    playerId: null,
    playerToken: null,
    lobby: null,          // son lobby_state
    round: null,          // aktif tur verisi (round_start payload + client flags)
    roundEndsAt: null,
    timerHandle: null,
    ending: null,         // son round_end verisi (sonuç ekranı için)
    gameOver: null,       // son game_over verisi
    picked: null,         // MC modunda seçilen player_id
    answered: false,
    connected: false,
};

function getSocket() {
    if (multiState.socket) return multiState.socket;
    // io global'i socket.io client CDN'den gelir
    const s = io({ transports: ['websocket', 'polling'] });
    multiState.socket = s;
    wireSocketEvents(s);
    return s;
}

function wireSocketEvents(s) {
    s.on('connect', () => {
        multiState.connected = true;
        // Sayfaya dönüldüyse rejoin dene
        const savedCode = localStorage.getItem('mp_code');
        const savedToken = localStorage.getItem('mp_token');
        if (savedCode && savedToken && !multiState.playerId) {
            s.emit('rejoin', { lobby_code: savedCode, player_token: savedToken });
        }
    });
    s.on('disconnect', () => { multiState.connected = false; });

    s.on('lobby_created', (data) => {
        multiState.code = data.lobby_code;
        multiState.playerId = data.player_id;
        multiState.playerToken = data.player_token;
        multiState.lobby = data.state;
        localStorage.setItem('mp_code', data.lobby_code);
        localStorage.setItem('mp_token', data.player_token);
        navigate(`#/lobby/${data.lobby_code}`);
    });

    s.on('joined_lobby', (data) => {
        multiState.code = data.lobby_code;
        multiState.playerId = data.player_id;
        multiState.playerToken = data.player_token;
        multiState.lobby = data.state;
        localStorage.setItem('mp_code', data.lobby_code);
        localStorage.setItem('mp_token', data.player_token);
        navigate(`#/lobby/${data.lobby_code}`);
    });

    s.on('rejoined', (data) => {
        multiState.code = data.lobby_code;
        multiState.playerId = data.player_id;
        multiState.lobby = data.state;
        const phase = data.state.phase;
        if (phase === 'IN_ROUND' || phase === 'ROUND_RESULT') navigate(`#/game/${data.lobby_code}`);
        else if (phase === 'GAME_OVER') navigate(`#/gameover/${data.lobby_code}`);
        else navigate(`#/lobby/${data.lobby_code}`);
    });

    s.on('lobby_state', (state) => {
        multiState.lobby = state;
        renderCurrentView();
    });

    s.on('settings_updated', (data) => {
        if (multiState.lobby) multiState.lobby.settings = data.settings;
        renderCurrentView();
    });

    s.on('player_joined', () => { /* lobby_state takip ediyor */ });
    s.on('player_left', () => { /* lobby_state takip ediyor */ });
    s.on('player_disconnected', () => { /* lobby_state takip ediyor */ });

    s.on('round_start', (data) => {
        multiState.round = data;
        multiState.roundEndsAt = data.ends_at;
        multiState.picked = null;
        multiState.answered = false;
        multiState.ending = null;
        navigate(`#/game/${multiState.code}`);
        startRoundTimer();
    });

    s.on('answer_result', (data) => {
        multiState.answered = true;
        if (multiState.lobby) {
            const me = multiState.lobby.players.find(p => p.player_id === multiState.playerId);
            if (me) me.score = data.total_score;
        }
        renderGameView(data);
    });

    s.on('player_answered', () => { /* subtle bildirim (ops.) */ });

    s.on('round_end', (data) => {
        multiState.ending = data;
        stopRoundTimer();
        // Skorları güncelle
        if (multiState.lobby) {
            multiState.lobby.players.forEach(p => {
                if (data.scores[p.player_id] !== undefined) p.score = data.scores[p.player_id];
            });
        }
        renderGameView();
    });

    s.on('game_over', (data) => {
        multiState.gameOver = data;
        stopRoundTimer();
        navigate(`#/gameover/${multiState.code}`);
        // 8 sn sonra herkesi lobi girişine geri gönder
        setTimeout(() => {
            if (location.hash.startsWith('#/gameover/')) {
                getSocket().emit('leave_lobby');
                clearSession();
                navigate('#/multi');
            }
        }, 8000);
    });

    s.on('kicked', () => {
        clearSession();
        alert('Lobiden çıkarıldın.');
        navigate('#/');
    });

    s.on('error', (err) => {
        alert(`${err.code}: ${err.message}`);
    });
}

function clearSession() {
    localStorage.removeItem('mp_code');
    localStorage.removeItem('mp_token');
    multiState.code = null;
    multiState.playerId = null;
    multiState.playerToken = null;
    multiState.lobby = null;
    multiState.round = null;
    multiState.ending = null;
    multiState.gameOver = null;
    multiState.picked = null;
    multiState.answered = false;
}

// ===== Router entegrasyonu =====
onRoute((route) => {
    if (route.name === 'multi') renderMultiEntry();
    else if (route.name === 'lobby') { ensureCode(route.params.code); renderLobbyView(); }
    else if (route.name === 'game')  { ensureCode(route.params.code); renderGameView(); }
    else if (route.name === 'gameover') { ensureCode(route.params.code); renderGameOverView(); }
});

function ensureCode(code) {
    if (!multiState.code) multiState.code = code;
}

function renderCurrentView() {
    const route = location.hash;
    if (route.startsWith('#/lobby/')) renderLobbyView();
    else if (route.startsWith('#/game/')) renderGameView();
    else if (route.startsWith('#/gameover/')) renderGameOverView();
}

// ===== Multi giriş ekranı (chooser → create / join) =====
let multiEntryView = 'chooser'; // 'chooser' | 'create' | 'join'

function renderMultiEntry() {
    multiEntryView = 'chooser';
    paintMultiEntry();
}

function paintMultiEntry() {
    const entry = document.getElementById('multi-entry');
    if (!entry) return;
    if (multiEntryView === 'create') return paintCreateForm(entry);
    if (multiEntryView === 'join')   return paintJoinForm(entry);
    paintChooser(entry);
}

function paintChooser(entry) {
    entry.innerHTML = `
        <div class="main-menu">
            <a class="menu-card" onclick="showMultiCreate()">
                <div class="menu-icon">&#10010;</div>
                <div class="menu-body">
                    <div class="menu-title">${t('multi_create')}</div>
                    <div class="menu-desc">${t('multi_create_desc')}</div>
                </div>
                <div class="menu-arrow">&rsaquo;</div>
            </a>
            <a class="menu-card" onclick="showMultiJoin()">
                <div class="menu-icon">&#128273;</div>
                <div class="menu-body">
                    <div class="menu-title">${t('multi_join')}</div>
                    <div class="menu-desc">${t('multi_join_desc')}</div>
                </div>
                <div class="menu-arrow">&rsaquo;</div>
            </a>
        </div>
    `;
    applyLang();
}

function paintCreateForm(entry) {
    const savedNick = localStorage.getItem('mp_nick') || '';
    entry.innerHTML = `
        <a class="back-link" onclick="showMultiChooser()">&larr; ${t('multi_back')}</a>
        <h2 style="margin-bottom:0.4rem">${t('multi_create')}</h2>
        <p class="subtitle" style="margin-bottom:1rem">${t('multi_create_hint')}</p>

        <div class="settings-panel">
            <div class="form-row">
                <label class="form-label">${t('multi_nickname')}</label>
                <input type="text" id="mp-nick" class="form-input" maxlength="16" value="${esc(savedNick)}" placeholder="${esc(t('multi_nickname_ph'))}">
            </div>
            <div class="form-row">
                <label class="form-label">${t('multi_target')}</label>
                <input type="number" id="mp-target" class="form-input" min="3" max="50" value="7">
                <div class="form-hint">${t('multi_target_hint')}</div>
            </div>
            <div class="form-row">
                <label class="form-label">${t('multi_difficulty')}</label>
                <div class="options" id="mp-diff-opts">
                    ${['easy','medium','hard'].map(d => `<button data-val="${d}" class="${d==='medium'?'active':''}" onclick="pickOpt('mp-diff-opts',this)">${t(d)}</button>`).join('')}
                </div>
            </div>
            <div class="form-row">
                <label class="form-label">${t('multi_mode')}</label>
                <div class="options" id="mp-mode-opts">
                    <button data-val="mc" class="active" onclick="pickOpt('mp-mode-opts',this)">${t('multi_mode_mc')}</button>
                    <button data-val="free" onclick="pickOpt('mp-mode-opts',this)">${t('multi_mode_free')}</button>
                </div>
            </div>
        </div>

        <button class="btn btn-primary" onclick="createLobby()">${t('multi_create')}</button>
    `;
    applyLang();
}

function paintJoinForm(entry) {
    const savedNick = localStorage.getItem('mp_nick') || '';
    entry.innerHTML = `
        <a class="back-link" onclick="showMultiChooser()">&larr; ${t('multi_back')}</a>
        <h2 style="margin-bottom:0.4rem">${t('multi_join')}</h2>
        <p class="subtitle" style="margin-bottom:1rem">${t('multi_join_hint')}</p>

        <div class="settings-panel">
            <div class="form-row">
                <label class="form-label">${t('multi_nickname')}</label>
                <input type="text" id="mp-nick" class="form-input" maxlength="16" value="${esc(savedNick)}" placeholder="${esc(t('multi_nickname_ph'))}">
            </div>
            <div class="form-row">
                <label class="form-label">${t('multi_code')}</label>
                <input type="text" id="mp-code" class="form-input form-code" maxlength="6" placeholder="${esc(t('multi_code_ph'))}">
            </div>
        </div>

        <button class="btn btn-primary" onclick="joinLobby()">${t('multi_join')}</button>
    `;
    applyLang();
    // Kod input'unda otomatik uppercase
    const codeInput = document.getElementById('mp-code');
    if (codeInput) {
        codeInput.addEventListener('input', () => {
            codeInput.value = codeInput.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
        });
    }
}

function showMultiChooser() { multiEntryView = 'chooser'; paintMultiEntry(); }
function showMultiCreate()  { multiEntryView = 'create';  paintMultiEntry(); }
function showMultiJoin()    { multiEntryView = 'join';    paintMultiEntry(); }

function pickOpt(groupId, btn) {
    const group = document.getElementById(groupId);
    if (!group) return;
    group.querySelectorAll('button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
}

function readPickedOpt(groupId, fallback) {
    const active = document.querySelector(`#${groupId} button.active`);
    return active?.dataset.val ?? fallback;
}

function createLobby() {
    const nick = (document.getElementById('mp-nick')?.value || '').trim();
    if (!nick) { alert(t('multi_nickname_ph')); return; }
    const target = parseInt(document.getElementById('mp-target')?.value, 10) || 7;
    const difficulty = readPickedOpt('mp-diff-opts', 'medium');
    const mode = readPickedOpt('mp-mode-opts', 'mc');
    localStorage.setItem('mp_nick', nick);
    getSocket().emit('create_lobby', {
        nickname: nick,
        settings: { mode, difficulty, target_score: target },
    });
}

function joinLobby() {
    const nick = (document.getElementById('mp-nick')?.value || '').trim();
    const code = (document.getElementById('mp-code')?.value || '').trim().toUpperCase();
    if (!nick) { alert(t('multi_nickname_ph')); return; }
    if (!code) { alert(t('multi_code_ph')); return; }
    localStorage.setItem('mp_nick', nick);
    getSocket().emit('join_lobby', { lobby_code: code, nickname: nick });
}

// ===== Lobby bekleme odası =====
function renderLobbyView() {
    const root = document.getElementById('lobby-view');
    if (!root) return;
    const lb = multiState.lobby;
    if (!lb) {
        root.innerHTML = `<div class="loading"><div class="spinner"></div><div>${t('multi_connecting') || 'Bağlanıyor...'}</div></div>`;
        getSocket();
        return;
    }

    const isHost = lb.host_id === multiState.playerId;
    const settings = lb.settings;

    const modeOpts = ['mc', 'free'].map(m => `
        <button data-active="${settings.mode === m}" class="${settings.mode === m ? 'active' : ''}"
                onclick="changeSetting('mode','${m}')" ${isHost ? '' : 'disabled'}>
            ${m === 'mc' ? t('multi_mode_mc') : t('multi_mode_free')}
        </button>`).join('');

    const diffOpts = ['easy', 'medium', 'hard'].map(d => `
        <button class="${settings.difficulty === d ? 'active' : ''}"
                onclick="changeSetting('difficulty','${d}')" ${isHost ? '' : 'disabled'}>
            ${t(d)}
        </button>`).join('');

    const targetInput = isHost
        ? `<input type="number" id="lobby-target" min="3" max="50" value="${settings.target_score}" class="form-input form-target" onchange="changeSetting('target_score', parseInt(this.value,10))">`
        : `<span style="font-weight:700;color:var(--gold);font-size:1.1rem">${settings.target_score}</span>`;

    const playersHtml = lb.players.map(p => {
        const isYou = p.player_id === multiState.playerId;
        const isH = p.player_id === lb.host_id;
        const classes = ['player-tile'];
        if (isYou) classes.push('you');
        if (isH) classes.push('host');
        if (!p.connected) classes.push('offline');
        const kickBtn = (isHost && !isYou && !isH)
            ? `<button class="btn btn-secondary" style="padding:0.2rem 0.5rem;font-size:0.75rem" onclick="kickPlayer('${p.player_id}')">×</button>`
            : '';
        return `<div class="${classes.join(' ')}">
            <div class="avatar">${esc(avatarLetter(p.nickname))}</div>
            <span class="nick">${esc(p.nickname)}</span>
            ${kickBtn}
        </div>`;
    }).join('');

    const canStart = lb.players.filter(p => p.connected).length >= 2;

    root.innerHTML = `
        <div class="lobby-code-display">
            <div class="label" data-i18n="multi_lobby_code">Lobi kodu</div>
            <div class="code" onclick="copyCode('${lb.code}')">${lb.code}</div>
            <div class="hint" data-i18n="multi_lobby_hint">Arkadaşlarına bu kodu gönder</div>
        </div>

        <div class="players-grid">${playersHtml}</div>

        <div class="settings-panel">
            <div class="row">
                <span class="label" data-i18n="multi_mode">Cevap modu</span>
                <div class="options">${modeOpts}</div>
            </div>
            <div class="row">
                <span class="label" data-i18n="multi_difficulty">Zorluk</span>
                <div class="options">${diffOpts}</div>
            </div>
            <div class="row">
                <span class="label" data-i18n="multi_target">Hedef puan</span>
                <div class="options">${targetInput}</div>
            </div>
        </div>

        ${isHost
            ? `<button class="btn btn-primary" ${canStart ? '' : 'disabled'} onclick="startGame()">${t('multi_start')}</button>
               ${!canStart ? `<p class="subtitle" style="text-align:center;margin-top:0.5rem">${t('multi_min_players')}</p>` : ''}`
            : `<p class="subtitle" style="text-align:center">${t('multi_waiting')}</p>`
        }
        <button class="btn btn-secondary" onclick="leaveLobby()" style="margin-top:0.8rem">${t('multi_leave')}</button>
    `;
    applyLang();
}

function changeSetting(key, val) {
    const lb = multiState.lobby;
    if (!lb) return;
    const newSettings = { ...lb.settings, [key]: val };
    getSocket().emit('update_settings', newSettings);
}

function startGame() {
    getSocket().emit('start_game');
}

function kickPlayer(pid) {
    if (!confirm('Oyuncu lobiden çıkarılsın mı?')) return;
    getSocket().emit('kick_player', { player_id: pid });
}

function leaveLobby() {
    getSocket().emit('leave_lobby');
    clearSession();
    navigate('#/multi');
}

function copyCode(code) {
    navigator.clipboard?.writeText(code).then(() => {
        // ops: toast
    });
}

// ===== Game (aktif tur) =====
function renderGameView(answerResult) {
    const root = document.getElementById('game-view');
    if (!root) return;
    const lb = multiState.lobby;
    const rnd = multiState.round;
    const end = multiState.ending;

    if (!lb || !rnd) {
        root.innerHTML = `<div class="loading"><div class="spinner"></div><div>${t('multi_connecting') || 'Bağlanıyor...'}</div></div>`;
        return;
    }

    const scoreChips = [...lb.players]
        .sort((a, b) => b.score - a.score)
        .map((p, i) => {
            const cls = ['score-chip'];
            if (p.player_id === multiState.playerId) cls.push('you');
            if (i === 0 && p.score > 0) cls.push('leader');
            return `<div class="${cls.join(' ')}"><span class="sc-nick">${esc(p.nickname)}</span><span class="sc-pts">${p.score}</span></div>`;
        }).join('');

    const timerHtml = end
        ? ''
        : `<div class="round-timer" id="round-timer">—</div>`;

    const teamsHtml = `
        <div class="results-header">
            <div class="club-badge"><img src="${rnd.club1.logo_url || ''}" onerror="this.style.display='none'" alt=""><span>${esc(rnd.club1.name)}</span></div>
            <span class="vs">&amp;</span>
            <div class="club-badge"><img src="${rnd.club2.logo_url || ''}" onerror="this.style.display='none'" alt=""><span>${esc(rnd.club2.name)}</span></div>
        </div>`;

    let body = '';
    if (end) {
        // Round sonuç ekranı
        if (rnd.mode === 'free') {
            body = renderFreeRoundResult(end);
        } else {
            const ans = end.correct_answer;
            body = `
                <div class="quiz-result correct" style="position:relative;transform:none">
                    <img class="player-photo" src="${ans.image_url || ''}" onerror="this.style.display='none'" alt="">
                    <div class="answer-name">${esc(ans.name)}</div>
                    <div class="answer-meta">
                        <span class="meta-pill">${esc(posText(ans.position))}</span>
                        <span class="meta-pill">${esc(ans.country || '?')}</span>
                    </div>
                    <div style="margin-top:0.8rem;font-size:0.9rem;color:var(--text-dim)">${t('multi_round_result')}</div>
                </div>`;
        }
    } else if (rnd.mode === 'mc') {
        const choices = rnd.choices || [];
        const cells = choices.map(c => {
            const disabled = multiState.answered ? 'disabled' : '';
            const picked = multiState.picked === c.player_id ? 'picked' : '';
            return `<button class="choice-btn ${picked}" ${disabled} onclick="pickChoice('${c.player_id}')">
                <img src="${c.image_url || ''}" onerror="this.style.display='none'" alt="">
                <span class="ch-name">${esc(c.name)}</span>
            </button>`;
        }).join('');
        body = `<div class="choice-grid">${cells}</div>`;
        if (multiState.answered) {
            const cls = answerResult?.correct === true ? '' : 'wrong';
            body += `<div class="answered-state ${cls}">${t('multi_already_answered')}</div>`;
        }
    } else {
        // free mode — canlı arama dropdown'u (solo tahmin oyunundaki gibi)
        body = `
            <div class="quiz-input-row" style="margin-top:1rem">
                <div class="search-wrapper quiz-search-wrapper">
                    <input type="text" id="mp-free-answer" autocomplete="off"
                        placeholder="${esc(t('guess_placeholder'))}"
                        ${multiState.answered ? 'disabled' : ''}>
                    <div class="dropdown" id="mp-free-dropdown"></div>
                </div>
                <button class="btn btn-primary" ${multiState.answered ? 'disabled' : ''} onclick="submitFreeAnswer()">${t('guess_btn')}</button>
            </div>`;
        if (multiState.answered) {
            const cls = answerResult?.correct === true ? '' : 'wrong';
            body += `<div class="answered-state ${cls}">${t('multi_already_answered')}</div>`;
        }
    }

    root.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.6rem;flex-wrap:wrap;gap:0.6rem">
            <div style="font-size:0.85rem;color:var(--text-dim)">${t('multi_round')} ${rnd.round_no}</div>
            <button class="btn btn-secondary" style="padding:0.3rem 0.7rem;font-size:0.8rem" onclick="leaveLobby()">${t('multi_leave')}</button>
        </div>
        ${timerHtml}
        <div class="scoreboard">${scoreChips}</div>
        ${teamsHtml}
        ${body}
    `;

    applyLang();
    if (!end) {
        startRoundTimer();
        if (rnd.mode === 'free') setupFreeSearch();
    }
}

// Serbest yazma için canlı arama (solo tahmin oyunundaki gibi)
let mpFreeDebounce = null;
function setupFreeSearch() {
    const input = document.getElementById('mp-free-answer');
    const dropdown = document.getElementById('mp-free-dropdown');
    if (!input || !dropdown) return;
    if (multiState.answered) return;
    input.focus();

    input.addEventListener('input', () => {
        clearTimeout(mpFreeDebounce);
        multiState.picked = null; // yeni yazımla seçim sıfırlanır
        const q = input.value.trim();
        if (q.length < 2) { dropdown.classList.remove('show'); return; }

        mpFreeDebounce = setTimeout(async () => {
            try {
                const res = await fetch('/api/search-player?q=' + encodeURIComponent(q));
                const players = await res.json();
                if (!players.length) {
                    dropdown.innerHTML = `<div style="padding:0.8rem;color:var(--text-dim)">${t('no_player')}</div>`;
                } else {
                    dropdown.innerHTML = players.map(p => `
                        <div class="dropdown-player" data-id="${p.player_id}" data-name="${esc(p.name)}">
                            <img src="${p.image_url || ''}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><rect fill=%22%23242734%22 width=%2240%22 height=%2240%22/><text x=%2220%22 y=%2224%22 text-anchor=%22middle%22 fill=%22%238b8fa3%22 font-size=%2216%22>?</text></svg>'" alt="">
                            <div class="dp-info">
                                <div class="dp-name">${esc(p.name)}</div>
                                <div class="dp-meta">${posText(p.position)} · ${esc(p.country || '')}</div>
                            </div>
                        </div>
                    `).join('');
                }
                dropdown.classList.add('show');
                dropdown.querySelectorAll('.dropdown-player').forEach(item => {
                    item.addEventListener('click', () => {
                        input.value = item.dataset.name;
                        multiState.picked = item.dataset.name; // anında submit için
                        dropdown.classList.remove('show');
                        submitFreeAnswer();
                    });
                });
            } catch (_) { /* sessiz */ }
        }, 250);
    });

    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submitFreeAnswer(); });
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.quiz-search-wrapper')) dropdown.classList.remove('show');
    }, { once: true });
}

function renderFreeRoundResult(end) {
    const me = end.player_results?.[multiState.playerId];
    let headline, sub, cls;
    if (!me || !me.answered) {
        cls = 'wrong';
        headline = t('multi_free_no_answer');
        sub = t('multi_free_no_answer_hint');
    } else if (me.correct) {
        cls = 'correct';
        headline = t('multi_free_correct');
        sub = me.answer_text ? esc(me.answer_text) : '';
    } else {
        cls = 'wrong';
        headline = t('multi_free_wrong');
        sub = me.answer_text ? `"${esc(me.answer_text)}"` : '';
    }
    const correctCount = (end.correct_player_ids || []).length;
    const totalCount = Object.keys(end.player_results || {}).length;
    return `
        <div class="quiz-result ${cls}" style="position:relative;transform:none;text-align:center">
            <div class="verdict" style="font-size:1.4rem;margin-bottom:0.4rem">${headline}</div>
            ${sub ? `<div class="answer-name" style="font-size:1.05rem">${sub}</div>` : ''}
            <div style="margin-top:0.8rem;font-size:0.85rem;color:var(--text-dim)">
                ${correctCount}/${totalCount} ${t('multi_free_correct_count')}
            </div>
        </div>`;
}

function pickChoice(playerId) {
    if (multiState.answered) return;
    const idNum = parseInt(playerId, 10);
    multiState.picked = idNum;
    getSocket().emit('submit_answer', { round_no: multiState.round.round_no, player_id: idNum });
    renderGameView();
}

function submitFreeAnswer() {
    if (multiState.answered) return;
    const input = document.getElementById('mp-free-answer');
    const dropdown = document.getElementById('mp-free-dropdown');
    const text = (input?.value || '').trim();
    if (!text) return;
    dropdown?.classList.remove('show');
    multiState.picked = text;
    getSocket().emit('submit_answer', { round_no: multiState.round.round_no, text });
}

// ===== Timer =====
function startRoundTimer() {
    stopRoundTimer();
    const tick = () => {
        const el = document.getElementById('round-timer');
        if (!el) { stopRoundTimer(); return; }
        const remaining = Math.max(0, Math.ceil((multiState.roundEndsAt || 0) * 1000 - Date.now()) / 1000);
        el.textContent = Math.ceil(remaining);
        el.classList.toggle('urgent', remaining <= 5);
        if (remaining <= 0) stopRoundTimer();
    };
    tick();
    multiState.timerHandle = setInterval(tick, 250);
}
function stopRoundTimer() {
    if (multiState.timerHandle) { clearInterval(multiState.timerHandle); multiState.timerHandle = null; }
}

// ===== Game over =====
function renderGameOverView() {
    const root = document.getElementById('gameover-view');
    if (!root) return;
    const lb = multiState.lobby;
    const go = multiState.gameOver;
    if (!lb || !go) {
        root.innerHTML = `<div class="loading"><div class="spinner"></div><div>${t('multi_connecting')}</div></div>`;
        return;
    }
    const sorted = [...lb.players].sort((a, b) => (go.final_scores[b.player_id] || 0) - (go.final_scores[a.player_id] || 0));
    const rows = sorted.map((p) => {
        const isYou = p.player_id === multiState.playerId;
        const isWinner = p.player_id === go.winner.player_id;
        const cls = ['player-tile'];
        if (isYou) cls.push('you');
        return `<div class="${cls.join(' ')}" style="${isWinner ? 'border-color:var(--gold);box-shadow:0 0 0 1px var(--gold)' : ''}">
            <div class="avatar">${esc(avatarLetter(p.nickname))}</div>
            <span class="nick">${esc(p.nickname)}</span>
            <span class="sc-pts" style="color:var(--gold);font-weight:800">${go.final_scores[p.player_id] || 0}</span>
        </div>`;
    }).join('');

    root.innerHTML = `
        <h1 style="text-align:center">${t('multi_game_over')}</h1>
        <div class="quiz-result correct" style="position:relative;transform:none;margin:1rem auto">
            <div class="verdict">${t('multi_winner')}</div>
            <div class="answer-name">${esc(go.winner.nickname)}</div>
        </div>
        <div class="players-grid">${rows}</div>
        <p class="subtitle" style="text-align:center;margin-top:1rem">
            <span id="gameover-countdown">8</span> ${t('multi_redirect_hint')}
        </p>
        <button class="btn btn-secondary" onclick="leaveLobbyNow()" style="margin-top:0.6rem">${t('multi_to_menu')}</button>
    `;
    applyLang();
    fireConfetti();
    startGameOverCountdown();
}

function startGameOverCountdown() {
    let remaining = 8;
    const tick = () => {
        const el = document.getElementById('gameover-countdown');
        if (!el) return;
        el.textContent = remaining;
        remaining -= 1;
        if (remaining < 0) return;
        setTimeout(tick, 1000);
    };
    tick();
}

function leaveLobbyNow() {
    getSocket().emit('leave_lobby');
    clearSession();
    navigate('#/multi');
}

function requestRematch() {
    getSocket().emit('request_rematch');
}
