// Solo modu: Oyuncu Tahmin Et (kariyer geçmişinden tahmin)

// ===== State =====
let currentQuiz = null;
let quizLeague = localStorage.getItem('solo_league') || 'ALL';
let quizRecognition = localStorage.getItem('solo_recognition') || 'known';
let quizOptions = null;
let quizOptionsPromise = null;
let quizLives = 0;
let hintsUsed = 0;
// Run (koşu) durumu: 8 can tüm koşu boyunca paylaşılır, yanlışta kalıcı azalır.
let runStreak = 0;   // mevcut seri (atlanınca sıfırlanır, doğruda artar)
let runMax = 0;      // koşudaki en yüksek seri
let runTotal = 0;    // koşuda doğru bilinen futbolcu sayısı
let runActive = false;
const MAX_LIVES = 8;

function effectiveRecognition() {
    return selectedLeague()?.uses_recognition === false ? 'all' : quizRecognition;
}

// ===== Retention: localStorage istatistikleri =====
function getSoloStats() {
    const key = `solo_best_streak:${quizLeague}:${effectiveRecognition()}`;
    const legacyBest = quizLeague === 'ALL' && quizRecognition === 'known'
        ? localStorage.getItem('solo_best_streak')
        : null;
    return {
        best:   parseInt(localStorage.getItem(key) || legacyBest || '0', 10),
        total:  runTotal,                                                        // KOŞU-İÇİ toplam doğru (can bitince sıfır)
        streak: runStreak,                                                       // mevcut koşunun serisi (bellek)
    };
}
function setSoloStats(s) {
    localStorage.setItem(
        `solo_best_streak:${quizLeague}:${effectiveRecognition()}`,
        String(s.best),
    );
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
async function startRun() {
    quizLives = MAX_LIVES;
    runStreak = 0;
    runMax = 0;
    runTotal = 0;
    runActive = true;
    document.getElementById('solo-setup').hidden = true;
    document.getElementById('solo-active-filter').hidden = false;
    updateActiveFilter();
    await loadQuiz();
}
async function newRound() {
    if (!runActive) { await startSelectedRun(); return; }
    resetRunStreak();                          // gönüllü geçiş seriyi kırar (can harcanmaz)
    await loadQuiz();
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
    try {
        return JSON.parse(
            localStorage.getItem(`solo_seen:${quizLeague}:${effectiveRecognition()}`) || '[]'
        );
    }
    catch (_) { return []; }
}
function pushSeen(id) {
    if (!id) return;
    const list = getSeen().filter(x => x !== id);
    list.unshift(id);
    localStorage.setItem(
        `solo_seen:${quizLeague}:${effectiveRecognition()}`,
        JSON.stringify(list.slice(0, SEEN_WINDOW)),
    );
}

// ===== Quiz =====
function leagueLabel(league) {
    if (!league) return quizLeague;
    if (league.id === 'ALL') return t('all_leagues');
    if (league.id === 'LEGENDS') return t('career_legends');
    if (currentLang === 'tr' && typeof LEAGUE_NAMES !== 'undefined') {
        return LEAGUE_NAMES[league.id] || league.name;
    }
    return league.name;
}

function recognitionLabel(recognition) {
    return t(recognition);
}

function selectedLeague() {
    return quizOptions?.leagues?.find(league => league.id === quizLeague) || null;
}

function renderQuizOptions() {
    if (!quizOptions) return;
    const select = document.getElementById('solo-league-select');
    const previous = quizLeague;
    select.innerHTML = '';
    quizOptions.leagues.forEach(league => {
        const option = document.createElement('option');
        option.value = league.id;
        option.textContent = leagueLabel(league);
        select.appendChild(option);
    });
    if (!quizOptions.leagues.some(league => league.id === previous)) {
        quizLeague = 'ALL';
    }
    select.value = quizLeague;
    renderRecognitionCounts();
    updateActiveFilter();
}

function renderRecognitionCounts() {
    const league = selectedLeague();
    if (!league) return;
    const usesRecognition = league.uses_recognition !== false;
    const poolControl = document.getElementById('solo-pool-control');
    if (poolControl) poolControl.hidden = !usesRecognition;
    document.querySelector('.solo-control-bar')?.classList.toggle(
        'without-recognition', !usesRecognition
    );
    document.querySelectorAll('#recognition-selector button').forEach(button => {
        const recognition = button.dataset.recognition;
        const count = Number(league.counts?.[recognition] || 0);
        const countEl = document.getElementById(`recognition-count-${recognition}`);
        if (countEl) countEl.textContent = `${count} ${t('player_count')}`;
        button.disabled = count === 0;
        button.classList.toggle('active', recognition === quizRecognition);
    });
    if (!league.counts?.[quizRecognition]) {
        const fallback = quizOptions.recognitions.find(key => league.counts?.[key] > 0);
        if (fallback) quizRecognition = fallback;
    }
    document.querySelectorAll('#recognition-selector button').forEach(button => {
        button.classList.toggle('active', button.dataset.recognition === quizRecognition);
    });
    document.getElementById('solo-start-btn').disabled = usesRecognition
        ? !Number(league.counts?.[quizRecognition] || 0)
        : !Number(league.total_count || 0);
}

async function initializeQuizOptions() {
    if (quizOptions) {
        renderQuizOptions();
        return quizOptions;
    }
    if (!quizOptionsPromise) {
        quizOptionsPromise = safeFetch('/api/quiz/options')
            .then(options => {
                quizOptions = options;
                renderQuizOptions();
                return options;
            })
            .catch(error => {
                quizOptionsPromise = null;
                document.getElementById('quiz-area').innerHTML = `<div class="error-card">
                    <p>${t('quiz_load_error')}</p>
                    <button class="btn btn-primary" onclick="initializeQuizOptions()">${t('retry')}</button>
                </div>`;
                throw error;
            });
    }
    return quizOptionsPromise;
}

function setQuizLeague(league) {
    quizLeague = league;
    localStorage.setItem('solo_league', league);
    renderRecognitionCounts();
    renderSoloStats();
}

function setRecognition(recognition, button) {
    if (button?.disabled) return;
    quizRecognition = recognition;
    localStorage.setItem('solo_recognition', recognition);
    document.querySelectorAll('#recognition-selector button').forEach(item => {
        item.classList.toggle('active', item === button);
    });
    renderSoloStats();
}

function updateActiveFilter() {
    const name = document.getElementById('solo-active-filter-name');
    if (!name || !quizOptions) return;
    const league = selectedLeague();
    name.textContent = league?.uses_recognition === false
        ? leagueLabel(league)
        : `${leagueLabel(league)} / ${recognitionLabel(quizRecognition)}`;
}

async function startSelectedRun() {
    await initializeQuizOptions();
    const league = selectedLeague();
    const playerCount = league?.uses_recognition === false
        ? league.total_count
        : league?.counts?.[quizRecognition];
    if (!playerCount) return;
    localStorage.setItem('solo_league', quizLeague);
    localStorage.setItem('solo_recognition', quizRecognition);
    await startRun();
}

function changeSoloSelection() {
    runActive = false;
    currentQuiz = null;
    runStreak = 0;
    runMax = 0;
    runTotal = 0;
    document.getElementById('solo-setup').hidden = false;
    document.getElementById('solo-active-filter').hidden = true;
    document.getElementById('quiz-input-row').style.display = 'none';
    document.getElementById('quiz-lives').style.display = 'none';
    document.getElementById('quiz-hint-reveal').style.display = 'none';
    document.getElementById('hint-btn').disabled = true;
    document.getElementById('skip-btn').disabled = true;
    document.getElementById('quiz-wrong-feedback').innerHTML = '';
    document.getElementById('quiz-area').innerHTML = `<div class="empty-state">
        <span>${t('start_prompt')}</span>
    </div>`;
    renderSoloStats();
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
        const recognition = selectedLeague()?.uses_recognition === false
            ? ''
            : '&recognition=' + encodeURIComponent(quizRecognition);
        currentQuiz = await safeFetch(
            '/api/quiz?league=' + encodeURIComponent(quizLeague)
            + recognition + exclude
        );
        pushSeen(currentQuiz.player_id);
    } catch (e) {
        document.getElementById('skip-btn').disabled = true;
        area.innerHTML = `<div class="error-card">
            <p>${t('quiz_load_error')}</p>
            <button class="btn btn-primary" onclick="loadQuiz()">${t('retry')}</button>
        </div>`;
        return;
    }

    renderQuizArea();
    if (window.matchMedia('(min-width: 769px) and (pointer: fine)').matches) {
        document.getElementById('quiz-guess').focus();
    }
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
                <div class="info-code">POS</div>
                <div class="info-text">
                    <div class="info-label">${t('position')}</div>
                    <div class="info-value">${esc(posText(currentQuiz.position))}</div>
                </div>
            </div>
            <div class="info-cell">
                <div class="info-code">NAT</div>
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
                    <div class="retirement-badge">R</div>
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

    attachSearchKeys(quizInput, quizDropdown, submitGuess);
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

    lastResult = {
        player: p,
        correct,
        recordInfo,
        league: quizLeague,
        recognition: quizRecognition,
    };
    renderResultModal();

    selectedGuessId = null;
    currentQuiz = null;

    if (correct) fireConfetti();
}

