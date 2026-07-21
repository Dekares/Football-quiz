// Ortak yardımcılar (solo + multi paylaşır)

// ===== i18n =====
const LANGS = {
    tr: {
        nav_menu: 'Günlük Tahmin',
        nav_multi: 'Düello',
        nav_duel: 'Harman 1v1',
        nav_about: 'Hakkında',
        nav_privacy: 'Gizlilik',
        nav_contact: 'İletişim',
        mh_midnight: 'Gece yarısı yeni oyuncu',
        mh_edition: 'Günlük Futbol Baskısı',
        daily_kicker: 'Günlük Meydan Okuma',
        daily_next: 'Sonraki oyuncu',
        status_guess: 'Tahmin',
        status_left: 'Kalan hak',
        status_streak: 'Seri',
        how_title: 'Nasıl oynanır',
        how_1: 'Gizli bir futbolcu seçilir; herkes için aynıdır.',
        how_2: 'Bir oyuncu adı yaz — her tahmin; milliyet, mevki, yaş, değer, kulüp ve ligi gizli oyuncuyla kıyaslar.',
        how_3: '🟩 aynı, 🟨 yakın, 🟥 alakasız. Sekiz hakta bul, serini koru.',
        cta_eyebrow: 'Günlük ritüel',
        cta_title: 'Bir oyuncu. Sekiz tahmin. Her gün.',
        cta_sub: 'Careerdle\'ı yer imlerine ekle ve yarın geri dön — seri sayacı sadık kalanı ödüllendirir.',
        stats_title: 'İstatistik',
        stat_played: 'Oynanan',
        stat_winrate: 'Kazanma %',
        stat_best: 'Rekor',
        dist_title: 'Tahmin dağılımı',
        banner_answer: 'Bugünkü oyuncu',
        footer_blurb: 'Futbol tutkunları için günlük bir sınav. Kariyeri oku, oyuncuyu bul, seriyi koru. Günde tek bulmaca — uzatma yok.',
        footer_est: '2026 · Careerdle Baskısı',
        footer_game: 'Oyun',
        footer_tag: 'Güzel oyun için yapıldı',
        help_title: 'Nasıl oynanır',
        help_eyebrow: 'Kurallar',
        help_intro: 'Careerdle günlük bir tahmin oyunudur. Gizli futbolcuyu en az tahminle bul.',
        help_s1: 'Her gün gizli bir futbolcu seçilir; herkes için aynıdır.',
        help_s2: 'Bir oyuncu adı ara ve tahmin et. Her tahmin gizli oyuncuyla kıyaslanır.',
        help_s3: '🟩 aynı, 🟨 yakın (kıta/lig), 🟥 alakasız; yaş ve değerde ▲▼ yön gösterir.',
        help_s4: 'Sekiz hakta bul; her gün gece yarısı yeni oyuncu gelir.',
        help_clues: 'İpuçların',
        clue_nat: 'Milliyet', clue_nat_d: 'Aynı ülkeyse yeşil, aynı kıtaysa sarı.',
        clue_pos: 'Mevki', clue_pos_d: 'Mevki tutarsa yeşil.',
        clue_age: 'Yaş / Değer', clue_age_d: 'Gizli oyuncu daha büyük/küçük mü — ▲▼.',
        clue_club: 'Kulüp / Lig', clue_club_d: 'Aynı kulüp/lig yeşil, aynı konfederasyon sarı.',
        app_title: 'Careerdle',
        app_subtitle: 'Ne oynamak istersin?',
        seo_h1: 'Careerdle — Futbolcuyu kariyerinden tahmin et',
        seo_intro: 'Her gün yeni "Günün Futbolcusu" bulmacası ve kariyer geçmişine dayalı lig bazlı solo tahmin oyunu. Ücretsiz, üyeliksiz.',
        solo_eyebrow: 'FUTBOLCU TAHMİN',
        quiz_title_a: 'Oyuncuyu',
        quiz_title_b: 'Tahmin Et',
        quiz_subtitle: 'Kariyer yolculuğundan gizemli futbolcuyu bul.',
        solo_setup_kicker: 'Kariyer modu',
        solo_setup_title: 'Koşunu oluştur',
        solo_setup_note: 'Lig ve oyuncu havuzunu belirle',
        solo_league_label: 'Lig',
        solo_league_note: 'Oyuncunun güncel ligi',
        solo_recognition_label: 'Oyuncu havuzu',
        solo_recognition_note: 'Ligdeki bilinirlik sırası',
        solo_start: 'Başlat',
        solo_active_pool: 'Aktif havuz',
        solo_change_pool: 'Seçimi Değiştir',
        all_leagues: 'Dünya Karması',
        career_legends: 'Kariyer Efsaneleri',
        known: 'Bilindik',
        less_known: 'Az Bilindik',
        obscure: 'Bilinmedik',
        player_count: 'oyuncu',
        easy: 'Kolay',
        medium: 'Orta',
        hard: 'Zor',
        start_prompt: 'Ligini ve oyuncu havuzunu seç',
        guess_placeholder: 'Oyuncu adını yaz...',
        guess_player_label: 'Oyuncu adı',
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
        result_solved_kicker: 'Oyuncu bulundu',
        result_skipped_kicker: 'Tur atlandı',
        result_skipped_title: 'Oyuncuyu geçtin',
        result_skipped_sub: 'Doğru oyuncu ve kariyer özeti aşağıda.',
        result_answer_label: 'Doğru oyuncu',
        result_career_summary: 'Kariyer özeti',
        result_club_count: 'Farklı kulüp',
        result_career_span: 'Kariyer aralığı',
        result_last_club: 'Son kulüp',
        result_pool: 'Seçili havuz',
        result_route: 'Kariyer rotası',
        result_change_pool: 'Havuzu değiştir',
        result_lives: 'Kalan hak',
        result_new_record: 'Yeni rekor',
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
        multi_game_over: 'Oyun Bitti',
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
        run_max_streak: 'En yüksek seri',
        game_over_missed: 'Bilemediğin oyuncu',
        new_run: 'Yeni Oyun',
        // Paylaşım
        share_result: 'Sonucu Paylaş',
        share_invite: 'Davet Linki',
        share_copied: 'Kopyalandı!',
        share_caption_run: 'Careerdle\'de {total} futbolcu bildim, en yüksek serim {streak}. Sen de dene:',
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
        nav_about: 'About',
        nav_privacy: 'Privacy',
        nav_contact: 'Contact',
        mh_midnight: 'New player at midnight',
        mh_edition: 'Daily Football Edition',
        daily_kicker: 'Daily Challenge',
        daily_next: 'Next player in',
        status_guess: 'Guesses',
        status_left: 'Guesses left',
        status_streak: 'Streak',
        how_title: 'How to play',
        how_1: 'A mystery footballer is chosen — the same one for everyone.',
        how_2: 'Type a player name — each guess compares nationality, position, age, value, club and league with the mystery player.',
        how_3: '🟩 exact, 🟨 close, 🟥 unrelated. Find them in eight guesses, keep your streak.',
        cta_eyebrow: 'Daily ritual',
        cta_title: 'One player. Eight guesses. Every day.',
        cta_sub: 'Bookmark Careerdle and come back tomorrow — the streak counter rewards the faithful.',
        stats_title: 'Statistics',
        stat_played: 'Played',
        stat_winrate: 'Win %',
        stat_best: 'Best',
        dist_title: 'Guess distribution',
        banner_answer: 'Today\'s player was',
        footer_blurb: 'A daily test for football obsessives. Read the career, name the player, keep the streak alive. One puzzle a day — no extra time.',
        footer_est: '2026 · Careerdle Edition',
        footer_game: 'Game',
        footer_tag: 'Made for the beautiful game',
        help_title: 'How to play',
        help_eyebrow: 'The rules',
        help_intro: 'Careerdle is a daily guessing game. Name the mystery player in as few guesses as possible.',
        help_s1: 'A mystery footballer is chosen every day — the same one for everyone.',
        help_s2: 'Search and guess any player. Each guess is compared with the mystery player.',
        help_s3: '🟩 exact, 🟨 close (continent/league), 🟥 unrelated; age and value show ▲▼ direction.',
        help_s4: 'Solve it in eight guesses; a new player arrives at midnight.',
        help_clues: 'Your clues',
        clue_nat: 'Nationality', clue_nat_d: 'Green for same nation, yellow for same continent.',
        clue_pos: 'Position', clue_pos_d: 'Green if the position matches.',
        clue_age: 'Age / Value', clue_age_d: 'Whether the mystery player is older/younger — ▲▼.',
        clue_club: 'Club / League', clue_club_d: 'Green for same club/league, yellow for same confederation.',
        app_title: 'Careerdle',
        app_subtitle: 'What do you want to play?',
        seo_h1: 'Careerdle — Guess the footballer from their career',
        seo_intro: 'A new "Player of the Day" puzzle every day and a league-based solo guessing game built from career history. Free, no sign-up.',
        solo_eyebrow: 'FOOTBALLER GUESS',
        quiz_title_a: 'Guess the',
        quiz_title_b: 'Player',
        quiz_subtitle: 'Identify the mystery footballer from their career journey.',
        solo_setup_kicker: 'Career mode',
        solo_setup_title: 'Build your run',
        solo_setup_note: 'Set the league and player pool',
        solo_league_label: 'League',
        solo_league_note: "The player's current league",
        solo_recognition_label: 'Player pool',
        solo_recognition_note: 'Recognition rank in the league',
        solo_start: 'Start',
        solo_active_pool: 'Active pool',
        solo_change_pool: 'Change Selection',
        all_leagues: 'World XI',
        career_legends: 'Career Legends',
        known: 'Known',
        less_known: 'Less Known',
        obscure: 'Obscure',
        player_count: 'players',
        easy: 'Easy',
        medium: 'Medium',
        hard: 'Hard',
        start_prompt: 'Choose a league and player pool',
        guess_placeholder: "Type the player's name...",
        guess_player_label: 'Player name',
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
        result_solved_kicker: 'Player found',
        result_skipped_kicker: 'Round skipped',
        result_skipped_title: 'Player passed',
        result_skipped_sub: 'The correct player and career summary are below.',
        result_answer_label: 'Correct player',
        result_career_summary: 'Career summary',
        result_club_count: 'Different clubs',
        result_career_span: 'Career span',
        result_last_club: 'Latest club',
        result_pool: 'Selected pool',
        result_route: 'Career route',
        result_change_pool: 'Change pool',
        result_lives: 'Lives left',
        result_new_record: 'New record',
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
        multi_game_over: 'Game Over',
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
        run_max_streak: 'Best streak',
        game_over_missed: 'The player you missed',
        new_run: 'New Game',
        // Share
        share_result: 'Share Result',
        share_invite: 'Invite Link',
        share_copied: 'Copied!',
        share_caption_run: 'Guessed {total} players on Careerdle, best streak {streak}. Try it:',
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

// ===== Tema (açık/koyu) — data-theme <html>'de; head'deki inline script ilk
// değeri atar (flash yok), burada toggle + buton etiketi yönetilir. =====
function applyTheme(th) {
    document.documentElement.setAttribute('data-theme', th);
    localStorage.setItem('theme', th);
    const b = document.querySelector('.theme-toggle');
    if (b) {
        b.textContent = th === 'dark' ? '☀' : '☾'; // ☀ / ☾
        b.setAttribute('aria-pressed', String(th === 'dark'));
        b.setAttribute('aria-label', currentLang === 'tr' ? 'Temayı değiştir' : 'Change theme');
    }
}
function toggleTheme() {
    const cur = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    applyTheme(cur === 'dark' ? 'light' : 'dark');
}
applyTheme(document.documentElement.getAttribute('data-theme') || 'light');

function toggleLang() {
    currentLang = currentLang === 'tr' ? 'en' : 'tr';
    localStorage.setItem('lang', currentLang);
    const toggle = document.querySelector('.lang-toggle');
    if (toggle) {
        toggle.textContent = currentLang === 'tr' ? 'EN' : 'TR';
        toggle.setAttribute(
            'aria-label',
            currentLang === 'tr' ? 'Switch to English' : 'Türkçeye geç',
        );
    }
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
    document.querySelectorAll('[data-lang]').forEach(el => {
        el.hidden = el.dataset.lang !== currentLang;
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

function flagHtml(country, large, countryCode) {
    const code = String(countryCode || '').toLowerCase();
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

// API/veritabanı kaynaklı URL'ler HTML içine yalnızca güvenli bir resim
// protokolüyle girer. javascript:, data: ve kullanıcı bilgisi taşıyan URL'ler
// ikinci-order attribute XSS'e dönüşmesin.
function safeImageUrl(value) {
    if (!value) return '';
    try {
        const url = new URL(String(value), window.location.origin);
        const sameOriginHttp = url.origin === window.location.origin
            && (url.protocol === 'http:' || url.protocol === 'https:');
        if (url.protocol !== 'https:' && !sameOriginHttp) return '';
        if (url.username || url.password) return '';
        return url.href;
    } catch (_) {
        return '';
    }
}

// Kimliksiz ürün olayları. Google Consent Mode saklama iznini yönetir;
// bu sınırlı listeye oyuncu adı, ID veya serbest metin asla girmez.
function trackEvent(name, details = {}) {
    if (typeof window.gtag !== 'function') return;
    const allowed = new Set([
        'mode', 'league', 'recognition', 'result', 'attempts', 'hints', 'lives', 'total', 'streak',
    ]);
    const safeDetails = {};
    Object.entries(details).forEach(([key, value]) => {
        if (!allowed.has(key)) return;
        safeDetails[key] = typeof value === 'number'
            ? Math.max(0, Math.round(value))
            : String(value).slice(0, 32);
    });
    window.gtag('event', String(name).slice(0, 40), safeDetails);
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

// ===== Arama dropdown'unda klavye gezinme (ok tuşları + Enter) =====
// Tüm arama kutularında ortak. Her `.dropdown-player` zaten "seç + gönder" yapan bir
// click handler'ına sahip → Enter'da highlight'lı öğeyi .click()'liyoruz.
// onEnter: hiçbir öğe seçili değilken Enter'a basılınca çağrılır (elle yazıp gönderme).
function attachSearchKeys(input, dropdown, onEnter) {
    input.addEventListener('keydown', (e) => {
        const items = dropdown.classList.contains('show')
            ? [...dropdown.querySelectorAll('.dropdown-player')] : [];
        const idx = items.findIndex(el => el.classList.contains('kbd-active'));
        if (e.key === 'ArrowDown' && items.length) {
            e.preventDefault();
            highlightItem(items, (idx + 1) % items.length);
        } else if (e.key === 'ArrowUp' && items.length) {
            e.preventDefault();
            highlightItem(items, (idx <= 0 ? items.length : idx) - 1);
        } else if (e.key === 'Enter') {
            if (idx >= 0 && items[idx]) { e.preventDefault(); items[idx].click(); }
            else if (onEnter) onEnter();
        } else if (e.key === 'Escape') {
            dropdown.classList.remove('show');
            input.setAttribute('aria-expanded', 'false');
            input.removeAttribute('aria-activedescendant');
        }
    });
}
function highlightItem(items, idx) {
    items.forEach((el, i) => {
        const active = i === idx;
        el.classList.toggle('kbd-active', active);
        el.setAttribute('aria-selected', String(active));
    });
    if (items[idx]) {
        if (!items[idx].id) items[idx].id = `search-option-${Date.now()}-${idx}`;
        const input = items[idx].closest('.search-wrapper')?.querySelector('[role="combobox"]');
        input?.setAttribute('aria-activedescendant', items[idx].id);
    }
    items[idx]?.scrollIntoView({ block: 'nearest' });
}

let activeDialog = null;
function activateDialog(backdrop, onClose) {
    const dialog = backdrop?.querySelector('[role="dialog"], .result-modal');
    if (!dialog) return;
    const previousFocus = document.activeElement;
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    if (!dialog.hasAttribute('tabindex')) dialog.tabIndex = -1;
    activeDialog = { backdrop, dialog, onClose, previousFocus };
    requestAnimationFrame(() => {
        const first = dialog.querySelector('button:not(:disabled), a[href], input:not(:disabled)');
        (first || dialog).focus();
    });
}
function deactivateDialog(backdrop) {
    if (!activeDialog || activeDialog.backdrop !== backdrop) return;
    const previousFocus = activeDialog.previousFocus;
    activeDialog = null;
    if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
}

document.addEventListener('keydown', (event) => {
    if (!activeDialog) return;
    if (event.key === 'Escape') {
        event.preventDefault();
        activeDialog.onClose?.();
        return;
    }
    if (event.key !== 'Tab') return;
    const focusable = [...activeDialog.dialog.querySelectorAll(
        'button:not(:disabled), a[href], input:not(:disabled), [tabindex]:not([tabindex="-1"])',
    )];
    if (!focusable.length) {
        event.preventDefault();
        activeDialog.dialog.focus();
        return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
    }
});

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

function toggleMobileNav() {
    const m = document.getElementById('mobile-nav');
    if (!m) return;
    const open = m.classList.toggle('open');
    m.setAttribute('aria-hidden', String(!open));
    document.querySelector('.nav-burger')?.setAttribute('aria-expanded', String(open));
}
function closeMobileNav() {
    const m = document.getElementById('mobile-nav');
    if (m) {
        m.classList.remove('open');
        m.setAttribute('aria-hidden', 'true');
    }
    document.querySelector('.nav-burger')?.setAttribute('aria-expanded', 'false');
}
document.addEventListener('click', function (event) {
    var control = event.target.closest('[data-shell-action]');
    if (!control) return;
    var action = window[control.dataset.shellAction];
    if (typeof action !== 'function') return;
    if (action.call(control) === false) event.preventDefault();
});
