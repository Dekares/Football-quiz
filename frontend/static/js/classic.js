// Günün Futbolcusu (LoLdle "Classic" tarzı) — ana sayfadaki günlük tahmin oyunu.
// İpucu yok: bir futbolcu adı yaz → özellikleri gizli oyuncuyla kıyaslanır
// (🟩 aynı / 🟨 kısmen / 🟥 alakasız, sayısallarda ↑↓). 8 tahmin hakkı.

const CLASSIC_KEY = 'classic_v1';
const CLASSIC_MAX_GUESSES = 8;
const ATTR_ORDER = ['nationality', 'position', 'age', 'value', 'club', 'league'];
let classicData = null;     // /api/classic yanıtı (gün boyu sabit)
let classicSearchDebounce = null;
let classicBusy = false;

// ---- localStorage durum ----
function classicState() {
    try {
        const s = JSON.parse(localStorage.getItem(CLASSIC_KEY) || 'null');
        if (s && classicData && s.day === classicData.day) return s;
    } catch (_) { /* yoksay */ }
    return { day: classicData ? classicData.day : 0, guesses: [], solved: false };
}
function classicSave(s) { localStorage.setItem(CLASSIC_KEY, JSON.stringify(s)); }

// ---- Router girişi ----
onRoute((route) => { if (route.name === 'menu') renderClassic(); });

// Dil değişince (menü açıksa) günlük tahmin kartını yeniden çiz.
window.addEventListener('langchange', () => {
    const h = location.hash;
    if ((h === '' || h === '#' || h === '#/') && classicData) paintClassic();
});

async function renderClassic() {
    const root = document.getElementById('classic-card');
    if (!root) return;
    if (!classicData) {
        try { classicData = await (await fetch('/api/classic')).json(); }
        catch (_) { root.style.display = 'none'; return; }
        if (!classicData || classicData.error) { root.style.display = 'none'; return; }
    }
    paintClassic();
}

// ---- Yardımcılar ----
function fmtVal(v) {
    if (!v) return '—';
    if (v >= 1e6) return (v / 1e6).toFixed(v % 1e6 ? 1 : 0).replace('.0', '') + 'M';
    if (v >= 1e3) return Math.round(v / 1e3) + 'K';
    return String(v);
}
function arrowHtml(dir) {
    if (dir === 'up') return '<span class="cl-arrow">▲</span>';
    if (dir === 'down') return '<span class="cl-arrow">▼</span>';
    return '';
}
function leagueName(code) {
    if (!code) return '—';
    return (typeof LEAGUE_NAMES !== 'undefined' && LEAGUE_NAMES[code]) || code;
}

function cellHtml(kind, a) {
    let inner;
    if (kind === 'nationality') inner = `${flagHtml(a.value) || ''}<span>${esc(a.value || '—')}</span>`;
    else if (kind === 'position') inner = esc(posText(a.value));
    else if (kind === 'age') inner = `${a.value ?? '—'} ${arrowHtml(a.dir)}`;
    else if (kind === 'value') inner = `${fmtVal(a.value)} ${arrowHtml(a.dir)}`;
    else if (kind === 'club') inner = esc(a.value || '—');
    else if (kind === 'league') inner = esc(leagueName(a.value));
    else inner = esc(a.value || '—');
    return `<div class="cl-cell ${a.status}">
            <span class="cl-cell-label">${t('attr_' + kind)}</span>
            <span class="cl-cell-val">${inner}</span>
        </div>`;
}

function classicStreakBadge() {
    const streak = parseInt(localStorage.getItem('classic_streak') || '0', 10);
    return streak > 0 ? `<span class="daily-streak">🔥 ${streak}</span>` : '';
}

function paintClassic() {
    const root = document.getElementById('classic-card');
    if (!root) return;
    const s = classicState();
    const over = s.solved || s.guesses.length >= CLASSIC_MAX_GUESSES;

    const legend = `
        <div class="cl-legend">
            <span><i class="cl-key hit"></i>${t('classic_legend_hit')}</span>
            <span><i class="cl-key partial"></i>${t('classic_legend_partial')}</span>
            <span><i class="cl-key miss"></i>${t('classic_legend_miss')}</span>
            <span class="cl-key-arrow">${t('classic_legend_up')}</span>
            <span class="cl-key-arrow">${t('classic_legend_down')}</span>
        </div>`;

    // Arama + sonuçlar arama kutusunun ALTINDA
    const inputBlock = over ? '' : `
        <div class="quiz-input-row daily-input">
            <div class="search-wrapper quiz-search-wrapper">
                <input type="text" id="classic-input" autocomplete="off" placeholder="${esc(t('guess_placeholder'))}">
                <div class="dropdown" id="classic-dropdown"></div>
            </div>
        </div>
        <div class="cl-poolnote">${t('classic_pool_note')}</div>`;

    // En yeni tahmin en üstte. İsim tam bir satır; özellikler altında etiketli hücreler.
    const rows = [...s.guesses].reverse().map(g => `
        <div class="cl-guess${g.correct ? ' is-correct' : ''}">
            <div class="cl-guess-head">
                <img src="${g.guess.image_url || ''}" onerror="this.style.display='none'" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">
                <span class="cl-guess-name">${esc(g.guess.name)}</span>
            </div>
            <div class="cl-attrs">${ATTR_ORDER.map(k => cellHtml(k, g.attrs[k])).join('')}</div>
        </div>`).join('');
    const table = s.guesses.length ? `<div class="cl-results">${rows}</div>` : '';

    const result = s.solved
        ? `<div class="cl-win">🎉 ${t('classic_solved')} — ${s.guesses.length} ${t('classic_tries')}</div>`
        : (over ? `<div class="cl-lose">${t('classic_lost')}</div>` : '');
    const actions = over
        ? `<div class="daily-actions"><button class="btn share-score-btn" onclick="shareClassic()">${t('share_result')}</button></div>
           <div class="daily-foot">${t('classic_tomorrow')}</div>`
        : `<div class="daily-foot">${t('classic_attempts')}: ${s.guesses.length} / ${CLASSIC_MAX_GUESSES}</div>`;

    root.style.display = '';
    root.innerHTML = `
        <div class="daily-head">
            <span class="daily-badge">${t('classic_title')} · #${classicData.day}</span>
            ${classicStreakBadge()}
        </div>
        <div class="daily-q">${t('classic_prompt')}</div>
        ${legend}
        ${inputBlock}
        ${result}
        ${table}
        ${actions}`;

    if (!s.solved) setupClassicSearch();
}

