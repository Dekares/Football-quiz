// Solo modu: Oyuncu Tahmin Et (kariyer geçmişinden tahmin)

// ===== State =====
let currentQuiz = null;
let quizDifficulty = 'easy';
let quizLives = 0;
let hintsUsed = 0;
// Run (koşu) durumu: 8 can tüm koşu boyunca paylaşılır, yanlışta kalıcı azalır.
let runStreak = 0;   // mevcut seri (atlanınca sıfırlanır, doğruda artar)
let runMax = 0;      // koşudaki en yüksek seri
let runTotal = 0;    // koşuda doğru bilinen futbolcu sayısı
let runActive = false;
const MAX_LIVES = 8;

// ===== Retention: localStorage istatistikleri =====
function getSoloStats() {
    return {
        best:   parseInt(localStorage.getItem('solo_best_streak') || '0', 10),   // tüm zamanların en iyi serisi (kalıcı)
        total:  runTotal,                                                        // KOŞU-İÇİ toplam doğru (can bitince sıfır)
        streak: runStreak,                                                       // mevcut koşunun serisi (bellek)
    };
}
function setSoloStats(s) {
    localStorage.setItem('solo_best_streak', String(s.best));
}
function renderSoloStats(opts) {
    const streakEl = document.getElementById('stat-streak');
    if (!streakEl) return;
    const s = getSoloStats();
    streakEl.textContent = s.streak;
    document.getElementById('stat-best').textContent = s.best;
    document.getElementById('stat-total').textContent = s.total;
    if (opts?.pulseRecord) {
        const card = document.querySelector('.stat-card.record');
        if (card) { card.classList.remove('pulse'); void card.offsetWidth; card.classList.add('pulse'); }
    }
}
function recordCorrectAnswer() {
    runStreak += 1;
    runTotal  += 1;
    if (runStreak > runMax) runMax = runStreak;
    const s = getSoloStats();
    const newRecord = runStreak > s.best;
    if (newRecord) s.best = runStreak;     // tüm zamanların rekoru (kalıcı)
    setSoloStats(s);
    renderSoloStats({ pulseRecord: newRecord });
    return { newRecord, streak: runStreak, best: s.best };
}
function resetRunStreak() {
    if (runStreak === 0) return;
    runStreak = 0;
    renderSoloStats();
}
// Yeni koşu: canlar dolar, sayaçlar sıfırlanır (kaldığı yerden DEVAM ETMEZ).
function startRun() {
    quizLives = MAX_LIVES;
    runStreak = 0;
    runMax = 0;
    runTotal = 0;
    runActive = true;
    loadQuiz();
}
function newRound() {
    if (!runActive) { startRun(); return; }   // ilk giriş: koşuyu başlat
    resetRunStreak();                          // gönüllü geçiş seriyi kırar (can harcanmaz)
    loadQuiz();
}

