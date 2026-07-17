function applyDocLang(lang) {
    document.documentElement.lang = lang;
    document.querySelectorAll('[data-lang]').forEach(function (element) {
        element.hidden = element.dataset.lang !== lang;
    });
    var toggle = document.querySelector('.lang-toggle');
    if (toggle) toggle.textContent = lang === 'tr' ? 'EN' : 'TR';
    var date = document.getElementById('mh-date');
    if (date) {
        date.textContent = new Date().toLocaleDateString(
            lang === 'tr' ? 'tr-TR' : 'en-US',
            { weekday: 'long', month: 'long', day: 'numeric' }
        );
    }
}

function toggleLang() {
    var lang = (localStorage.getItem('lang') || 'tr') === 'tr' ? 'en' : 'tr';
    localStorage.setItem('lang', lang);
    applyDocLang(lang);
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    var toggle = document.querySelector('.theme-toggle');
    if (toggle) toggle.textContent = theme === 'dark' ? '☀' : '☾';
}

function toggleTheme() {
    var current = document.documentElement.getAttribute('data-theme') === 'dark'
        ? 'dark' : 'light';
    applyTheme(current === 'dark' ? 'light' : 'dark');
}

function toggleMobileNav() {
    var nav = document.getElementById('mobile-nav');
    if (nav) nav.classList.toggle('open');
}

function closeMobileNav() {
    var nav = document.getElementById('mobile-nav');
    if (nav) nav.classList.remove('open');
}

function markActiveShellLink() {
    document.querySelectorAll('[data-shell-path]').forEach(function (link) {
        if (link.dataset.shellPath === location.pathname) {
            link.setAttribute('aria-current', 'page');
        }
    });
}

applyDocLang(localStorage.getItem('lang') || 'tr');
applyTheme(document.documentElement.getAttribute('data-theme') || 'light');
markActiveShellLink();
