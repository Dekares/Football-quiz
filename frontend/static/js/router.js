// Hash tabanlı basit router
// Rotalar:
//   #/         -> menu (Günün Futbolcusu)
//   #/solo     -> solo (kariyerden futbolcu tahmin)

const ROUTES = [
    { pattern: /^#?\/?$/,                           name: 'menu' },
    { pattern: /^#\/solo$/,                         name: 'solo' },
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
    document.documentElement.lang = currentLang;
    const toggle = document.querySelector('.lang-toggle');
    if (toggle) toggle.textContent = currentLang === 'tr' ? 'EN' : 'TR';

    renderRoute();
});
