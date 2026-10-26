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
  // A WebSocket URL carries its own scheme, so the origin check maps it back
  // to the page scheme the way the WebSocket standard does.
  var PAGE_SCHEMES = { 'ws:': 'http:', 'wss:': 'https:' };

  function isSameOrigin(url) {
    try {
      var target = new URL(url, self.location.href);
      var targetScheme = PAGE_SCHEMES[target.protocol];
      if (targetScheme) {
        var pageScheme = PAGE_SCHEMES[self.location.protocol] || self.location.protocol;
        return targetScheme === pageScheme && target.host === self.location.host;
      }
      return target.origin === self.location.origin;
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

  /**
   * Copy the native constructor's own static members onto the replacement, so
   * a snippet still reads the documented constants (WebSocket.OPEN and the
   * like) instead of finding them undefined.
   */
  function copyStaticMembers(replacement, native) {
    var names = Object.getOwnPropertyNames(native);
    for (var i = 0; i < names.length; i++) {
      var name = names[i];
      if (name === 'prototype' || name === 'length' || name === 'name') continue;
      var descriptor = Object.getOwnPropertyDescriptor(native, name);
      if (!descriptor) continue;
      try {
        Object.defineProperty(replacement, name, descriptor);
      } catch (e) {
        /* a member the runtime refuses to copy stays out */
      }
    }
  }

  /**
   * Point the prototype at the replacement constructor: the native one stays
   * reachable through `prototype.constructor`, and a snippet could use it to
   * open a connection the guard refuses.
   */
  function guardNativeConstructor(prototype, replacement) {
    var descriptor = Object.getOwnPropertyDescriptor(prototype, 'constructor');
    if (!descriptor || !descriptor.configurable) return;
    Object.defineProperty(prototype, 'constructor', {
      value: replacement,
      writable: descriptor.writable,
      enumerable: descriptor.enumerable,
      configurable: true,
    });
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
    copyStaticMembers(self.WebSocket, NativeWebSocket);
    guardNativeConstructor(self.WebSocket.prototype, self.WebSocket);
  }

  if (typeof self.EventSource === 'function') {
    var NativeEventSource = self.EventSource;
    self.EventSource = function (url, init) {
      guardTarget('EventSource', url);
      return new NativeEventSource(url, init);
    };
    self.EventSource.prototype = NativeEventSource.prototype;
    copyStaticMembers(self.EventSource, NativeEventSource);
    guardNativeConstructor(self.EventSource.prototype, self.EventSource);
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