// ===== Son Tahminler (yan panel) =====
function getRecent() {
    try { return JSON.parse(localStorage.getItem('solo_recent') || '[]'); }
    catch (_) { return []; }
}
function pushRecent(player, correct) {
    const list = getRecent();
    list.unshift({ name: player.name, image: player.image_url || '', correct, ts: Date.now() });
    localStorage.setItem('solo_recent', JSON.stringify(list.slice(0, 8)));
    renderRecent();
}
function relTime(ts) {
    const sec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
    if (sec < 60) return t('time_now');
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min} ${t('time_min')}`;
    return `${Math.floor(min / 60)} ${t('time_hour')}`;
}
function renderRecent() {
    const el = document.getElementById('recent-guesses');
    if (!el) return;
    const list = getRecent();
    if (list.length === 0) {
        el.innerHTML = `<div class="recent-empty">${t('recent_empty')}</div>`;
        return;
    }
    el.innerHTML = list.map(r => `
        <div class="recent-item">
            <img src="${esc(r.image)}" onerror="this.src='${PLAYER_FALLBACK}'" alt="">
            <span class="rg-name">${esc(r.name)}</span>
            <span class="rg-time">${relTime(r.ts)}</span>
            <span class="rg-mark ${r.correct ? 'ok' : 'no'}">${r.correct ? '✓' : '✕'}</span>
        </div>`).join('');
}

const PLAYER_FALLBACK = 'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><rect fill=%22%23161f33%22 width=%2240%22 height=%2240%22/><text x=%2220%22 y=%2224%22 text-anchor=%22middle%22 fill=%22%238a93a6%22 font-size=%2216%22>?</text></svg>';

// ===== Tekrar önleme: son görülen oyuncular (kayan pencere) =====
// Server'a exclude listesi olarak gider → ardışık/yakın tekrarı engeller.
// Pencere havuzdan çok küçük (easy ~300) olduğu için havuzu tüketmez; tüketse
// bile server dışlamayı yok sayıp yine oyuncu döndürür.
const SEEN_WINDOW = 30;
function getSeen() {
    try { return JSON.parse(localStorage.getItem('solo_seen') || '[]'); }
    catch (_) { return []; }
}
function pushSeen(id) {
    if (!id) return;
    const list = getSeen().filter(x => x !== id);
    list.unshift(id);
    localStorage.setItem('solo_seen', JSON.stringify(list.slice(0, SEEN_WINDOW)));
}

// ===== Quiz =====
function setDifficulty(diff, btn) {
    if (diff === quizDifficulty && currentQuiz) return;   // değişiklik yoksa turu bozma
    quizDifficulty = diff;
    document.querySelectorAll('#page-solo .difficulty-selector button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    // Zorluk değişince beklemeden yeni zorluktan tur yükle (mevcut turun bitmesini bekleme).
    // Sonuç modalı açıksa kapanışta zaten yeni zorlukla yüklenir.
    if (!document.getElementById('quiz-modal-backdrop')) loadQuiz();
}

function renderLives(animateLost) {
    const el = document.getElementById('quiz-lives');
    el.style.display = 'flex';
    let html = '';
    for (let i = 0; i < MAX_LIVES; i++) {
        if (i < quizLives) html += '<div class="life active">&#10003;</div>';
        else {
            const isJustLost = animateLost && i === quizLives;
            html += `<div class="life used${isJustLost ? ' lost-anim' : ''}">&#10007;</div>`;
        }
    }
    el.innerHTML = html;
}

function formatDate(c) {
    const dfrom = c.date_from ? c.date_from.substring(0, 4) : null;
    const dto = c.date_to ? c.date_to.substring(0, 4) : null;
    if (dfrom && dto) return (dfrom === dto) ? dfrom : `${dfrom} – ${dto}`;
    if (dfrom && !dto) return `${dfrom} – ${t('ongoing')}`;
    if (!dfrom && dto) return `${dto}${t('until')}`;
    return '';
}

// ===== İpucu: gizli oyuncudan kademeli bilgi (yaş → detaylı mevki → baş harfler) =====
function ageFrom(dob) {
    if (!dob) return null;
    const b = new Date(dob);
    if (isNaN(b.getTime())) return null;
    const now = new Date();
    let age = now.getFullYear() - b.getFullYear();
    const m = now.getMonth() - b.getMonth();
    if (m < 0 || (m === 0 && now.getDate() < b.getDate())) age--;
    return (age >= 0 && age < 120) ? age : null;
}
function maskName(name) {
    // İlk harf açık, gerisi yıldız: "Jadon Sancho" -> "J**** S*****"
    return name.split(' ').map(word =>
        [...word].map((ch, i) => (/[\p{L}]/u.test(ch) && i >= 1) ? '*' : ch).join('')
    ).join(' ');
}
// Sırayla açılacak kutucuklar (etiket/emoji yok, sadece bilgi); boş değer atlanır.
function hintCards() {
    if (!currentQuiz) return [];
    const q = currentQuiz, cards = [];
    const age = ageFrom(q.date_of_birth);
    if (age != null) cards.push(`${age} ${t('hint_years_old')}`);
    if (q.sub_position) cards.push(subPosText(q.sub_position));
    cards.push(maskName(q.name));
    return cards;
}
function setHintBtn() {
    const btn = document.getElementById('hint-btn');
    const badge = document.getElementById('hint-count');
    const total = hintCards().length;
    if (badge) badge.textContent = Math.max(0, total - hintsUsed);
    if (btn) btn.disabled = !currentQuiz || hintsUsed >= total;
}
function useHint() {
    const cards = hintCards();
    if (!currentQuiz || hintsUsed >= cards.length) return;
    hintsUsed += 1;
    const box = document.getElementById('quiz-hint-reveal');
    box.style.display = 'flex';
    box.innerHTML = cards.slice(0, hintsUsed)
        .map(v => `<span class="hint-box">${esc(v)}</span>`).join('');
    setHintBtn();
}

