// Ortak yardımcılar (solo + multi paylaşır)

// ===== i18n =====
const LANGS = {
    tr: {
        nav_menu: 'Ana Menü',
        nav_common: 'Ortak Oyuncu',
        nav_quiz: 'Tahmin Oyunu',
        nav_multi: 'Çok Kişilik',
        app_title: 'Futbol Quiz',
        app_subtitle: 'Ne oynamak istersin?',
        multi_soon: 'Çok kişilik modu yakında geliyor.',
        common_title: 'Ortak Oyuncu Bul',
        common_subtitle: 'İki takım seç, her ikisinde de oynamış oyuncuları bul',
        team1: '1. Takım',
        team2: '2. Takım',
        search_team: 'Takım adı yaz...',
        find_common: 'Ortak Oyuncuları Bul',
        quiz_title: 'Oyuncu Tahmin Et',
        quiz_subtitle: 'Kulüp geçmişine bakarak oyuncuyu tahmin et',
        easy: 'Kolay',
        medium: 'Orta',
        hard: 'Zor',
        score: 'Skor',
        start_prompt: 'Başlamak için aşağıdaki butona tıkla',
        guess_placeholder: 'Oyuncu adını yaz...',
        guess_btn: 'Tahmin Et',
        new_question: 'Yeni Soru',
        next_question: 'Sonraki Soru',
        pass: 'Pas Geç',
        no_result: 'Sonuç bulunamadı',
        no_player: 'Oyuncu bulunamadı',
        no_common: 'Bu iki takımda oynamış ortak oyuncu bulunamadı.',
        common_found: 'ortak oyuncu bulundu',
        searching: 'Aranıyor...',
        loading: 'Soru yükleniyor...',
        correct: 'Doğru!',
        wrong: 'Yanlış!',
        wrong_guess: 'Yanlış tahmin!',
        lives_left: 'hak kaldı',
        position: 'Mevki',
        nationality: 'Milliyet',
        ongoing: 'Devam ediyor',
        until: "'a kadar",
        pos_attack: 'Forvet',
        pos_midfield: 'Orta Saha',
        pos_defender: 'Defans',
        pos_goalkeeper: 'Kaleci',
        // Menu
        menu_solo_title: 'Solo Oyun',
        menu_solo_desc: 'Ortak oyuncu bul veya tek başına oyuncu tahmin et',
        menu_multi_title: 'Çok Kişilik Oyun',
        menu_multi_desc: '2-8 kişilik lobide arkadaşlarınla yarış',
        // Multi
        multi_title: 'Çok Kişilik',
        multi_subtitle: 'Arkadaşlarınla gerçek zamanlı yarış',
        multi_create: 'Lobi Kur',
        multi_join: 'Koda Katıl',
        multi_create_desc: 'Yeni bir lobi aç ve arkadaşlarını davet et',
        multi_join_desc: 'Sana verilen 6 haneli kodla lobiye katıl',
        multi_create_hint: 'Oyun ayarlarını seç, lobi kodun otomatik üretilir',
        multi_join_hint: 'Lobi sahibinden aldığın kodu yaz',
        multi_target_hint: '3 ile 50 arasında bir sayı seç',
        multi_nickname: 'Takma ad',
        multi_nickname_ph: 'Takma ad gir...',
        multi_code: 'Lobi kodu',
        multi_code_ph: 'Kod gir (6 karakter)',
        multi_back: '← Geri',
        multi_lobby_code: 'Lobi kodu',
        multi_lobby_hint: 'Arkadaşlarına bu kodu gönder',
        multi_mode: 'Cevap modu',
        multi_mode_mc: '4 Şıklı',
        multi_mode_free: 'Serbest Yazma',
        multi_difficulty: 'Zorluk',
        multi_target: 'Hedef puan',
        multi_start: 'Oyunu Başlat',
        multi_leave: 'Lobiden Çık',
        multi_waiting: 'Host oyunu başlatmayı bekliyor...',
        multi_min_players: 'Başlatmak için en az 2 oyuncu gerekli',
        multi_round: 'Tur',
        multi_already_answered: 'Cevabın alındı. Diğer oyuncular bekleniyor...',
        multi_round_result: 'Tur Sonucu',
        multi_free_correct: 'Doğru cevap!',
        multi_free_wrong: 'Yanlış cevap',
        multi_free_no_answer: 'Süre doldu',
        multi_free_no_answer_hint: 'Bu turda cevap göndermedin',
        multi_free_correct_count: 'oyuncu doğru bildi',
        multi_game_over: 'Oyun Bitti',
        multi_winner: 'Kazanan',
        multi_rematch: 'Yeniden Oyna',
        multi_to_menu: 'Ana Menüye',
        multi_redirect_hint: 'saniye sonra lobi girişine döneceksin...',
        multi_host_left: 'Host ayrıldı, yeni host atandı',
        multi_error_invalid_code: 'Geçersiz lobi kodu',
        multi_error_full: 'Lobi dolu',
        multi_error_in_game: 'Oyun zaten başladı',
        multi_connecting: 'Bağlanıyor...',
        multi_disconnected: 'Bağlantı koptu, yeniden bağlanıyor...',
    },
    en: {
        nav_menu: 'Main Menu',
        nav_common: 'Common Player',
        nav_quiz: 'Guess Game',
        nav_multi: 'Multiplayer',
        app_title: 'Football Quiz',
        app_subtitle: 'What do you want to play?',
        multi_soon: 'Multiplayer mode coming soon.',
        common_title: 'Find Common Players',
        common_subtitle: 'Pick two teams and find players who played for both',
        team1: 'Team 1',
        team2: 'Team 2',
        search_team: 'Type team name...',
        find_common: 'Find Common Players',
        quiz_title: 'Guess the Player',
        quiz_subtitle: 'Guess the player from their club history',
        easy: 'Easy',
        medium: 'Medium',
        hard: 'Hard',
        score: 'Score',
        start_prompt: 'Click the button below to start',
        guess_placeholder: 'Type player name...',
        guess_btn: 'Guess',
        new_question: 'New Question',
        next_question: 'Next Question',
        pass: 'Pass',
        no_result: 'No results found',
        no_player: 'Player not found',
        no_common: 'No common players found for these two teams.',
        common_found: 'common players found',
        searching: 'Searching...',
        loading: 'Loading question...',
        correct: 'Correct!',
        wrong: 'Wrong!',
        wrong_guess: 'Wrong guess!',
        lives_left: 'lives left',
        position: 'Position',
        nationality: 'Nationality',
        ongoing: 'Present',
        until: ' until',
        pos_attack: 'Forward',
        pos_midfield: 'Midfielder',
        pos_defender: 'Defender',
        pos_goalkeeper: 'Goalkeeper',
        menu_solo_title: 'Solo Play',
        menu_solo_desc: 'Find common players or guess on your own',
        menu_multi_title: 'Multiplayer',
        menu_multi_desc: 'Compete with 2-8 friends in real time',
        multi_title: 'Multiplayer',
        multi_subtitle: 'Real-time competition with friends',
        multi_create: 'Create Lobby',
        multi_join: 'Join by Code',
        multi_create_desc: 'Open a new lobby and invite your friends',
        multi_join_desc: 'Join with the 6-character code you were given',
        multi_create_hint: 'Pick game settings; your lobby code is generated',
        multi_join_hint: 'Enter the code from the lobby host',
        multi_target_hint: 'Pick a number between 3 and 50',
        multi_nickname: 'Nickname',
        multi_nickname_ph: 'Enter a nickname...',
        multi_code: 'Lobby code',
        multi_code_ph: 'Enter code (6 chars)',
        multi_back: '← Back',
        multi_lobby_code: 'Lobby code',
        multi_lobby_hint: 'Share this code with your friends',
        multi_mode: 'Answer mode',
        multi_mode_mc: '4-Choice',
        multi_mode_free: 'Free type',
        multi_difficulty: 'Difficulty',
        multi_target: 'Target score',
        multi_start: 'Start Game',
        multi_leave: 'Leave Lobby',
        multi_waiting: 'Waiting for host to start...',
        multi_min_players: 'Need at least 2 players to start',
        multi_round: 'Round',
        multi_already_answered: 'Your answer is in. Waiting for others...',
        multi_round_result: 'Round Result',
        multi_free_correct: 'Correct!',
        multi_free_wrong: 'Wrong answer',
        multi_free_no_answer: "Time's up",
        multi_free_no_answer_hint: "You didn't submit an answer",
        multi_free_correct_count: 'players got it right',
        multi_game_over: 'Game Over',
        multi_winner: 'Winner',
        multi_rematch: 'Rematch',
        multi_to_menu: 'Main Menu',
        multi_redirect_hint: 'seconds until you return to the lobby menu...',
        multi_host_left: 'Host left, new host assigned',
        multi_error_invalid_code: 'Invalid lobby code',
        multi_error_full: 'Lobby is full',
        multi_error_in_game: 'Game already in progress',
        multi_connecting: 'Connecting...',
        multi_disconnected: 'Disconnected, reconnecting...',
    }
};

