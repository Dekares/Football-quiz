// Ortak yardımcılar (solo + multi paylaşır)

// ===== i18n =====
const LANGS = {
    tr: {
        nav_menu: 'Günlük Tahmin',
        nav_multi: 'Düello',
        nav_duel: 'Harman 1v1',
        app_title: 'Careerdle',
        app_subtitle: 'Ne oynamak istersin?',
        multi_soon: 'Çok kişilik modu yakında geliyor.',
        seo_h1: 'Careerdle — Futbolcuyu kariyerinden tahmin et',
        seo_intro: 'Her gün yeni "Günün Futbolcusu" bulmacası, kariyer ve transfer geçmişine dayalı solo futbolcu tahmin oyunu ve arkadaşlarınla 2-6 kişilik canlı düello. Ücretsiz, üyeliksiz.',
        solo_eyebrow: 'FUTBOLCU TAHMİN',
        quiz_title_a: 'Oyuncuyu',
        quiz_title_b: 'Tahmin Et',
        quiz_subtitle: 'Kariyer yolculuğundan gizemli futbolcuyu bul.',
        easy: 'Kolay',
        medium: 'Orta',
        hard: 'Zor',
        start_prompt: "Başlamak için Yeni Tur'a bas",
        guess_placeholder: 'Oyuncu adını yaz...',
        submit_guess: 'Tahmini Gönder',
        guess_btn: 'Tahmin Et',
        next_question: 'Sonraki Soru',
        hint: 'İpucu',
        skip: 'Atla',
        new_round: 'Yeni Tur',
        career_journey: 'Kariyer Yolculuğu',
        recent_guesses: 'Son Tahminler',
        recent_empty: 'Henüz tahmin yok',
        quick_tips: 'İpuçları',
        tip_1: 'Mevki ve milliyet en güçlü ilk ipuçların.',
        tip_2: 'Kariyer sırası önemli — ilk kulüp en üstte.',
        tip_3: 'İpucu hakkını adın baş harflerini görmek için kullan.',
        tip_4: 'Takıldıysan Atla ve yeni turla geri dön.',
        streak_note: 'Devam et!',
        record_note: 'En iyin',
        total_note: 'Gelişmeye devam',
        time_now: 'az önce',
        time_min: 'dk önce',
        time_hour: 'sa önce',
        no_player: 'Oyuncu bulunamadı',
        loading: 'Soru yükleniyor...',
        correct: 'Doğru!',
        wrong: 'Yanlış!',
        quiz_correct_title: 'Doğru',
        quiz_correct_accent: 'Tahmin!',
        quiz_correct_sub: 'Harika! Oyuncuyu bildin.',
        quiz_wrong_title: 'Bilemedin',
        quiz_wrong_sub: 'Doğru oyuncu buydu.',
        quiz_next_player: 'Yeni Oyuncu',
        wrong_guess: 'Yanlış tahmin!',
        lives_left: 'hak kaldı',
        position: 'Mevki',
        nationality: 'Milliyet',
        ongoing: 'Devam ediyor',
        until: "'a kadar",
        retirement: 'Emeklilik',
        quiz_load_error: 'Soru yüklenemedi, bağlantını kontrol et.',
        retry: 'Tekrar dene',
        pos_attack: 'Forvet',
        pos_midfield: 'Orta Saha',
        pos_defender: 'Defans',
        pos_goalkeeper: 'Kaleci',
        hint_age: 'Yaş',
        hint_subpos: 'Detaylı mevki',
        hint_initials: 'Baş harfler',
        hint_years_old: 'yaşında',
        // Menu / nav
        menu_solo_title: 'Futbolcu Tahmin',
        // Harman 1v1 sayfası
        duel_title: 'Harman 1v1',
        duel_subtitle: 'İki takım seçilir, ortak oyuncuyu ilk söyleyen puanı kapar',
        duel_rule_1: 'İki oyuncu aynı anda birer takım seçer.',
        duel_rule_2: 'Herkes iki takımda da oynamış bir futbolcuyu yazmaya yarışır.',
        duel_rule_3: 'İlk doğru cevap +1 puan; hedefe ulaşan kazanır.',
        // Multi (Düello lobi)
        multi_title: 'Düello',
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
        multi_players: 'Oyuncular',
        multi_lobby_hint: 'Arkadaşlarına bu kodu gönder',
        multi_mode: 'Cevap modu',
        multi_mode_mc: '4 Şıklı',
        multi_mode_free: 'Serbest Yazma',
        multi_mode_duel: 'Düello',
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
        multi_duel_retry: 'Yanlış — tekrar dene',
        duel_pick_title: 'Takımları seçin',
        duel_your_turn: 'Senin sıran: {n}. takımı seç',
        duel_search_team: 'Takım adı yaz...',
        duel_is_picking: 'takım seçiyor...',
        duel_pick_now: 'Takımını seç',
        duel_you: 'sen',
        duel_starting: 'Başlıyor…',
        duel_answer: 'Doğru cevap',
        duel_solved_by: 'bildi!',
        duel_nobody: 'Kimse bilemedi',
        duel_example: 'Örnek ortak oyuncu',
        no_result: 'Sonuç bulunamadı',
        multi_game_over: 'Oyun Bitti',
        multi_winner: 'Kazanan',
        multi_rematch: 'Yeniden Oyna',
        multi_to_menu: 'Ana Menüye',
        multi_back_to_lobby: 'Lobiye Dön',
        multi_redirect_hint: 'saniye sonra lobiye dönüp host\'u bekleyeceksin...',
        multi_host_left: 'Host ayrıldı, yeni host atandı',
        multi_connecting: 'Bağlanıyor...',
        multi_disconnected: 'Bağlantı koptu, yeniden bağlanıyor...',
        multi_kicked: 'Lobiden çıkarıldın',
        multi_kick_confirm: 'Oyuncu lobiden çıkarılsın mı?',
        // Sunucu hata kodları (socket 'error' event'i → kullanıcıya gösterilen mesaj)
        err_rate_limited: 'Çok hızlı, biraz yavaşla',
        err_server_busy: 'Sunucu şu an dolu, sonra tekrar dene',
        err_invalid_code: 'Geçersiz lobi kodu',
        err_lobby_full: 'Lobi dolu',
        err_in_game: 'Oyun zaten başladı',
        err_unknown_player: 'Bu lobide bu oyuncu yok',
        err_not_host: 'Bunu sadece host yapabilir',
        err_cannot_start: 'Başlatılamadı (en az 2 oyuncu gerekli)',
        err_not_your_turn: 'Sıra sende değil',
        err_no_common: 'Bu iki takımın ortak oyuncusu yok, başka takım seç',
        err_no_question: 'Bu zorluk için uygun soru bulunamadı',
        err_generic: 'Bir hata oluştu',
        // Hero / landing
        hero_hook: 'Kulüp geçmişine bak, gizemli oyuncuyu bul.',
        // Günün Futbolcusu (LoLdle tarzı)
        classic_title: 'Günün Futbolcusu',
        classic_prompt: 'Bir futbolcu adı yaz; her tahminde özellikler kıyaslanır.',
        classic_attempts: 'Tahmin sayısı',
        classic_tries: 'tahmin',
        classic_solved: 'Buldun!',
        classic_lost: 'Hakların bitti! Yarın yeni bir futbolcu seni bekliyor.',
        classic_reveal: 'Cevabı gör',
        classic_answer: 'Doğru cevap',
        close: 'Kapat',
        classic_already: 'Bu oyuncuyu zaten denedin',
        classic_tomorrow: 'Her gün yeni bir futbolcu. Yarın tekrar gel!',
        classic_pool_note: 'Tüm aktif oyuncuları arayabilirsin',
        classic_legend_hit: 'Doğru',
        classic_legend_partial: 'Kısmen (kıta/lig/yakın)',
        classic_legend_miss: 'Yanlış',
        classic_legend_up: '▲ Aranan daha yüksek/yaşlı',
        classic_legend_down: '▼ Aranan daha düşük/genç',
        attr_nationality: 'Milliyet',
        attr_position: 'Mevki',
        attr_age: 'Yaş',
        attr_value: 'Değer',
        attr_club: 'Kulüp',
        attr_league: 'Lig',
        // Solo rekor
        solo_record: 'Rekor',
        solo_total_correct: 'Toplam doğru',
        solo_streak: 'Seri',
        solo_new_record: 'Yeni rekor!',
        // Paylaşım
        share_result: 'Skorumu Paylaş',
        share_invite: 'Davet Linki',
        share_copied: 'Kopyalandı!',
        share_caption_solo: '⚽ Careerdle\'de {correct}/{total} doğru, rekor seri: {streak}. Sen de dene:',
        share_caption_multi: '⚽ Careerdle\'de {score} puanla {place}. oldum! Sen de dene:',
        // Cold-start
        waking_up: 'Sunucu uyanıyor (ilk açılışta ~30sn)...',
        // Lobby
        copy_code: 'Kodu Kopyala',
        copy_invite: 'Davet Linkini Kopyala',
    },
    en: {
        nav_menu: 'Daily Guess',
        nav_multi: 'Duel',
        nav_duel: 'Harman 1v1',
        app_title: 'Careerdle',
        app_subtitle: 'What do you want to play?',
        multi_soon: 'Multiplayer mode coming soon.',
        seo_h1: 'Careerdle — Guess the footballer from their career',
        seo_intro: 'A new "Player of the Day" puzzle every day, a solo footballer guessing game based on career and transfer history, plus live 2-6 player duels with friends. Free, no sign-up.',
        solo_eyebrow: 'FOOTBALLER GUESS',
        quiz_title_a: 'Guess the',
        quiz_title_b: 'Player',
        quiz_subtitle: 'Identify the mystery footballer from their career journey.',
        easy: 'Easy',
        medium: 'Medium',
        hard: 'Hard',
        start_prompt: 'Hit New Round to start',
        guess_placeholder: "Type the player's name...",
        submit_guess: 'Submit Guess',
        guess_btn: 'Guess',
        next_question: 'Next Question',
        hint: 'Hint',
        skip: 'Skip',
        new_round: 'New Round',
        career_journey: 'Career Journey',
        recent_guesses: 'Recent Guesses',
        recent_empty: 'No guesses yet',
        quick_tips: 'Quick Tips',
        tip_1: 'Position and nationality are your strongest first clues.',
        tip_2: 'Order matters — the first club is at the top.',
        tip_3: 'Use a hint to reveal the name letter by letter.',
        tip_4: 'Stuck? Skip and come back with a new round.',
        streak_note: 'Keep it going!',
        record_note: 'Best so far',
        total_note: 'Keep improving!',
        time_now: 'just now',
        time_min: 'm ago',
        time_hour: 'h ago',
        no_player: 'Player not found',
        loading: 'Loading question...',
        correct: 'Correct!',
        wrong: 'Wrong!',
        quiz_correct_title: 'Correct',
        quiz_correct_accent: 'Guess!',
        quiz_correct_sub: 'Nice! You got the player.',
        quiz_wrong_title: 'Not quite',
        quiz_wrong_sub: 'This was the right player.',
        quiz_next_player: 'New Player',
        wrong_guess: 'Wrong guess!',
        lives_left: 'lives left',
        position: 'Position',
        nationality: 'Nationality',
        ongoing: 'Present',
        until: ' until',
        retirement: 'Retired',
        quiz_load_error: 'Could not load quiz, check your connection.',
        retry: 'Retry',
        pos_attack: 'Forward',
        pos_midfield: 'Midfielder',
        pos_defender: 'Defender',
        pos_goalkeeper: 'Goalkeeper',
        hint_age: 'Age',
        hint_subpos: 'Detailed position',
        hint_initials: 'Initials',
        hint_years_old: 'years old',
        menu_solo_title: 'Footballer Guess',
        // Harman 1v1 page
        duel_title: 'Harman 1v1',
        duel_subtitle: 'Two teams are picked; first to name a shared player scores',
        duel_rule_1: 'Two players each pick a team at the same time.',
        duel_rule_2: 'Everyone races to name a player who played for both teams.',
        duel_rule_3: 'First correct answer scores +1; first to the target wins.',
        multi_title: 'Duel',
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
        multi_players: 'Players',
        multi_lobby_hint: 'Share this code with your friends',
        multi_mode: 'Answer mode',
        multi_mode_mc: '4-Choice',
        multi_mode_free: 'Free type',
        multi_mode_duel: 'Duel',
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
        multi_duel_retry: 'Wrong — try again',
        duel_pick_title: 'Pick the teams',
        duel_your_turn: 'Your turn: pick team {n}',
        duel_search_team: 'Type a team name...',
        duel_is_picking: 'is picking a team...',
        duel_pick_now: 'Pick your team',
        duel_you: 'you',
        duel_starting: 'Starting…',
        duel_answer: 'Correct answer',
        duel_solved_by: 'got it!',
        duel_nobody: 'Nobody got it',
        duel_example: 'Example common player',
        no_result: 'No results found',
        multi_game_over: 'Game Over',
        multi_winner: 'Winner',
        multi_rematch: 'Rematch',
        multi_to_menu: 'Main Menu',
        multi_back_to_lobby: 'Back to Lobby',
        multi_redirect_hint: 'seconds until you return to the lobby and wait for the host...',
        multi_host_left: 'Host left, new host assigned',
        multi_connecting: 'Connecting...',
        multi_disconnected: 'Disconnected, reconnecting...',
        multi_kicked: "You've been removed from the lobby",
        multi_kick_confirm: 'Remove this player from the lobby?',
        // Server error codes (socket 'error' event → message shown to user)
        err_rate_limited: 'Too fast, slow down a bit',
        err_server_busy: 'Server is busy right now, try again later',
        err_invalid_code: 'Invalid lobby code',
        err_lobby_full: 'Lobby is full',
        err_in_game: 'Game already in progress',
        err_unknown_player: 'This player is not in the lobby',
        err_not_host: 'Only the host can do this',
        err_cannot_start: 'Cannot start (at least 2 players required)',
        err_not_your_turn: "It's not your turn",
        err_no_common: 'These two teams share no player, pick another',
        err_no_question: 'No suitable question for this difficulty',
        err_generic: 'Something went wrong',
        // Hero / landing
        hero_hook: 'Read the club history, name the mystery player.',
        // Daily Footballer (LoLdle-style)
        classic_title: 'Daily Footballer',
        classic_prompt: 'Type a player; each guess compares their attributes.',
        classic_attempts: 'Guesses',
        classic_tries: 'guesses',
        classic_solved: 'Solved!',
        classic_lost: 'Out of guesses! A new footballer awaits tomorrow.',
        classic_reveal: 'Reveal answer',
        classic_answer: 'The answer',
        close: 'Close',
        classic_already: 'You already tried this player',
        classic_tomorrow: 'A new footballer every day. Come back tomorrow!',
        classic_pool_note: 'Search any active player',
        classic_legend_hit: 'Correct',
        classic_legend_partial: 'Partial (continent/league/close)',
        classic_legend_miss: 'Wrong',
        classic_legend_up: '▲ Target is higher/older',
        classic_legend_down: '▼ Target is lower/younger',
        attr_nationality: 'Nationality',
        attr_position: 'Position',
        attr_age: 'Age',
        attr_value: 'Value',
        attr_club: 'Club',
        attr_league: 'League',
        // Solo records
        solo_record: 'Record',
        solo_total_correct: 'Total correct',
        solo_streak: 'Streak',
        solo_new_record: 'New record!',
        // Share
        share_result: 'Share Score',
        share_invite: 'Invite Link',
        share_copied: 'Copied!',
        share_caption_solo: '⚽ Got {correct}/{total} on Careerdle, best streak: {streak}. Try it:',
        share_caption_multi: '⚽ Finished #{place} with {score} points on Careerdle! Try it:',
        // Cold-start
        waking_up: 'Waking up server (first load ~30s)...',
        // Lobby
        copy_code: 'Copy Code',
        copy_invite: 'Copy Invite Link',
    }
};

