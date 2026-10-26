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
 * The snippet runs in this same global, so the bootstrap takes the network and
 * script restrictions away from it before the driver is installed:
 *
 * - Every guarded API becomes a locked own property of the worker global. A
 *   snippet can neither swap it nor delete it, so the native behind it stays
 *   out of reach.
 * - The native entries are removed from the prototype chain, because
 *   `Object.getPrototypeOf(self).fetch` would otherwise reach them without
 *   passing the check.
 * - The globals the checks read are captured before the snippet runs, so a
 *   snippet cannot report a foreign origin as the worker's own.
 * - The worker offers no nested worker: a child worker would carry no policy
 *   of its own.
 *
 * The policy of the worker response closes what a script cannot: a script load
 * that redirects to another origin. That policy is `connect-src 'self'`,
 * `script-src 'self' blob:` and `worker-src 'none'`; see vite.config.ts for
 * the header the dev and preview servers send and docs/web/frontend.md for
 * the header a production static server has to send.
 */
(function () {
  // A WebSocket URL carries its own scheme, so the origin check maps it back
  // to the page scheme the way the WebSocket standard does.
  var PAGE_SCHEMES = { 'ws:': 'http:', 'wss:': 'https:' };

  // Trusted intrinsics, captured before the snippet runs: the snippet shares
  // this global, so the checks must not read a global it can replace.
  var NativeURL = self.URL;
  var NativeObject = Object;
  var NativeError = Error;

  // The worker's own place, captured for the same reason.
  var WORKER_ORIGIN = self.location.origin;
  var WORKER_HREF = self.location.href;
  var WORKER_PROTOCOL = self.location.protocol;
  var WORKER_HOST = self.location.host;

  /**
   * The URL a request target points at, or null when it carries none.
   *
   * `fetch` takes a string, a URL or a Request. A URL has no `url` property,
   * so reading only `url` would treat a foreign URL as a relative one and let
   * it through.
   */
  function targetUrl(target) {
    if (typeof target === 'string') return target;
    if (!target) return null;
    if (typeof target.href === 'string') return target.href;
    if (typeof target.url === 'string') return target.url;
    return null;
  }

  function isSameOrigin(url) {
    if (typeof url !== 'string') return false;
    try {
      var target = new NativeURL(url, WORKER_HREF);
      var targetScheme = PAGE_SCHEMES[target.protocol];
      if (targetScheme) {
        var pageScheme = PAGE_SCHEMES[WORKER_PROTOCOL] || WORKER_PROTOCOL;
        return targetScheme === pageScheme && target.host === WORKER_HOST;
      }
      return target.origin === WORKER_ORIGIN;
    } catch (e) {
      return false;
    }
  }

  function guardTarget(what, target) {
    var url = targetUrl(target);
    if (url !== null && isSameOrigin(url)) return;
    throw new NativeError(
      'The code runner may only reach ' + WORKER_ORIGIN + ' (' + what + ' blocked).'
    );
  }

  /**
   * Install a replacement as a locked own property of the worker global: the
   * snippet can neither replace it nor delete it.
   */
  function lockGlobal(name, value) {
    try {
      NativeObject.defineProperty(self, name, {
        value: value,
        writable: false,
        enumerable: true,
        configurable: false,
      });
    } catch (e) {
      /* a runtime that refuses the swap keeps the entry it has */
    }
  }

  /**
   * Remove the native entry of `name` from every prototype that carries it.
   *
   * The guards live on the worker global, but the native stays reachable
   * through the prototype chain (`Object.getPrototypeOf(self).fetch`), where a
   * snippet could call it without passing the check.
   */
  function hideNative(name) {
    var proto = NativeObject.getPrototypeOf(self);
    while (proto) {
      var descriptor = NativeObject.getOwnPropertyDescriptor(proto, name);
      if (descriptor && descriptor.configurable) {
        try {
          delete proto[name];
        } catch (e) {
          /* a prototype that refuses the delete keeps its native entry */
        }
      }
      proto = NativeObject.getPrototypeOf(proto);
    }
  }

  /**
   * Copy the native constructor's own static members onto the replacement, so
   * a snippet still reads the documented constants (WebSocket.OPEN and the
   * like) instead of finding them undefined.
   */
  function copyStaticMembers(replacement, native) {
    var names = NativeObject.getOwnPropertyNames(native);
    for (var i = 0; i < names.length; i++) {
      var name = names[i];
      if (name === 'prototype' || name === 'length' || name === 'name') continue;
      var descriptor = NativeObject.getOwnPropertyDescriptor(native, name);
      if (!descriptor) continue;
      try {
        NativeObject.defineProperty(replacement, name, descriptor);
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
    var descriptor = NativeObject.getOwnPropertyDescriptor(prototype, 'constructor');
    if (!descriptor || !descriptor.configurable) return;
    NativeObject.defineProperty(prototype, 'constructor', {
      value: replacement,
      writable: descriptor.writable,
      enumerable: descriptor.enumerable,
      configurable: true,
    });
  }

  // The URL constructor is a global the origin check reads, so the snippet
  // cannot replace it with one that reports a foreign origin as its own.
  lockGlobal('URL', NativeURL);

  if (typeof self.fetch === 'function') {
    var nativeFetch = self.fetch;
    hideNative('fetch');
    lockGlobal('fetch', function (input, init) {
      guardTarget('fetch', input);
      // A redirect leaves the origin, and its target cannot be checked before
      // the request is on the wire, so the guarded fetch follows none.
      var options = NativeObject.assign({}, init || {}, { redirect: 'error' });
      return nativeFetch.call(self, input, options);
    });
  }

  if (typeof self.XMLHttpRequest === 'function') {
    var NativeXhr = self.XMLHttpRequest;
    var nativeOpen = NativeXhr.prototype.open;
    NativeXhr.prototype.open = function (method, url) {
      guardTarget('XMLHttpRequest', url);
      return nativeOpen.apply(this, arguments);
    };
    hideNative('XMLHttpRequest');
    lockGlobal('XMLHttpRequest', NativeXhr);
  }

  if (typeof self.WebSocket === 'function') {
    var NativeWebSocket = self.WebSocket;
    hideNative('WebSocket');
    lockGlobal('WebSocket', function (url, protocols) {
      guardTarget('WebSocket', url);
      return new NativeWebSocket(url, protocols);
    });
    self.WebSocket.prototype = NativeWebSocket.prototype;
    copyStaticMembers(self.WebSocket, NativeWebSocket);
    guardNativeConstructor(self.WebSocket.prototype, self.WebSocket);
  }

  if (typeof self.EventSource === 'function') {
    var NativeEventSource = self.EventSource;
    hideNative('EventSource');
    lockGlobal('EventSource', function (url, init) {
      guardTarget('EventSource', url);
      return new NativeEventSource(url, init);
    });
    self.EventSource.prototype = NativeEventSource.prototype;
    copyStaticMembers(self.EventSource, NativeEventSource);
    guardNativeConstructor(self.EventSource.prototype, self.EventSource);
  }

  // A transport of its own: WebTransport opens a QUIC connection to the URL
  // it is given, so it needs the same limit as the other transports.
  if (typeof self.WebTransport === 'function') {
    var NativeWebTransport = self.WebTransport;
    hideNative('WebTransport');
    lockGlobal('WebTransport', function (url, options) {
      guardTarget('WebTransport', url);
      return new NativeWebTransport(url, options);
    });
    self.WebTransport.prototype = NativeWebTransport.prototype;
    copyStaticMembers(self.WebTransport, NativeWebTransport);
    guardNativeConstructor(self.WebTransport.prototype, self.WebTransport);
  }

  // The driver loads the vendored engine from this origin, so the same limit
  // applies to the scripts it pulls in. Every argument is checked and handed
  // on: importScripts takes a list of scripts and loads them all.
  var nativeImportScripts = self.importScripts;
  hideNative('importScripts');
  lockGlobal('importScripts', function () {
    var urls = arguments;
    for (var i = 0; i < urls.length; i++) {
      guardTarget('importScripts', urls[i]);
    }
    return nativeImportScripts.apply(self, urls);
  });

  // A nested worker would carry no policy of its own, so the runner offers
  // none. The policy of the worker response blocks them as well.
  hideNative('Worker');

  self.onmessage = function (event) {
    var driver = event.data && event.data.driver;
    if (typeof driver !== 'string') return;
    self.onmessage = null;
    var url = NativeURL.createObjectURL(new Blob([driver], { type: 'text/javascript' }));
    importScripts(url);
    NativeURL.revokeObjectURL(url);
  };
})();