let currentLang = localStorage.getItem('lang') || 'tr';

function t(key) { return LANGS[currentLang][key] || key; }

function toggleLang() {
    currentLang = currentLang === 'tr' ? 'en' : 'tr';
    localStorage.setItem('lang', currentLang);
    const toggle = document.querySelector('.lang-toggle');
    if (toggle) toggle.textContent = currentLang === 'tr' ? 'EN' : 'TR';
    applyLang();
}

function applyLang() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        el.textContent = t(el.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        el.placeholder = t(el.dataset.i18nPlaceholder);
    });
}

function posText(pos) {
    const map = { 'Attack': t('pos_attack'), 'Midfield': t('pos_midfield'), 'Defender': t('pos_defender'), 'Goalkeeper': t('pos_goalkeeper') };
    return map[pos] || pos || '?';
}

// ===== Ülke kodları =====
const COUNTRY_CODES = {
    'Brazil': 'br', 'France': 'fr', 'Spain': 'es', 'Italy': 'it', 'Germany': 'de',
    'England': 'gb-eng', 'Wales': 'gb-wls', 'Scotland': 'gb-sct', 'Northern Ireland': 'gb-nir',
    'Ireland': 'ie', 'Republic of Ireland': 'ie', 'United Kingdom': 'gb',
    'Netherlands': 'nl', 'Belgium': 'be', 'Portugal': 'pt',
    'Argentina': 'ar', 'Uruguay': 'uy', 'Chile': 'cl', 'Colombia': 'co',
    'Mexico': 'mx', 'United States': 'us', 'USA': 'us', 'Canada': 'ca',
    'Peru': 'pe', 'Ecuador': 'ec', 'Venezuela': 've', 'Paraguay': 'py', 'Bolivia': 'bo',
    'Costa Rica': 'cr', 'Panama': 'pa', 'Honduras': 'hn', 'Jamaica': 'jm',
    'Czech Republic': 'cz', 'Czechia': 'cz', 'Slovakia': 'sk', 'Poland': 'pl',
    'Ukraine': 'ua', 'Russia': 'ru', 'Belarus': 'by',
    'Croatia': 'hr', 'Serbia': 'rs', 'Bosnia-Herzegovina': 'ba', 'Bosnia and Herzegovina': 'ba',
    'Slovenia': 'si', 'North Macedonia': 'mk', 'Macedonia': 'mk', 'Montenegro': 'me', 'Albania': 'al', 'Kosovo': 'xk',
    'Sweden': 'se', 'Norway': 'no', 'Denmark': 'dk', 'Finland': 'fi', 'Iceland': 'is',
    'Switzerland': 'ch', 'Austria': 'at', 'Hungary': 'hu', 'Romania': 'ro', 'Bulgaria': 'bg', 'Greece': 'gr',
    'Türkiye': 'tr', 'Turkey': 'tr', 'Cyprus': 'cy',
    'Iran': 'ir', 'Iraq': 'iq', 'Saudi Arabia': 'sa', 'United Arab Emirates': 'ae',
    'Qatar': 'qa', 'Kuwait': 'kw', 'Bahrain': 'bh', 'Oman': 'om', 'Jordan': 'jo',
    'Lebanon': 'lb', 'Syria': 'sy', 'Israel': 'il', 'Palestine': 'ps',
    'Egypt': 'eg', 'Morocco': 'ma', 'Algeria': 'dz', 'Tunisia': 'tn', 'Libya': 'ly',
    'Senegal': 'sn', 'Nigeria': 'ng', 'Ghana': 'gh', 'Mali': 'ml', 'Cameroon': 'cm',
    'Ivory Coast': 'ci', "Cote d'Ivoire": 'ci',
    'South Africa': 'za', 'Kenya': 'ke', 'Ethiopia': 'et', 'Sudan': 'sd',
    'Congo DR': 'cd', 'DR Congo': 'cd', 'Congo': 'cg', 'Gabon': 'ga', 'Angola': 'ao',
    'Burkina Faso': 'bf', 'Guinea': 'gn', 'Togo': 'tg', 'Benin': 'bj', 'Zambia': 'zm', 'Zimbabwe': 'zw',
    'Cape Verde': 'cv', 'Mauritania': 'mr', 'Niger': 'ne', 'Madagascar': 'mg',
    'Japan': 'jp', 'South Korea': 'kr', 'Korea, South': 'kr', 'North Korea': 'kp',
    'China': 'cn', "China PR": 'cn', 'Australia': 'au', 'New Zealand': 'nz',
    'Indonesia': 'id', 'Malaysia': 'my', 'Singapore': 'sg', 'Thailand': 'th', 'Vietnam': 'vn',
    'Philippines': 'ph', 'India': 'in', 'Pakistan': 'pk', 'Bangladesh': 'bd',
    'Uzbekistan': 'uz', 'Kazakhstan': 'kz', 'Azerbaijan': 'az', 'Armenia': 'am', 'Georgia': 'ge',
    'Estonia': 'ee', 'Latvia': 'lv', 'Lithuania': 'lt', 'Moldova': 'md',
    'Luxembourg': 'lu', 'Malta': 'mt', 'San Marino': 'sm', 'Andorra': 'ad', 'Liechtenstein': 'li',
    'Faroe Islands': 'fo', 'Gibraltar': 'gi'
};

