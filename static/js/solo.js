// Solo modu: Ortak Oyuncu Bul + Tahmin Oyunu

// ===== State =====
let selectedClub1 = null;
let selectedClub2 = null;
let currentQuiz = null;
let quizDifficulty = 'easy';
let quizCorrect = 0;
let quizTotal = 0;
let quizLives = 0;
const MAX_LIVES = 8;
let debounceTimer = null;

// ===== Solo alt-sekme geçişi =====
function showSoloTab(tab, btn) {
    document.querySelectorAll('#page-solo .solo-tab').forEach(p => p.classList.remove('active'));
    document.getElementById('solo-' + tab).classList.add('active');
    document.querySelectorAll('#page-solo .sub-nav button').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
}

// ===== Kulüp Arama =====
function setupSearch(inputId, dropdownId, onSelect) {
    const input = document.getElementById(inputId);
    const dropdown = document.getElementById(dropdownId);
    if (!input || !dropdown) return;

    input.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const q = input.value.trim();
        if (q.length < 2) { dropdown.classList.remove('show'); return; }

        debounceTimer = setTimeout(async () => {
            const res = await fetch('/api/search-club?q=' + encodeURIComponent(q));
            const clubs = await res.json();
            if (clubs.length === 0) {
                dropdown.innerHTML = `<div style="padding:0.8rem;color:var(--text-dim)">${t('no_result')}</div>`;
            } else {
                dropdown.innerHTML = clubs.map(c => `
                    <div class="dropdown-item" data-id="${c.club_id}" data-name="${esc(c.name)}" data-logo="${c.logo_url || ''}">
                        <img src="${c.logo_url || ''}" onerror="this.style.display='none'" alt="">
                        <span>${esc(c.name)}</span>
                    </div>
                `).join('');
            }
            dropdown.classList.add('show');
            dropdown.querySelectorAll('.dropdown-item').forEach(item => {
                item.addEventListener('click', () => {
                    const club = { club_id: parseInt(item.dataset.id), name: item.dataset.name, logo_url: item.dataset.logo };
                    input.value = club.name;
                    input.classList.add('selected');
                    dropdown.classList.remove('show');
                    onSelect(club);
                });
            });
        }, 250);
    });

    input.addEventListener('focus', () => {
        if (input.classList.contains('selected')) {
            input.value = '';
            input.classList.remove('selected');
            onSelect(null);
        }
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-wrapper')) dropdown.classList.remove('show');
    });
}

function updateFindBtn() {
    const btn = document.getElementById('find-btn');
    if (btn) btn.disabled = !(selectedClub1 && selectedClub2);
}

// ===== Ortak Oyuncular =====
async function findCommon() {
    if (!selectedClub1 || !selectedClub2) return;
    const results = document.getElementById('common-results');
    results.innerHTML = `<div class="loading"><div class="spinner"></div><div>${t('searching')}</div></div>`;

    const res = await fetch(`/api/common-players?club1=${selectedClub1.club_id}&club2=${selectedClub2.club_id}`);
    const data = await res.json();

    const headerHtml = `
        <div class="results-header">
            <div class="club-badge"><img src="${selectedClub1.logo_url}" onerror="this.style.display='none'" alt=""><span>${esc(selectedClub1.name)}</span></div>
            <span class="vs">&amp;</span>
            <div class="club-badge"><img src="${selectedClub2.logo_url}" onerror="this.style.display='none'" alt=""><span>${esc(selectedClub2.name)}</span></div>
        </div>`;

    if (data.players.length === 0) {
        results.innerHTML = headerHtml + `<div class="no-results">${t('no_common')}</div>`;
        return;
    }

    let html = headerHtml + `<div class="count-badge"><strong>${data.count}</strong> ${t('common_found')}</div>`;
    data.players.forEach((p, i) => {
        html += `
            <div class="player-card" style="animation-delay:${Math.min(i * 40, 800)}ms">
                <img src="${p.image_url || ''}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><rect fill=%22%23242734%22 width=%2240%22 height=%2240%22/><text x=%2220%22 y=%2224%22 text-anchor=%22middle%22 fill=%22%238b8fa3%22 font-size=%2216%22>?</text></svg>'" alt="">
                <div class="player-info">
                    <div class="name">${esc(p.name)}</div>
                    <div class="meta">${posText(p.position)} · ${esc(p.country || '')}</div>
                </div>
            </div>`;
    });
    results.innerHTML = html;
}

