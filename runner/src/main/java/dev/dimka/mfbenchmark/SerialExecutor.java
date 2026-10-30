package dev.dimka.mfbenchmark;

import java.util.ArrayDeque;
import java.util.Queue;
import java.util.concurrent.Executor;

final class SerialExecutor implements Executor {
  private final Executor executor;
  private final Queue<Runnable> tasks = new ArrayDeque<>();
  private Runnable active;

  SerialExecutor(Executor executor) { this.executor = executor; }

  @Override public synchronized void execute(Runnable command) {
    tasks.offer(() -> {
      try { command.run(); }
      finally { scheduleNext(); }
    });
    if (active == null) scheduleNext();
  }

  private synchronized void scheduleNext() {
    if ((active = tasks.poll()) != null) executor.execute(active);
  }
}
