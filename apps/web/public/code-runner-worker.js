/**
 * Code-runner worker bootstrap.
 *
 * The page ships the engine driver as source (it embeds the tested output
 * helpers), so the worker installs that driver here and then behaves as the
 * driver. Serving the worker as its own script is what keeps the engines
 * compiling snippets out of the page policy: a worker loaded from a URL gets
 * the Content Security Policy of its own response, while a blob worker would
 * inherit the page policy.
 *
 * The driver is imported as a script rather than evaluated here, so the code
 * that compiles snippets stays in the driver and nowhere else.
 *
 * The worker policy is the policy of its own response, so the page policy does
 * not reach it. The page policy used to hold the runner to same-origin
 * requests; the same limit is enforced here, so a snippet cannot hand what it
 * reads to a third party.
 */
(function () {
  function isSameOrigin(url) {
    try {
      return new URL(url, self.location.href).origin === self.location.origin;
    } catch (e) {
      return false;
    }
  }

  function guardTarget(what, target) {
    var url = typeof target === 'string' ? target : target && target.url;
    if (isSameOrigin(url)) return;
    throw new Error(
      'The code runner may only reach ' + self.location.origin + ' (' + what + ' blocked).'
    );
  }

  if (typeof self.fetch === 'function') {
    var nativeFetch = self.fetch;
    self.fetch = function (input, init) {
      guardTarget('fetch', input);
      return nativeFetch.call(self, input, init);
    };
  }

  if (typeof self.XMLHttpRequest === 'function') {
    var nativeOpen = self.XMLHttpRequest.prototype.open;
    self.XMLHttpRequest.prototype.open = function (method, url) {
      guardTarget('XMLHttpRequest', url);
      return nativeOpen.apply(this, arguments);
    };
  }

  if (typeof self.WebSocket === 'function') {
    var NativeWebSocket = self.WebSocket;
    self.WebSocket = function (url, protocols) {
      guardTarget('WebSocket', url);
      return new NativeWebSocket(url, protocols);
    };
    self.WebSocket.prototype = NativeWebSocket.prototype;
  }

  if (typeof self.EventSource === 'function') {
    var NativeEventSource = self.EventSource;
    self.EventSource = function (url, init) {
      guardTarget('EventSource', url);
      return new NativeEventSource(url, init);
    };
    self.EventSource.prototype = NativeEventSource.prototype;
  }

  // The driver loads the vendored engine from this origin, so the same limit
  // applies to the scripts it pulls in.
  var nativeImportScripts = self.importScripts;
  self.importScripts = function (url) {
    guardTarget('importScripts', url);
    return nativeImportScripts.call(self, url);
  };

  self.onmessage = function (event) {
    var driver = event.data && event.data.driver;
    if (typeof driver !== 'string') return;
    self.onmessage = null;
    var url = URL.createObjectURL(new Blob([driver], { type: 'text/javascript' }));
    importScripts(url);
    URL.revokeObjectURL(url);
  };
})();
