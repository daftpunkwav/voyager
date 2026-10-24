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
 */
self.onmessage = function (event) {
  var driver = event.data && event.data.driver;
  if (typeof driver !== 'string') return;
  self.onmessage = null;
  var url = URL.createObjectURL(new Blob([driver], { type: 'text/javascript' }));
  importScripts(url);
  URL.revokeObjectURL(url);
};