function flagHtml(country, large) {
    if (!country) return '';
    const code = COUNTRY_CODES[country];
    if (!code) return '';
    const cls = large ? 'flag-img flag-lg' : 'flag-img';
    return `<img class="${cls}" src="https://flagcdn.com/w40/${code}.png" srcset="https://flagcdn.com/w80/${code}.png 2x" alt="" onerror="this.style.display='none'">`;
}

// ===== normalize (istemci tarafı: kıyaslama ve arama) =====
function normalize(s) {
    if (!s) return '';
    return s.toLowerCase()
        .replace(/[çÇ]/g, 'c').replace(/[ğĞ]/g, 'g').replace(/[ıİ]/g, 'i')
        .replace(/[öÖ]/g, 'o').replace(/[şŞ]/g, 's').replace(/[üÜ]/g, 'u')
        .replace(/[áàâãä]/g, 'a').replace(/[éèêë]/g, 'e').replace(/[íìîï]/g, 'i')
        .replace(/[óòôõö]/g, 'o').replace(/[úùûü]/g, 'u').replace(/[ñ]/g, 'n')
        .replace(/[ß]/g, 'ss').replace(/[ø]/g, 'o').replace(/[æ]/g, 'ae')
        .replace(/[œ]/g, 'oe').replace(/[ł]/g, 'l').replace(/[đ]/g, 'd')
        .replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
}

function esc(s) {
    if (s === null || s === undefined) return '';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
}

// ===== Confetti =====
function fireConfetti() {
    const colors = ['#6c5ce7', '#00cec9', '#00d68f', '#ffd43b', '#ff4757', '#8474f5'];
    const count = 80;
    for (let i = 0; i < count; i++) {
        const piece = document.createElement('div');
        piece.className = 'confetti-piece';
        piece.style.left = Math.random() * 100 + 'vw';
        piece.style.background = colors[Math.floor(Math.random() * colors.length)];
        piece.style.width = (6 + Math.random() * 8) + 'px';
        piece.style.height = piece.style.width;
        if (Math.random() > 0.5) piece.style.borderRadius = '50%';
        piece.style.animationDuration = (1.8 + Math.random() * 1.6) + 's';
        piece.style.animationDelay = (Math.random() * 0.4) + 's';
        document.body.appendChild(piece);
        setTimeout(() => piece.remove(), 4000);
    }
}

// ===== Basit avatar: nickname'in baş harfi =====
function avatarLetter(nick) {
    return (nick || '?').trim().charAt(0).toUpperCase() || '?';
}