// ===== Quiz =====
function setDifficulty(diff, btn) {
    quizDifficulty = diff;
    document.querySelectorAll('#solo-quiz .difficulty-selector button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
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
    if (dfrom && dto) return (dfrom === dto) ? dfrom : `${dfrom} - ${dto}`;
    if (dfrom && !dto) return `${dfrom} - ${t('ongoing')}`;
    if (!dfrom && dto) return `${dto}${t('until')}`;
    return '';
}

async function loadQuiz() {
    const area = document.getElementById('quiz-area');
    area.innerHTML = `<div class="loading"><div class="spinner"></div><div>${t('loading')}</div></div>`;

    quizLives = MAX_LIVES;
    document.getElementById('quiz-wrong-feedback').innerHTML = '';
    document.getElementById('quiz-input-row').style.display = 'flex';
    document.getElementById('quiz-pass-btn').style.display = 'block';
    document.getElementById('quiz-start-btn').style.display = 'none';
    document.getElementById('quiz-guess').value = '';
    document.getElementById('quiz-guess').focus();

    renderLives(false);

    const res = await fetch('/api/quiz?difficulty=' + quizDifficulty);
    currentQuiz = await res.json();

    let html = `
        <div class="quiz-hints">
            <div class="hint-tag"><span class="hint-label">${t('position')}</span><span class="hint-value">${esc(posText(currentQuiz.position))}</span></div>
            <div class="hint-tag"><span class="hint-label">${t('nationality')}</span><span class="hint-value">${flagHtml(currentQuiz.country, true)}${esc(currentQuiz.country || '?')}</span></div>
        </div>
        <div class="quiz-timeline">`;

    currentQuiz.clubs.forEach((c, i) => {
        html += `
            <div class="timeline-item" style="animation-delay:${Math.min(i * 70, 700)}ms">
                ${c.logo_url ? `<img src="${c.logo_url}" onerror="this.style.display='none'" alt="">` : ''}
                <div class="timeline-info">
                    <div class="club-name">${esc(c.name)}</div>
                    <div class="club-dates">${formatDate(c)}</div>
                </div>
            </div>`;
    });
    html += '</div>';
    area.innerHTML = html;
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
                quizDropdown.innerHTML = players.map(p => `
                    <div class="dropdown-player" data-id="${p.player_id}" data-name="${esc(p.name)}">
                        <img src="${p.image_url || ''}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><rect fill=%22%23242734%22 width=%2240%22 height=%2240%22/><text x=%2220%22 y=%2224%22 text-anchor=%22middle%22 fill=%22%238b8fa3%22 font-size=%2216%22>?</text></svg>'" alt="">
                        <div class="dp-info">
                            <div class="dp-name">${esc(p.name)}</div>
                            <div class="dp-meta">${posText(p.position)} · ${esc(p.country || '')}</div>
                        </div>
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
        quizCorrect++;
        quizTotal++;
        showQuizResult(true);
    } else {
        quizLives--;
        renderLives(true);
        selectedGuessId = null;

        if (quizLives <= 0) {
            quizTotal++;
            document.getElementById('quiz-wrong-feedback').innerHTML = '';
            showQuizResult(false);
        } else {
            document.getElementById('quiz-wrong-feedback').innerHTML =
                `<div class="wrong-guess">${t('wrong_guess')} ${quizLives} ${t('lives_left')}</div>`;
            quizInput.value = '';
            quizInput.focus();
        }
    }
}

function passQuiz() {
    if (!currentQuiz) return;
    const quizDropdown = document.getElementById('quiz-player-dropdown');
    quizDropdown.classList.remove('show');
    quizTotal++;
    document.getElementById('quiz-wrong-feedback').innerHTML = '';
    showQuizResult(false);
}

function showQuizResult(correct) {
    const p = currentQuiz;

    document.getElementById('quiz-input-row').style.display = 'none';
    document.getElementById('quiz-pass-btn').style.display = 'none';
    document.getElementById('quiz-lives').style.display = 'none';
    document.getElementById('quiz-start-btn').style.display = 'none';

    const scoreEl = document.getElementById('quiz-score');
    scoreEl.style.display = 'block';
    document.getElementById('score-correct').textContent = quizCorrect;
    document.getElementById('score-total').textContent = quizTotal;

    const existing = document.getElementById('quiz-modal-backdrop');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.className = 'quiz-modal-backdrop';
    backdrop.id = 'quiz-modal-backdrop';
    backdrop.innerHTML = `
        <div class="quiz-result ${correct ? 'correct' : 'wrong'}">
            <img class="player-photo" src="${p.image_url || ''}" onerror="this.style.display='none'" alt="">
            <div class="verdict">${correct ? t('correct') : t('wrong')}</div>
            <div class="answer-name">${esc(p.name)}</div>
            <div class="answer-meta">
                <span class="meta-pill">${esc(posText(p.position))}</span>
                <span class="meta-pill">${esc(p.country || '?')}</span>
            </div>
            <button class="btn btn-primary next-btn" onclick="closeQuizModalAndNext()">${t('next_question')}</button>
        </div>`;
    document.body.appendChild(backdrop);

    selectedGuessId = null;
    currentQuiz = null;

    if (correct) fireConfetti();
}

function closeQuizModalAndNext() {
    const backdrop = document.getElementById('quiz-modal-backdrop');
    if (backdrop) backdrop.remove();
    loadQuiz();
}

// ===== Init =====
setupSearch('club1-input', 'club1-dropdown', (club) => { selectedClub1 = club; updateFindBtn(); });
setupSearch('club2-input', 'club2-dropdown', (club) => { selectedClub2 = club; updateFindBtn(); });
setupQuizSearch();
