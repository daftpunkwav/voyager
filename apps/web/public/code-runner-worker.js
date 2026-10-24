/**
 * Code-runner worker bootstrap.
 *
 * The page ships the engine driver as source (it embeds the tested output
 * helpers), so the worker installs that driver here and then behaves as the
 * driver. Serving the worker as its own script is what keeps the engines
 * compiling snippets out of the page policy: a worker loaded from a URL gets
 * the Content Security Policy of its own response, while a blob worker would
 * inherit the page policy.
 */
self.onmessage = function (event) {
  var driver = event.data && event.data.driver;
  if (typeof driver !== 'string') return;
  self.onmessage = null;
  try {
    (0, eval)(driver);
  } catch (err) {
    self.postMessage({
      ok: false,
      output: '',
      error: { name: 'Error', message: 'Failed to start the execution worker: ' + err },
    });
  }
};
