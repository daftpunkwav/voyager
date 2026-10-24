/**
 * First-paint theme and locale sync.
 *
 * Loaded as a classic script in <head> so the persisted theme and locale are
 * applied before the app renders (no flash). The store keys arrive through the
 * data attributes of the script tag, which the build replaces with the
 * configured brand storage keys.
 */
(function () {
  try {
    var script = document.currentScript;
    var storeKey = script ? script.getAttribute('data-ui-store-key') : null;
    var legacyStoreKey = script ? script.getAttribute('data-ui-store-legacy-key') : null;
    var stored = storeKey ? localStorage.getItem(storeKey) : null;
    if (!stored && legacyStoreKey) stored = localStorage.getItem(legacyStoreKey);

    var theme = stored ? JSON.parse(stored).state?.theme : null;
    if (theme === 'system' || !theme) {
      theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', theme === 'dark' ? 'dark' : 'light');

    // UI language first-paint sync: read the locale choice persisted by uiStore and set html[lang]
    // (screen readers depend on it; for 'system'/missing, match via navigator with a zh-CN fallback, matching the backend SSOT default)
    var state = stored ? JSON.parse(stored).state : null;
    var locale = state ? state.locale : null;
    if (locale !== 'zh-CN' && locale !== 'en' && locale !== 'system') {
      locale = 'zh-CN';
    }
    if (locale === 'system') {
      var langs =
        navigator.languages && navigator.languages.length
          ? navigator.languages
          : [navigator.language];
      locale = 'zh-CN';
      for (var i = 0; i < langs.length; i++) {
        var tag = (langs[i] || '').toLowerCase();
        if (tag.indexOf('en') === 0) {
          locale = 'en';
          break;
        }
        if (tag.indexOf('zh') === 0) {
          locale = 'zh-CN';
          break;
        }
      }
    }
    document.documentElement.setAttribute('lang', locale);
  } catch (e) {
    // keep the default light + zh-CN in private mode / when localStorage is unavailable
  }
})();
