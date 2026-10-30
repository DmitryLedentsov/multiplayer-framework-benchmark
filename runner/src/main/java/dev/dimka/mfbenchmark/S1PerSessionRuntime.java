package dev.dimka.mfbenchmark;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

final class S1PerSessionRuntime implements RuntimeAdapter {
  private final BenchConfig config;
  private final MeasurementRecorder recorder;
  private final List<BaselineSession> sessions = new ArrayList<>();
  private final List<ScheduledExecutorService> executors = new ArrayList<>();

  S1PerSessionRuntime(BenchConfig config, MeasurementRecorder recorder) {
    this.config = config;
    this.recorder = recorder;
  }

  @Override public String id() { return "s1"; }

  @Override public void start() {
    long period = config.tickIntervalNanos();
    for (int i = 0; i < config.sessions(); i++) {
      BaselineSession session = new BaselineSession(config, recorder);
      sessions.add(session);
      int index = i;
      ScheduledExecutorService executor = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "s1-session-" + index);
        t.setDaemon(true);
        return t;
      });
      executors.add(executor);
      executor.scheduleAtFixedRate(session::step, 0L, period, TimeUnit.NANOSECONDS);
    }
  }

  @Override public boolean offerAction(int sessionIndex, long enqueuedNanos) {
    return sessions.get(sessionIndex).offer(enqueuedNanos);
  }

  @Override public long pendingActions() {
    return sessions.stream().mapToLong(BaselineSession::pending).sum();
  }

  @Override public void close() {
    executors.forEach(ScheduledExecutorService::shutdownNow);
  }
}
