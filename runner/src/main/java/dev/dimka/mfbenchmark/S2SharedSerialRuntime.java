package dev.dimka.mfbenchmark;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

final class S2SharedSerialRuntime implements RuntimeAdapter {
  private final BenchConfig config;
  private final MeasurementRecorder recorder;
  private final List<BaselineSession> sessions = new ArrayList<>();
  private final List<SerialExecutor> serials = new ArrayList<>();
  private ScheduledThreadPoolExecutor pool;

  S2SharedSerialRuntime(BenchConfig config, MeasurementRecorder recorder) {
    this.config = config;
    this.recorder = recorder;
  }

  @Override public String id() { return "s2"; }

  @Override public void start() {
    pool = new ScheduledThreadPoolExecutor(config.workers(), r -> {
      Thread t = new Thread(r, "s2-worker");
      t.setDaemon(true);
      return t;
    });
    pool.setRemoveOnCancelPolicy(true);
    long period = config.tickIntervalNanos();
    for (int i = 0; i < config.sessions(); i++) {
      BaselineSession session = new BaselineSession(config, recorder);
      SerialExecutor serial = new SerialExecutor(pool);
      sessions.add(session);
      serials.add(serial);
      pool.scheduleAtFixedRate(() -> serial.execute(session::step), 0L, period, TimeUnit.NANOSECONDS);
    }
  }

  @Override public boolean offerAction(int sessionIndex, long enqueuedNanos) {
    return sessions.get(sessionIndex).offer(enqueuedNanos);
  }

  @Override public long pendingActions() {
    return sessions.stream().mapToLong(BaselineSession::pending).sum();
  }

  @Override public void close() {
    if (pool != null) pool.shutdownNow();
  }
}