let currentLang = localStorage.getItem('lang') || 'tr';

function t(key) { return LANGS[currentLang][key] || key; }

function toggleLang() {
    currentLang = currentLang === 'tr' ? 'en' : 'tr';
    localStorage.setItem('lang', currentLang);
    const toggle = document.querySelector('.lang-toggle');
    if (toggle) toggle.textContent = currentLang === 'tr' ? 'EN' : 'TR';
    document.documentElement.lang = currentLang;
    applyLang();
    // Dinamik render edilen ekranlar (lobi/oyun/günlük tahmin/solo) statik
    // data-i18n taşımaz; her modül bu olayı dinleyip aktif görünümü yeniden çizer.
    window.dispatchEvent(new CustomEvent('langchange', { detail: currentLang }));
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

// Detaylı mevki (Transfermarkt sub_position) — TR'de çevir, EN'de ham değer.
const SUBPOS_TR = {
    'Centre-Back': 'Stoper', 'Centre-Forward': 'Santrfor',
    'Central Midfield': 'Merkez Orta Saha', 'Defensive Midfield': 'Defansif Orta Saha',
    'Attacking Midfield': 'Ofansif Orta Saha', 'Left Winger': 'Sol Kanat',
    'Right Winger': 'Sağ Kanat', 'Right-Back': 'Sağ Bek', 'Left-Back': 'Sol Bek',
    'Goalkeeper': 'Kaleci', 'Second Striker': 'İkinci Forvet',
    'Right Midfield': 'Sağ Orta Saha', 'Left Midfield': 'Sol Orta Saha',
};
function subPosText(pos) {
    if (!pos) return '?';
    return currentLang === 'tr' ? (SUBPOS_TR[pos] || pos) : pos;
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

// ===== Lig kodu → görünür isim (Günün Futbolcusu) =====
const LEAGUE_NAMES = {
    GB1: 'Premier Lig', ES1: 'LaLiga', IT1: 'Serie A', L1: 'Bundesliga', FR1: 'Ligue 1',
    PO1: 'Primeira Liga', NL1: 'Eredivisie', TR1: 'Süper Lig', RU1: 'Rusya Premier',
    UKR1: 'Ukrayna Premier', BE1: 'Pro League', GR1: 'Süper Lig (YUN)', A1: 'Avusturya Bundesliga',
    C1: 'İsviçre Super League', SC1: 'İskoçya Premiership', DK1: 'Superliga', SE1: 'Allsvenskan',
    NO1: 'Eliteserien', PL1: 'Ekstraklasa', RO1: 'Liga 1', SER1: 'Sırbistan SuperLiga',
    TS1: 'Çek Ligi', KR1: 'Hırvatistan HNL', BRA1: 'Brasileirão', ARG1: 'Arjantin Ligi',
    COL1: 'Kolombiya Primera', MLS1: 'MLS', MEX1: 'Liga MX', JAP1: 'J1 League',
    SA1: 'Suudi Pro Lig', RSK1: 'K League', AUS1: 'A-League',
};

function flagHtml(country, large) {
    if (!country) return '';
    const code = COUNTRY_CODES[country];
    if (!code) return '';
    const cls = large ? 'flag-img flag-lg' : 'flag-img';
    return `<img class="${cls}" src="https://flagcdn.com/w40/${code}.png" srcset="https://flagcdn.com/w80/${code}.png 2x" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.style.display='none'">`;
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

// ===== Toast (küçük bildirim) =====
function showToast(msg, kind) {
    const prev = document.getElementById('toast-notify');
    if (prev) prev.remove();
    const el = document.createElement('div');
    el.id = 'toast-notify';
    el.className = 'toast-notify' + (kind === 'error' ? ' error' : '');
    el.textContent = msg;
    document.body.appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => {
        el.classList.remove('show');
        setTimeout(() => el.remove(), 300);
    }, 2200);
}

// ===== Clipboard + share =====
async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (_) {
        // Fallback
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); } catch (_) {}
        ta.remove();
        return true;
    }
}