function renderResultModal() {
    if (!lastResult) return;
    const { player: p, correct, recordInfo, league, recognition } = lastResult;

    const existing = document.getElementById('quiz-modal-backdrop');
    if (existing) existing.remove();

    const stats = getSoloStats();
    const career = (p.clubs || []).filter(club => !club.is_retirement);
    const uniqueClubCount = new Set(career.map(club => club.name)).size;
    const careerYears = career
        .flatMap(club => [club.date_from, club.date_to])
        .filter(Boolean)
        .map(value => value.substring(0, 4))
        .sort();
    const firstYear = careerYears[0] || '—';
    const hasCurrentClub = career.some(club => !club.date_to);
    const lastYear = hasCurrentClub
        ? t('ongoing')
        : (careerYears[careerYears.length - 1] || '—');
    const careerSpan = firstYear === '—' ? '—' : `${firstYear} – ${lastYear}`;
    const lastClub = career[career.length - 1]?.name || '—';
    const selected = quizOptions?.leagues?.find(item => item.id === league);
    const poolName = selected?.uses_recognition === false
        ? leagueLabel(selected)
        : `${leagueLabel(selected)} / ${recognitionLabel(recognition)}`;
    const statItems = [
        [stats.streak, t('solo_streak'), ''],
        [stats.best, t('solo_record'), recordInfo?.newRecord ? 'record' : ''],
        [stats.total, t('solo_total_correct'), ''],
    ];
    const statsHtml = correct ? `
        <div class="rm-stats">
            ${statItems.map(([value, label, className]) => `
                <div class="rm-stat ${className}">
                    <div class="rm-stat-val">${value}</div>
                    <div class="rm-stat-lbl">${label}</div>
                    ${className ? `<div class="rm-stat-note">${t('result_new_record')}</div>` : ''}
                </div>`).join('')}
        </div>` : '';

    const title = correct
        ? `${t('quiz_correct_title')} <span class="accent">${t('quiz_correct_accent')}</span>`
        : t('result_skipped_title');
    const sub = correct ? t('quiz_correct_sub') : t('result_skipped_sub');

    const backdrop = document.createElement('div');
    backdrop.className = 'quiz-modal-backdrop';
    backdrop.id = 'quiz-modal-backdrop';
    backdrop.innerHTML = `
        <div class="result-modal solo-result-modal ${correct ? 'correct' : 'skipped'}">
            <header class="rm-result-head">
                <div>
                    <div class="rm-result-kicker">${t(correct ? 'result_solved_kicker' : 'result_skipped_kicker')}</div>
                    <h2 class="rm-title">${title}</h2>
                    <p class="rm-sub">${esc(sub)}</p>
                </div>
                <div class="rm-outcome-code" aria-hidden="true">${correct ? '&#10003;' : '&rarr;'}</div>
            </header>

            <section class="rm-player-profile">
                <div class="rm-photo-wrap">
                    <span class="rm-photo-fallback" aria-hidden="true">PLY</span>
                    <img class="rm-photo" src="${p.image_url || ''}" onerror="this.style.display='none'" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">
                </div>
                <div class="rm-player-copy">
                    <div class="rm-section-label">${t('result_answer_label')}</div>
                    <div class="rm-name">${esc(p.name)}</div>
                    <div class="rm-pills">
                        <span class="rm-pill">${esc(posText(p.position))}</span>
                        <span class="rm-pill">${flagHtml(p.country, true)} ${esc(p.country || '?')}</span>
                    </div>
                </div>
            </section>

            <section class="rm-quick-facts" aria-label="${esc(t('result_career_summary'))}">
                <div class="rm-fact">
                    <span>${t('result_club_count')}</span>
                    <strong>${uniqueClubCount}</strong>
                </div>
                <div class="rm-fact">
                    <span>${t('result_career_span')}</span>
                    <strong>${esc(careerSpan)}</strong>
                </div>
                <div class="rm-fact">
                    <span>${t('result_last_club')}</span>
                    <strong>${esc(lastClub)}</strong>
                </div>
            </section>

            ${statsHtml}

            <div class="rm-pool-line">
                <span>${t('result_pool')}</span>
                <strong>${esc(poolName)}</strong>
            </div>

            <div class="rm-result-actions">
                <button class="btn btn-primary rm-next" onclick="closeQuizModalAndNext()">
                    <span>${t('quiz_next_player')}</span><span class="rm-arrow">&rarr;</span>
                </button>
                <button class="btn rm-change-pool" onclick="closeQuizModalAndChangeSelection()">
                    ${t('result_change_pool')}
                </button>
            </div>
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
            <div class="rm-check">&times;</div>
            <h2 class="rm-title">${t('multi_game_over')}</h2>
            <p class="rm-sub">${t('game_over_missed')}</p>
            <img class="rm-photo" src="${p.image_url || ''}" onerror="this.style.display='none'" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">
            <div class="rm-name">${esc(p.name)}</div>
            <div class="rm-stats">
                <div class="rm-stat">
                    <div class="rm-stat-meta"><div class="rm-stat-val">${mx}</div><div class="rm-stat-lbl">${t('run_max_streak')}</div></div>
                </div>
                <div class="rm-stat">
                    <div class="rm-stat-meta"><div class="rm-stat-val">${tot}</div><div class="rm-stat-lbl">${t('solo_total_correct')}</div></div>
                </div>
            </div>
            <button class="btn btn-primary rm-next" onclick="restartRun()">
                <span>${t('new_run')}</span>
            </button>
            <button class="btn rm-share" onclick="shareRunResult()">${t('share_result')}</button>
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

function closeQuizModalAndChangeSelection() {
    const backdrop = document.getElementById('quiz-modal-backdrop');
    if (backdrop) backdrop.remove();
    lastResult = null;
    changeSoloSelection();
}

// Dil değişince solo görünümünü yeniden çiz: aktif quiz alanı, son tahminler
// paneli ve (açıksa) sonuç modalı t() ile kurulduğundan tazelenmeli.
window.addEventListener('langchange', () => {
    renderRecent();
    renderQuizArea();
    renderQuizOptions();
    updateActiveFilter();
    if (document.getElementById('quiz-modal-backdrop')) {
        lastResult?.gameOver ? renderGameOverModal() : renderResultModal();
    }
});

// ===== Init =====
setupQuizSearch();

window.addEventListener('DOMContentLoaded', () => {
    renderSoloStats();
    renderRecent();
    if (typeof onRoute === 'function') {
        onRoute((route) => {
            if (route.name === 'solo') {
                initializeQuizOptions().catch(() => {});
                if (runActive) {
                    document.getElementById('solo-setup').hidden = true;
                    document.getElementById('solo-active-filter').hidden = false;
                    updateActiveFilter();
                }
            }
        });
    }
});
