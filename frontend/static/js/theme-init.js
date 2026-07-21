(function () {
    var theme = 'light';
    try {
        theme = localStorage.getItem('theme');
        if (theme !== 'light' && theme !== 'dark') {
            theme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
    } catch (_) {
        theme = 'light';
    }
    document.documentElement.setAttribute('data-theme', theme);
})();