async function shareOrCopy(text, url) {
    const payload = { title: 'Careerdle', text, url };
    if (navigator.share) {
        try {
            await navigator.share(payload);
            return 'shared';
        } catch (_) { /* user cancelled → fall back */ }
    }
    await copyText(`${text} ${url}`);
    showToast(t('share_copied'));
    return 'copied';
}

// ===== URL params =====
function getQueryParam(name) {
    try {
        const params = new URLSearchParams(location.search);
        return params.get(name);
    } catch (_) { return null; }
}

// ===== safeFetch: timeout + hata yönetimi =====
// Render cold-start + flaky network → her fetch askıda kalabilir.
// AbortController ile 15sn timeout, !ok'te Error throw, JSON parse koruması.
async function safeFetch(url, opts = {}) {
    const timeout = opts.timeout || 15000;
    const ctrl = new AbortController();
    const tid = setTimeout(() => ctrl.abort(), timeout);
    try {
        const res = await fetch(url, { ...opts, signal: ctrl.signal });
        if (!res.ok) {
            const body = await res.text().catch(() => '');
            const err = new Error(`HTTP ${res.status}`);
            err.status = res.status;
            err.body = body;
            throw err;
        }
        return await res.json();
    } catch (e) {
        if (e.name === 'AbortError') {
            const timeoutErr = new Error('timeout');
            timeoutErr.isTimeout = true;
            throw timeoutErr;
        }
        throw e;
    } finally {
        clearTimeout(tid);
    }
}

