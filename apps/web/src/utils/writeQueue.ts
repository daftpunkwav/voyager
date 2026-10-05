/**
 * Per-key write serialization: each enqueue chains behind the previous write
 * for the same key, so rapid updates cannot commit out of order and an older
 * write can never land last. The writer's first parameter is the queue key.
 * A failed write does not poison the key's queue, and different keys never
 * wait on each other. One settled tail per key is retained (key sets are
 * small and finite).
 */
export function createKeyedWriteQueue<K, Args extends unknown[]>(
  write: (key: K, ...args: Args) => Promise<unknown>
): (key: K, ...args: Args) => Promise<void> {
  const tails = new Map<K, Promise<void>>();
  return (key, ...args) => {
    const prev = tails.get(key) ?? Promise.resolve();
    const next: Promise<void> = prev
      .catch((): void => {})
      .then(async () => {
        await write(key, ...args);
      });
    tails.set(
      key,
      next.catch((): void => {})
    );
    return next;
  };
}
