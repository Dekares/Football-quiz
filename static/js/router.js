// Hash tabanlı basit router
// Rotalar:
//   #/                 -> menu
//   #/solo             -> solo (ortak oyuncu + tahmin)
//   #/multi            -> multiplayer giriş (lobi kur / katıl)
//   #/lobby/XXXXXX     -> bekleme odası
//   #/game/XXXXXX      -> aktif tur
//   #/gameover/XXXXXX  -> sonuç ekranı

const ROUTES = [
    { pattern: /^#?\/?$/,                           name: 'menu' },
    { pattern: /^#\/solo$/,                         name: 'solo' },
    { pattern: /^#\/multi$/,                        name: 'multi' },
    { pattern: /^#\/lobby\/([A-Z0-9]{4,10})$/i,     name: 'lobby',    paramKey: 'code' },
    { pattern: /^#\/game\/([A-Z0-9]{4,10})$/i,      name: 'game',     paramKey: 'code' },
    { pattern: /^#\/gameover\/([A-Z0-9]{4,10})$/i,  name: 'gameover', paramKey: 'code' },
];

const routeListeners = [];
function onRoute(fn) { routeListeners.push(fn); }

function parseRoute(hash) {
    const h = hash || location.hash || '#/';
    for (const r of ROUTES) {
        const m = h.match(r.pattern);
        if (m) {
            const params = {};
            if (r.paramKey && m[1]) params[r.paramKey] = m[1].toUpperCase();
            return { name: r.name, params, hash: h };
        }
    }
    return { name: 'menu', params: {}, hash: '#/' };
}

function renderRoute() {
    const route = parseRoute();
    document.querySelectorAll('section.page').forEach(s => {
        s.classList.toggle('active', s.dataset.route === route.name);
    });
    document.querySelectorAll('nav [data-nav-route]').forEach(b => {
        b.classList.toggle('active', b.dataset.navRoute === route.name);
    });
    routeListeners.forEach(fn => { try { fn(route); } catch (e) { console.error(e); } });
}

function navigate(hash) {
    if (location.hash === hash) renderRoute();
    else location.hash = hash;
}

window.addEventListener('hashchange', renderRoute);
window.addEventListener('DOMContentLoaded', () => {
    applyLang();
    const toggle = document.querySelector('.lang-toggle');
    if (toggle) toggle.textContent = currentLang === 'tr' ? 'EN' : 'TR';

    // ?join=XXXXXX ile gelindiyse direkt multi girişine yönlendir.
    // multi.js bu query'yi görüp join formunu doldurur.
    const joinCode = getQueryParam('join');
    if (joinCode && (!location.hash || location.hash === '#' || location.hash === '#/')) {
        location.hash = '#/multi';
    }

    renderRoute();
});