async function loadQuiz() {
    const area = document.getElementById('quiz-area');
    area.innerHTML = `<div class="loading"><div class="spinner"></div><div>${t('loading')}</div></div>`;

    hintsUsed = 0;
    currentQuiz = null;
    document.getElementById('quiz-wrong-feedback').innerHTML = '';
    document.getElementById('quiz-hint-reveal').style.display = 'none';
    document.getElementById('quiz-input-row').style.display = 'flex';
    document.getElementById('skip-btn').disabled = false;
    document.getElementById('quiz-guess').value = '';

    renderLives(false);
    renderSoloStats();
    setHintBtn();

    try {
        const seen = getSeen();
        const exclude = seen.length ? '&exclude=' + seen.join(',') : '';
        currentQuiz = await safeFetch('/api/quiz?difficulty=' + quizDifficulty + exclude);
        pushSeen(currentQuiz.player_id);
    } catch (e) {
        area.innerHTML = `<div class="error-card">
            <p>${t('quiz_load_error')}</p>
            <button class="btn btn-primary" onclick="loadQuiz()">${t('retry')}</button>
        </div>`;
        return;
    }

    renderQuizArea();
    document.getElementById('quiz-guess').focus();
}

// #quiz-area içeriğini (mevki/milliyet paneli + kariyer zaman çizelgesi) currentQuiz'den
// kurar. Can/ipucu/giriş satırları bu alanın dışında olduğundan dil değişiminde tekrar
// çağrılması mevcut tur durumunu bozmaz.
function renderQuizArea() {
    const area = document.getElementById('quiz-area');
    if (!area || !currentQuiz) return;

    let html = `
        <div class="info-panel">
            <div class="info-cell">
                <div class="info-ico">&#128085;</div>
                <div class="info-text">
                    <div class="info-label">${t('position')}</div>
                    <div class="info-value">${esc(posText(currentQuiz.position))}</div>
                </div>
            </div>
            <div class="info-cell">
                <div class="info-ico">&#127760;</div>
                <div class="info-text">
                    <div class="info-label">${t('nationality')}</div>
                    <div class="info-value">${flagHtml(currentQuiz.country, true)}${esc(currentQuiz.country || '?')}</div>
                </div>
            </div>
        </div>
        <div class="career-head">${t('career_journey')}</div>
        <div class="quiz-timeline">`;

    currentQuiz.clubs.forEach((c, i) => {
        const delay = `animation-delay:${Math.min(i * 60, 600)}ms`;
        if (c.is_retirement) {
            const year = c.date_from ? c.date_from.substring(0, 4) : '';
            html += `
                <div class="timeline-item retirement" style="${delay}">
                    <div class="retirement-badge">🏁</div>
                    <div class="timeline-info"><div class="club-name">${t('retirement')}</div></div>
                    <div class="club-years">${esc(year)}</div>
                </div>`;
        } else {
            html += `
                <div class="timeline-item" style="${delay}">
                    ${c.logo_url ? `<img src="${c.logo_url}" onerror="this.style.display='none'" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">` : ''}
                    <div class="timeline-info"><div class="club-name">${esc(c.name)}</div></div>
                    <div class="club-years">${formatDate(c)}</div>
                </div>`;
        }
    });
    html += '</div>';
    area.innerHTML = html;

    setHintBtn();
}

// ===== Player Search Dropdown =====
let selectedGuessId = null;
let quizDebounce = null;

function setupQuizSearch() {
    const quizInput = document.getElementById('quiz-guess');
    const quizDropdown = document.getElementById('quiz-player-dropdown');
    if (!quizInput || !quizDropdown) return;

    quizInput.addEventListener('input', () => {
        clearTimeout(quizDebounce);
        selectedGuessId = null;
        const q = quizInput.value.trim();
        if (q.length < 2) { quizDropdown.classList.remove('show'); return; }

        quizDebounce = setTimeout(async () => {
            const res = await fetch('/api/search-player?q=' + encodeURIComponent(q));
            const players = await res.json();
            if (players.length === 0) {
                quizDropdown.innerHTML = `<div style="padding:0.8rem;color:var(--text-dim)">${t('no_player')}</div>`;
            } else {
                // Tahmin oyununda mevki/ülke gösterilmez (cevabı ele vermesin).
                quizDropdown.innerHTML = players.map(p => `
                    <div class="dropdown-player" data-id="${p.player_id}" data-name="${esc(p.name)}">
                        <img src="${p.image_url || ''}" onerror="this.src='${PLAYER_FALLBACK}'" alt="">
                        <div class="dp-info"><div class="dp-name">${esc(p.name)}</div></div>
                    </div>
                `).join('');
            }
            quizDropdown.classList.add('show');
            quizDropdown.querySelectorAll('.dropdown-player').forEach(item => {
                item.addEventListener('click', () => {
                    selectedGuessId = parseInt(item.dataset.id);
                    quizInput.value = item.dataset.name;
                    quizDropdown.classList.remove('show');
                    submitGuess();
                });
            });
        }, 250);
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.quiz-search-wrapper')) quizDropdown.classList.remove('show');
    });

    quizInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') submitGuess();
    });
}

function submitGuess() {
    if (!currentQuiz) return;
    const quizInput = document.getElementById('quiz-guess');
    const quizDropdown = document.getElementById('quiz-player-dropdown');
    const guess = quizInput.value.trim();
    if (!guess) return;

    quizDropdown.classList.remove('show');

    let isCorrect = false;
    if (selectedGuessId !== null) {
        isCorrect = selectedGuessId === currentQuiz.player_id;
    } else {
        const normalizedGuess = normalize(guess);
        const normalizedAnswer = normalize(currentQuiz.name);
        const answerParts = normalizedAnswer.split(/\s+/);
        const guessParts = normalizedGuess.split(/\s+/);
        isCorrect = normalizedGuess === normalizedAnswer
            || answerParts.some(p => p.length > 2 && normalizedGuess.includes(p))
            || guessParts.some(p => p.length > 2 && normalizedAnswer.includes(p));
    }

    if (isCorrect) {
        const rec = recordCorrectAnswer();
        showQuizResult(true, rec);
    } else {
        quizLives--;
        renderLives(true);
        selectedGuessId = null;

        if (quizLives <= 0) {
            runActive = false;   // koşu bitti → game-over kartı, sonra sıfırdan
            document.getElementById('quiz-wrong-feedback').innerHTML = '';
            showGameOver();
        } else {
            document.getElementById('quiz-wrong-feedback').innerHTML =
                `<div class="wrong-guess">${t('wrong_guess')} ${quizLives} ${t('lives_left')}</div>`;
            quizInput.value = '';
            quizInput.focus();
        }
    }
}

function passQuiz() {
    if (!currentQuiz) return;   // atla: cevabı göster, seriyi kır, CAN HARCAMA, sonraki oyuncu
    document.getElementById('quiz-player-dropdown').classList.remove('show');
    resetRunStreak();
    document.getElementById('quiz-wrong-feedback').innerHTML = '';
    showQuizResult(false);
}

// Açık sonuç modalının verisi — dil değişince yeniden çizebilmek için saklanır.
let lastResult = null;

function showQuizResult(correct, recordInfo) {
    const p = currentQuiz;
    pushRecent(p, correct);

    document.getElementById('quiz-input-row').style.display = 'none';
    document.getElementById('quiz-lives').style.display = 'none';
    document.getElementById('quiz-hint-reveal').style.display = 'none';
    document.getElementById('skip-btn').disabled = true;
    document.getElementById('hint-btn').disabled = true;

    lastResult = { player: p, correct, recordInfo };
    renderResultModal();

    selectedGuessId = null;
    currentQuiz = null;

    if (correct) fireConfetti();
}

function renderResultModal() {
    if (!lastResult) return;
    const { player: p, correct, recordInfo } = lastResult;

    const existing = document.getElementById('quiz-modal-backdrop');
    if (existing) existing.remove();

    const stats = getSoloStats();
    const statsHtml = correct ? `
            <div class="rm-stats">
                <div class="rm-stat">
                    <div class="rm-stat-ico">&#11088;</div>
                    <div class="rm-stat-meta"><div class="rm-stat-val">${stats.streak}</div><div class="rm-stat-lbl">${t('solo_streak')}</div></div>
                </div>
                <div class="rm-stat${recordInfo?.newRecord ? ' record' : ''}">
                    <div class="rm-stat-ico">&#127942;</div>
                    <div class="rm-stat-meta"><div class="rm-stat-val">${stats.best}</div><div class="rm-stat-lbl">${t('solo_record')}</div></div>
                </div>
            </div>` : '';

    const title = correct
        ? `${t('quiz_correct_title')} <span class="accent">${t('quiz_correct_accent')}</span>`
        : t('quiz_wrong_title');
    const sub = correct ? t('quiz_correct_sub') : t('quiz_wrong_sub');

    const backdrop = document.createElement('div');
    backdrop.className = 'quiz-modal-backdrop';
    backdrop.id = 'quiz-modal-backdrop';
    backdrop.innerHTML = `
        <div class="result-modal ${correct ? 'correct' : 'wrong'}">
            <div class="rm-check">${correct ? '&#10003;' : '&#10007;'}</div>
            <h2 class="rm-title">${title}</h2>
            <p class="rm-sub">${esc(sub)}</p>
            <img class="rm-photo" src="${p.image_url || ''}" onerror="this.style.display='none'" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">
            <div class="rm-name">${esc(p.name)}</div>
            <div class="rm-pills">
                <span class="rm-pill">&#128737;&#65039; ${esc(posText(p.position))}</span>
                <span class="rm-pill">${flagHtml(p.country, true)} ${esc(p.country || '?')}</span>
            </div>
            ${statsHtml}
            <button class="btn btn-primary rm-next" onclick="closeQuizModalAndNext()">
                <span>&#9917; ${t('quiz_next_player')}</span><span class="rm-arrow">&rsaquo;</span>
            </button>
        </div>`;
    document.body.appendChild(backdrop);
}

// Koşu bitti kartı: bilemediğin oyuncu + en yüksek seri + toplam doğru + paylaş.
function showGameOver() {
    const p = currentQuiz;
    pushRecent(p, false);
    document.getElementById('quiz-input-row').style.display = 'none';
    document.getElementById('quiz-lives').style.display = 'none';
    document.getElementById('quiz-hint-reveal').style.display = 'none';
    document.getElementById('skip-btn').disabled = true;
    document.getElementById('hint-btn').disabled = true;
    lastResult = { gameOver: true, player: p, runMax, runTotal };
    renderGameOverModal();
    selectedGuessId = null;
    currentQuiz = null;
}

function renderGameOverModal() {
    if (!lastResult?.gameOver) return;
    const { player: p, runMax: mx, runTotal: tot } = lastResult;
    const existing = document.getElementById('quiz-modal-backdrop');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.className = 'quiz-modal-backdrop';
    backdrop.id = 'quiz-modal-backdrop';
    backdrop.innerHTML = `
        <div class="result-modal wrong">
            <div class="rm-check">&#128128;</div>
            <h2 class="rm-title">${t('multi_game_over')}</h2>
            <p class="rm-sub">${t('game_over_missed')}</p>
            <img class="rm-photo" src="${p.image_url || ''}" onerror="this.style.display='none'" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">
            <div class="rm-name">${esc(p.name)}</div>
            <div class="rm-stats">
                <div class="rm-stat">
                    <div class="rm-stat-ico">&#128293;</div>
                    <div class="rm-stat-meta"><div class="rm-stat-val">${mx}</div><div class="rm-stat-lbl">${t('run_max_streak')}</div></div>
                </div>
                <div class="rm-stat">
                    <div class="rm-stat-ico">&#127919;</div>
                    <div class="rm-stat-meta"><div class="rm-stat-val">${tot}</div><div class="rm-stat-lbl">${t('solo_total_correct')}</div></div>
                </div>
            </div>
            <button class="btn btn-primary rm-next" onclick="restartRun()">
                <span>&#9917; ${t('new_run')}</span>
            </button>
            <button class="btn rm-share" onclick="shareRunResult()">&#128279; ${t('share_result')}</button>
        </div>`;
    document.body.appendChild(backdrop);
}

function restartRun() {
    const b = document.getElementById('quiz-modal-backdrop');
    if (b) b.remove();
    lastResult = null;
    startRun();
}

function shareRunResult() {
    const r = lastResult || {};
    const caption = t('share_caption_run')
        .replace('{total}', r.runTotal || 0)
        .replace('{streak}', r.runMax || 0);
    shareOrCopy(caption, `${location.origin}/`);
}

function closeQuizModalAndNext() {
    const backdrop = document.getElementById('quiz-modal-backdrop');
    if (backdrop) backdrop.remove();
    lastResult = null;
    loadQuiz();
}

// Dil değişince solo görünümünü yeniden çiz: aktif quiz alanı, son tahminler
// paneli ve (açıksa) sonuç modalı t() ile kurulduğundan tazelenmeli.
window.addEventListener('langchange', () => {
    renderRecent();
    renderQuizArea();
    if (document.getElementById('quiz-modal-backdrop')) {
        lastResult?.gameOver ? renderGameOverModal() : renderResultModal();
    }
});

// ===== Init =====
setupQuizSearch();

window.addEventListener('DOMContentLoaded', () => {
    renderSoloStats();
    renderRecent();
    // Solo sayfasına ilk girişte otomatik bir tur yükle (tasarımdaki gibi aktif soru).
    if (typeof onRoute === 'function') {
        onRoute((route) => {
            if (route.name === 'solo' && !runActive && !document.getElementById('quiz-modal-backdrop')) {
                startRun();
            }
        });
    }
});
