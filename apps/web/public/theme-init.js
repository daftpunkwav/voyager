/**
 * First-paint theme and locale sync.
 *
 * Loaded as a classic script in <head> so the persisted theme and locale are
 * applied before the app renders (no flash). The store keys arrive through the
 * data attributes of the script tag, which the build replaces with the
 * configured brand storage keys.
 */
(function () {
  /** Persisted UI store state, or null when nothing is stored yet. */
  function readStoredState() {
    var script = document.currentScript;
    if (!script) return null;
    var stored = localStorage.getItem(script.getAttribute('data-ui-store-key'));
    if (!stored) {
      stored = localStorage.getItem(script.getAttribute('data-ui-store-legacy-key'));
    }
    if (!stored) return null;
    return JSON.parse(stored).state;
  }

  /** 'dark' or 'light': the stored choice, or the system preference. */
  function resolveTheme(state) {
    var theme = state ? state.theme : null;
    if (theme === 'system' || !theme) {
      theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return theme === 'dark' ? 'dark' : 'light';
  }

  /** 'zh-CN', 'en', or the first browser language that matches. */
  function resolveLocale(state) {
    var locale = state ? state.locale : null;
    if (locale !== 'zh-CN' && locale !== 'en' && locale !== 'system') {
      return 'zh-CN';
    }
    if (locale !== 'system') {
      return locale;
    }
    var langs =
      navigator.languages && navigator.languages.length
        ? navigator.languages
        : [navigator.language];
    for (var i = 0; i < langs.length; i++) {
      var tag = (langs[i] || '').toLowerCase();
      if (tag.indexOf('en') === 0) return 'en';
      if (tag.indexOf('zh') === 0) return 'zh-CN';
    }
    return 'zh-CN';
  }

  try {
    var state = readStoredState();
    document.documentElement.setAttribute('data-theme', resolveTheme(state));
    document.documentElement.setAttribute('lang', resolveLocale(state));
  } catch (e) {
    // keep the default light + zh-CN in private mode / when localStorage is unavailable
  }
})();