// ---- Tahmin ----
async function classicGuessById(playerId) {
    const s = classicState();
    if (s.solved || s.guesses.length >= CLASSIC_MAX_GUESSES || classicBusy) return;
    if (s.guesses.some(g => g.guess.player_id === playerId)) {
        showToast(t('classic_already'), 'error');
        return;
    }
    classicBusy = true;
    let res;
    try { res = await (await fetch(`/api/classic/guess?player_id=${playerId}`)).json(); }
    catch (_) { classicBusy = false; showToast(t('quiz_load_error'), 'error'); return; }
    classicBusy = false;
    if (!res || res.error) { showToast(t('quiz_load_error'), 'error'); return; }

    s.guesses.push({ guess: res.guess, attrs: res.attrs, correct: res.correct });
    if (res.correct) { s.solved = true; classicApplyStreak(); }
    classicSave(s);
    paintClassic();
}

function submitClassic() {
    // Açık dropdown'da ilk öneriyi seç (boş submit yerine).
    const first = document.querySelector('#classic-dropdown .dropdown-player');
    if (first) first.click();
}

function classicApplyStreak() {
    const day = classicData.day;
    const last = parseInt(localStorage.getItem('classic_last_day') || '-999', 10);
    let streak = parseInt(localStorage.getItem('classic_streak') || '0', 10);
    streak = (last === day - 1) ? streak + 1 : 1;
    const best = Math.max(streak, parseInt(localStorage.getItem('classic_best') || '0', 10));
    localStorage.setItem('classic_streak', String(streak));
    localStorage.setItem('classic_best', String(best));
    localStorage.setItem('classic_last_day', String(day));
}

function shareClassic() {
    const s = classicState();
    const grid = s.guesses.map(g =>
        ATTR_ORDER.map(k => {
            const st = g.attrs[k].status;
            return st === 'hit' ? '🟩' : (st === 'partial' ? '🟨' : '🟥');
        }).join('')
    ).join('\n');
    const score = s.solved ? `${s.guesses.length}/${CLASSIC_MAX_GUESSES}` : `X/${CLASSIC_MAX_GUESSES}`;
    const caption = `${t('classic_title')} #${classicData.day} — ${score}\n${grid}`;
    shareOrCopy(caption, location.origin + '/');
}

// ---- Canlı arama (yalnız tanınmış oyuncular) ----
function setupClassicSearch() {
    const input = document.getElementById('classic-input');
    const dropdown = document.getElementById('classic-dropdown');
    if (!input || !dropdown) return;

    input.addEventListener('input', () => {
        clearTimeout(classicSearchDebounce);
        const q = input.value.trim();
        if (q.length < 2) { dropdown.classList.remove('show'); return; }
        classicSearchDebounce = setTimeout(async () => {
            try {
                const players = await (await fetch('/api/search-player?active=1&q=' + encodeURIComponent(q))).json();
                if (!players.length) {
                    dropdown.innerHTML = `<div style="padding:0.8rem;color:var(--text-dim)">${t('no_player')}</div>`;
                } else {
                    dropdown.innerHTML = players.map(p => `
                        <div class="dropdown-player" data-id="${p.player_id}" data-name="${esc(p.name)}">
                            <img src="${p.image_url || ''}" onerror="this.style.display='none'" alt="">
                            <div class="dp-info">
                                <div class="dp-name">${esc(p.name)}</div>
                                <div class="dp-meta">${posText(p.position)} · ${esc(p.country || '')}</div>
                            </div>
                        </div>`).join('');
                }
                dropdown.classList.add('show');
                dropdown.querySelectorAll('.dropdown-player').forEach(item => {
                    item.addEventListener('click', () => {
                        dropdown.classList.remove('show');
                        input.value = '';
                        classicGuessById(parseInt(item.dataset.id, 10));
                    });
                });
            } catch (_) { /* sessiz */ }
        }, 250);
    });

    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submitClassic(); });
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.quiz-search-wrapper')) dropdown.classList.remove('show');
    }, { once: true });
}
