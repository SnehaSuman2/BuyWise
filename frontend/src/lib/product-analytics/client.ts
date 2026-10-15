export type Properties = Record<string, string | number | boolean>;

export interface AnalyticsAdapter {
  track(event: string, properties: Properties): void;
  identify(userId: string, properties: Properties): void;
  reset(): void;
  reconcileAnonymous?(): void;
}

type Operation = (adapter: AnalyticsAdapter) => void;
type PendingOperation = { run: Operation; essential: boolean };

/** Each provider loads independently and replays actions in their original order. */
export function createAnalyticsClient(factories: Array<() => Promise<AnalyticsAdapter>>) {
  const providers = factories.map((factory) => ({
    factory,
    adapter: undefined as AnalyticsAdapter | undefined,
    queue: [] as PendingOperation[],
    loading: false,
    failed: false,
  }));

  function safelyRun(operation: Operation, adapter: AnalyticsAdapter) {
    try { operation(adapter); return true; } catch { return false; }
  }

  function dispatch(operation: Operation, essential = false) {
    for (const provider of providers) {
      if (provider.failed) continue;
      if (provider.adapter) {
        if (!safelyRun(operation, provider.adapter) && essential) provider.failed = true;
        continue;
      }
      // Bound pending work when a provider cannot finish loading. Preserve identity actions.
      if (provider.queue.length >= 100 && !essential) continue;
      provider.queue.push({ run: operation, essential });
      if (provider.loading) continue;
      provider.loading = true;
      Promise.resolve().then(provider.factory).then((adapter) => {
        provider.adapter = adapter;
        for (const queued of provider.queue) {
          if (!safelyRun(queued.run, adapter) && queued.essential) { provider.failed = true; break; }
        }
        provider.queue = [];
      }).catch(() => {
        provider.failed = true;
        provider.queue = [];
        console.warn("[analytics] provider initialization failed");
      });
    }
  }

  return {
    track: (event: string, properties: Properties) => {
      const snapshot = { ...properties };
      dispatch((adapter) => adapter.track(event, snapshot));
    },
    identify: (userId: string, properties: Properties) => {
      const snapshot = { ...properties };
      dispatch((adapter) => adapter.identify(userId, snapshot), true);
    },
    reset: () => dispatch((adapter) => adapter.reset(), true),
    reconcileAnonymous: () => dispatch((adapter) => adapter.reconcileAnonymous?.(), true),
  };
}
