package dev.dimka.mfbenchmark;

import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;

final class BaselineSession {
  private final ConcurrentLinkedQueue<Long> actions = new ConcurrentLinkedQueue<>();
  private final AtomicInteger pending = new AtomicInteger();
  private final int capacity;
  private final int budget;
  private final SyntheticLogic logic;

  BaselineSession(BenchConfig config, MeasurementRecorder recorder) {
    this.capacity = config.capacity();
    this.budget = config.budget();
    this.logic = new SyntheticLogic(recorder, config);
  }

  boolean offer(long enqueuedNanos) {
    int queued = pending.incrementAndGet();
    if (queued > capacity) {
      pending.decrementAndGet();
      return false;
    }
    actions.offer(enqueuedNanos);
    return true;
  }

  void step() {
    for (int i = 0; i < budget; i++) {
      Long enqueued = actions.poll();
      if (enqueued == null) break;
      pending.decrementAndGet();
      logic.onAction(enqueued);
    }
    logic.onTick(System.nanoTime(), true);
  }

  int pending() { return pending.get(); }
}
