// Günün Futbolcusu (LoLdle "Classic" tarzı) — ana sayfadaki günlük tahmin oyunu.
// İpucu yok: bir futbolcu adı yaz → özellikleri gizli oyuncuyla kıyaslanır
// (🟩 aynı / 🟨 kısmen / 🟥 alakasız, sayısallarda ↑↓). 8 tahmin hakkı.

const CLASSIC_KEY = 'classic_v1';
const CLASSIC_MAX_GUESSES = 8;
const ATTR_ORDER = ['nationality', 'position', 'age', 'value', 'club', 'league'];
let classicData = null;     // /api/classic yanıtı (gün boyu sabit)
let classicSearchDebounce = null;
let classicBusy = false;
let classicOutsideClickBound = false;

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
    if ((h === '' || h === '#' || h === '#/') && classicData) { fillMasthead(); paintClassic(); }
});

async function renderClassic() {
    const root = document.getElementById('classic-card');
    if (!root) return;
    if (!classicData) {
        try { classicData = await (await fetch('/api/classic')).json(); }
        catch (_) { root.style.display = 'none'; return; }
        if (!classicData || classicData.error) { root.style.display = 'none'; return; }
    }
    fillMasthead();
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
    if (kind === 'nationality') inner = `${flagHtml(a.value, false, a.code) || ''}<span>${esc(a.value || '—')}</span>`;
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

function paintClassic() {
    const root = document.getElementById('classic-card');
    if (!root) return;
    const s = classicState();
    const used = s.guesses.length;
    const over = s.solved || used >= CLASSIC_MAX_GUESSES;
    const left = Math.max(0, CLASSIC_MAX_GUESSES - used);
    const streak = parseInt(localStorage.getItem('classic_streak') || '0', 10);

    // Başlık bandı (kicker + büyük başlık + geri sayım)
    const band = `
        <div class="daily-band">
            <div>
                <p class="daily-kicker">${t('daily_kicker')} &middot; #${classicData.day}</p>
                <h1 class="daily-headline">${t('classic_prompt')}</h1>
            </div>
            <div class="daily-next">
                <span>${t('daily_next')}</span>
                <span class="daily-countdown" id="daily-countdown">--:--:--</span>
            </div>
        </div>`;

    // Durum şeridi (3 hücre)
    const strip = `
        <div class="status-strip">
            <div class="status-cell"><span class="status-val">${used}</span><span class="status-lbl">${t('status_guess')}</span></div>
            <div class="status-cell b"><span class="status-val${!over ? ' em' : ''}">${left}</span><span class="status-lbl">${t('status_left')}</span></div>
            <div class="status-cell b"><span class="status-val">${streak}</span><span class="status-lbl">${t('status_streak')}</span></div>
        </div>`;

    // Deneme pip'leri
    const pips = `<div class="attempt-pips">${Array.from({ length: CLASSIC_MAX_GUESSES }).map((_, i) => {
        let cls = 'pip';
        if (i < used) cls += (s.solved && i === used - 1) ? ' hit' : ' miss';
        return `<span class="${cls}"></span>`;
    }).join('')}</div>`;

    // Sonuç banner'ı
    let banner = '';
    if (s.solved) {
        const name = s.guesses[used - 1]?.guess?.name || '';
        banner = `<div class="result-banner win"><div><p class="rb-title">${t('classic_solved')}</p><p class="rb-sub">${t('banner_answer')}: <b>${esc(name)}</b> — ${used} ${t('classic_tries')}</p></div></div>`;
    } else if (over) {
        banner = `<div class="result-banner lose"><div><p class="rb-title">${t('classic_lost')}</p><p class="rb-sub">${t('classic_tomorrow')}</p></div></div>`;
    }

    const legend = `
        <div class="cl-legend">
            <span><i class="cl-key hit"></i>${t('classic_legend_hit')}</span>
            <span><i class="cl-key partial"></i>${t('classic_legend_partial')}</span>
            <span><i class="cl-key miss"></i>${t('classic_legend_miss')}</span>
            <span class="cl-key-arrow">${t('classic_legend_up')}</span>
            <span class="cl-key-arrow">${t('classic_legend_down')}</span>
        </div>`;

    const inputBlock = over ? '' : `
        <div class="quiz-input-row daily-input">
            <div class="search-wrapper quiz-search-wrapper">
                <label class="visually-hidden" for="classic-input">${esc(t('guess_placeholder'))}</label>
                <input type="text" id="classic-input" autocomplete="off" maxlength="80" placeholder="${esc(t('guess_placeholder'))}"
                       role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="classic-dropdown">
                <div class="dropdown" id="classic-dropdown" role="listbox"></div>
            </div>
        </div>
        <div class="cl-poolnote">${t('classic_pool_note')}</div>`;

    const rows = [...s.guesses].reverse().map(g => `
        <div class="cl-guess${g.correct ? ' is-correct' : ''}">
            <div class="cl-guess-head">
                <img src="${esc(safeImageUrl(g.guess.image_url))}" onerror="this.style.display='none'" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">
                <span class="cl-guess-name">${esc(g.guess.name)}</span>
            </div>
            <div class="cl-attrs">${ATTR_ORDER.map(k => cellHtml(k, g.attrs[k])).join('')}</div>
        </div>`).join('');
    const table = s.guesses.length ? `<div class="cl-results">${rows}</div>` : '';

    const lost = over && !s.solved;
    const revealBtn = lost
        ? `<button class="btn btn-secondary" onclick="revealClassic()">${t('classic_reveal')}</button>` : '';
    const actions = over
        ? `<div class="daily-actions">${revealBtn}<button class="btn share-score-btn" onclick="shareClassic()">${t('share_result')}</button></div>`
        : '';

    root.style.display = '';
    root.innerHTML = `${band}${strip}${pips}${banner}
        <div class="daily-body">
            ${legend}
            ${inputBlock}
            ${table}
            ${actions}
        </div>`;

    startDailyCountdown();
    renderDailyStats();
    if (!s.solved && !over) setupClassicSearch();
}

// ---- Yan panel istatistikleri (mockup Statistics — dağılım çubukları) ----
function classicStats() {
    try { return JSON.parse(localStorage.getItem('classic_stats') || 'null') || null; }
    catch (_) { return null; }
}
function dailyStatsHTML(withTitle) {
    const st = classicStats() || { played: 0, wins: 0, dist: [0, 0, 0, 0, 0, 0, 0, 0] };
    const streak = parseInt(localStorage.getItem('classic_streak') || '0', 10);
    const best = parseInt(localStorage.getItem('classic_best') || '0', 10);
    const winRate = st.played ? Math.round((st.wins / st.played) * 100) : 0;
    const s = classicState();
    const highlight = s.solved ? s.guesses.length : 0;

    const cells = [
        [st.played, t('stat_played')],
        [winRate, t('stat_winrate')],
        [streak, t('status_streak')],
        [best, t('stat_best')],
    ].map(([v, l], i) => `<div class="dstat${i ? ' b' : ''}"><span class="dstat-val">${v}</span><span class="dstat-lbl">${l}</span></div>`).join('');

    const maxDist = Math.max(1, ...st.dist);
    const bars = st.dist.map((c, i) => {
        const pct = Math.max(Math.round((c / maxDist) * 100), c > 0 ? 12 : 6);
        const cls = (highlight === i + 1) ? 'dbar hl' : (c > 0 ? 'dbar on' : 'dbar');
        return `<div class="dist-row"><span class="dist-no">${i + 1}</span><div class="dist-track"><div class="${cls}" style="width:${pct}%">${c}</div></div></div>`;
    }).join('');

    return `${withTitle ? `<h3 class="kicker">${t('stats_title')}</h3>` : ''}
        <div class="dstat-grid">${cells}</div>
        <h4 class="kicker dist-head">${t('dist_title')}</h4>
        <div class="dist-list">${bars}</div>`;
}
function renderDailyStats() {
    const el = document.getElementById('daily-stats');
    if (el) el.innerHTML = dailyStatsHTML(true);
}

// ---- Gece yarısına geri sayım ----
let dailyCountdownTimer = null;
function startDailyCountdown() {
    if (dailyCountdownTimer) return;
    const tick = () => {
        const elc = document.getElementById('daily-countdown');
        if (!elc) { clearInterval(dailyCountdownTimer); dailyCountdownTimer = null; return; }
        const now = Date.now();
        const trNow = new Date(now + 3 * 60 * 60 * 1000);
        const next = Date.UTC(
            trNow.getUTCFullYear(),
            trNow.getUTCMonth(),
            trNow.getUTCDate() + 1,
        ) - 3 * 60 * 60 * 1000;
        let d = Math.max(0, next - now);
        const p = (n) => String(n).padStart(2, '0');
        elc.textContent = `${p(Math.floor(d / 3.6e6))}:${p(Math.floor(d % 3.6e6 / 6e4))}:${p(Math.floor(d % 6e4 / 1e3))}`;
    };
    tick();
    dailyCountdownTimer = setInterval(tick, 1000);
}

// ---- Masthead (tarih + puzzle no) ----
function fillMasthead() {
    const d = document.getElementById('mh-date');
    if (d && classicData?.date) {
        d.textContent = new Date(`${classicData.date}T12:00:00`).toLocaleDateString(
            currentLang === 'tr' ? 'tr-TR' : 'en-US',
            { weekday: 'long', month: 'long', day: 'numeric' },
        );
    }
    const n = document.getElementById('mh-no');
    if (n && classicData) n.textContent = 'No. ' + classicData.day + ' · ';
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

    if (s.guesses.length === 0) trackEvent('daily_start', { mode: 'daily' });
    s.guesses.push({ guess: res.guess, attrs: res.attrs, correct: res.correct });
    if (res.correct) { s.solved = true; classicApplyStreak(); }

    // İstatistik: oyun bittiğinde bir kez say (oynanan/kazanılan/dağılım).
    const over = res.correct || s.guesses.length >= CLASSIC_MAX_GUESSES;
    if (over && !s.counted) {
        trackEvent('daily_finish', {
            mode: 'daily',
            result: res.correct ? 'solved' : 'failed',
            attempts: s.guesses.length,
        });
        let st;
        try { st = JSON.parse(localStorage.getItem('classic_stats') || 'null'); } catch (_) { st = null; }
        if (!st) st = { played: 0, wins: 0, dist: [0, 0, 0, 0, 0, 0, 0, 0] };
        st.played++;
        if (res.correct) { st.wins++; const i = s.guesses.length - 1; st.dist[i] = (st.dist[i] || 0) + 1; }
        localStorage.setItem('classic_stats', JSON.stringify(st));
        s.counted = true;
    }

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

// Gizli oyuncuyu popup'ta gösterir (yalnız oyun bitince). İlk açılışta sunucudan
// çekip localStorage'a yazar (gün değişince yeni state ile sıfırlanır); sonraki
// tıklamalarda tekrar fetch etmeden modalı açar.
async function revealClassic() {
    const s = classicState();
    const over = s.solved || s.guesses.length >= CLASSIC_MAX_GUESSES;
    if (!over) return;
    if (!s.revealed) {
        let res;
        try { res = await (await fetch('/api/classic/reveal')).json(); }
        catch (_) { showToast(t('quiz_load_error'), 'error'); return; }
        if (!res || res.error || !res.player) { showToast(t('quiz_load_error'), 'error'); return; }
        s.revealed = res.player;
        classicSave(s);
    }
    openRevealModal(s.revealed);
}

function openRevealModal(r) {
    closeRevealModal();
    const meta = [
        `<span class="rm-pill">${flagHtml(r.country, true, r.country_code) || ''} ${esc(r.country || '?')}</span>`,
        `<span class="rm-pill">${esc(posText(r.position))}</span>`,
        r.club_name ? `<span class="rm-pill">${esc(r.club_name)}</span>` : '',
    ].join('');
    const backdrop = document.createElement('div');
    backdrop.className = 'quiz-modal-backdrop';
    backdrop.id = 'classic-reveal-backdrop';
    backdrop.onclick = (e) => { if (e.target === backdrop) closeRevealModal(); };
    backdrop.innerHTML = `
        <div class="result-modal reveal">
            <button class="rm-close" onclick="closeRevealModal()" aria-label="${esc(t('close'))}">&times;</button>
            <div class="rm-sub" style="text-transform:uppercase;letter-spacing:0.05em">${t('classic_answer')}</div>
            <img class="rm-photo" src="${esc(safeImageUrl(r.image_url))}" onerror="this.style.display='none'" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">
            <div class="rm-name">${esc(r.name)}</div>
            <div class="rm-pills">${meta}</div>
            <button class="btn btn-primary rm-next" onclick="closeRevealModal()">${t('close')}</button>
        </div>`;
    document.body.appendChild(backdrop);
    activateDialog(backdrop, closeRevealModal);
}

function closeRevealModal() {
    const b = document.getElementById('classic-reveal-backdrop');
    if (b) { deactivateDialog(b); b.remove(); }
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
        if (q.length < 2) {
            dropdown.classList.remove('show');
            input.setAttribute('aria-expanded', 'false');
            return;
        }
        classicSearchDebounce = setTimeout(async () => {
            try {
                const response = await fetch('/api/search-player?active=1&q=' + encodeURIComponent(q));
                if (!response.ok) throw new Error(`search failed: ${response.status}`);
                const players = await response.json();
                if (input.value.trim() !== q) return;
                if (!players.length) {
                    dropdown.innerHTML = `<div style="padding:0.8rem;color:var(--text-dim)">${t('no_player')}</div>`;
                } else {
                    dropdown.innerHTML = players.map(p => `
                        <div class="dropdown-player" role="option" aria-selected="false" data-id="${p.player_id}" data-name="${esc(p.name)}">
                            <img src="${esc(safeImageUrl(p.image_url))}" onerror="this.style.display='none'" alt="">
                            <div class="dp-info">
                                <div class="dp-name">${esc(p.name)}</div>
                            </div>
                        </div>`).join('');
                }
                dropdown.classList.add('show');
                input.setAttribute('aria-expanded', 'true');
                dropdown.querySelectorAll('.dropdown-player').forEach(item => {
                    item.addEventListener('click', () => {
                        dropdown.classList.remove('show');
                        input.setAttribute('aria-expanded', 'false');
                        input.value = '';
                        classicGuessById(parseInt(item.dataset.id, 10));
                    });
                });
            } catch (_) {
                if (input.value.trim() === q) {
                    dropdown.classList.remove('show');
                    input.setAttribute('aria-expanded', 'false');
                }
            }
        }, 250);
    });

    attachSearchKeys(input, dropdown, submitClassic);
    if (!classicOutsideClickBound) {
        classicOutsideClickBound = true;
        document.addEventListener('click', (e) => {
            if (e.target.closest('#classic-card .quiz-search-wrapper')) return;
            const activeDropdown = document.getElementById('classic-dropdown');
            const activeInput = document.getElementById('classic-input');
            activeDropdown?.classList.remove('show');
            activeInput?.setAttribute('aria-expanded', 'false');
        });
    }
}
