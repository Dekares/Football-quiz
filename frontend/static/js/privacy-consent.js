/* Google Consent Mode v2 defaults. A Google-certified CMP must update these choices. */
(function () {
    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
    window.gtag('consent', 'default', {
        ad_storage: 'denied',
        analytics_storage: 'denied',
        ad_user_data: 'denied',
        ad_personalization: 'denied',
        wait_for_update: 2000
    });
    window.gtag('set', 'ads_data_redaction', true);
    window.googlefc = window.googlefc || {};
    window.googlefc.callbackQueue = window.googlefc.callbackQueue || [];

    window.openPrivacyChoices = function () {
        if (typeof window.googlefc.showRevocationMessage === 'function') {
            window.googlefc.callbackQueue.push(window.googlefc.showRevocationMessage);
            return false;
        }
        if (window.location.pathname !== '/') {
            window.location.assign('/?privacy-settings=1');
            return false;
        }
        window.location.assign('/privacy#privacy-choices');
        return false;
    };

    window.addEventListener('load', function () {
        var params = new URLSearchParams(window.location.search);
        if (params.get('privacy-settings') !== '1') return;
        var attempts = 0;
        var timer = window.setInterval(function () {
            attempts += 1;
            if (typeof window.googlefc.showRevocationMessage === 'function') {
                window.clearInterval(timer);
                window.googlefc.callbackQueue.push(window.googlefc.showRevocationMessage);
            } else if (attempts >= 20) {
                window.clearInterval(timer);
                window.location.hash = 'privacy-choices';
            }
        }, 250);
    });
})();