// ===== Cold-start (ilk yüklemede sunucunun uyandığını göster) =====
let wakeupOverlayTimer = null;
function showWakeupOverlayIfSlow(delayMs) {
    if (document.getElementById('wakeup-overlay')) return;
    wakeupOverlayTimer = setTimeout(() => {
        if (document.getElementById('wakeup-overlay')) return;
        const el = document.createElement('div');
        el.id = 'wakeup-overlay';
        el.className = 'wakeup-overlay';
        el.innerHTML = `<div class="wakeup-card">
            <div class="spinner"></div>
            <div class="wakeup-msg">${t('waking_up')}</div>
        </div>`;
        document.body.appendChild(el);
    }, delayMs || 1200);
}
function hideWakeupOverlay() {
    if (wakeupOverlayTimer) { clearTimeout(wakeupOverlayTimer); wakeupOverlayTimer = null; }
    const el = document.getElementById('wakeup-overlay');
    if (el) {
        el.classList.add('fade-out');
        setTimeout(() => el.remove(), 250);
    }
}

// İlk ping: ana sayfa açılışında backend'e dokunarak Render cold-start'ı tetikler.
// Yanıt gelirse overlay yok; 1.2sn sonra hala bekliyorsa overlay çıkar.
(function pingServerOnLoad() {
    if (sessionStorage.getItem('pinged')) return;
    showWakeupOverlayIfSlow(1500);
    fetch('/api/health', { cache: 'no-store' })
        .catch(() => {})
        .finally(() => {
            sessionStorage.setItem('pinged', '1');
            hideWakeupOverlay();
        });
})();
