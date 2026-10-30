package dev.dimka.mfbenchmark;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.LockSupport;

final class ActionGenerator implements AutoCloseable {
  private final BenchConfig config;
  private final RuntimeAdapter runtime;
  private final MeasurementRecorder recorder;
  private final AtomicBoolean running = new AtomicBoolean();
  private final List<Thread> threads = new ArrayList<>();

  ActionGenerator(BenchConfig config, RuntimeAdapter runtime, MeasurementRecorder recorder) {
    this.config = config;
    this.runtime = runtime;
    this.recorder = recorder;
  }

  void start() {
    if (config.actionRate() <= 0) return;
    running.set(true);
    for (int i = 0; i < config.producerThreads(); i++) {
      final int producer = i;
      Thread thread = new Thread(() -> runProducer(producer), "action-producer-" + producer);
      thread.setDaemon(true);
      threads.add(thread);
      thread.start();
    }
  }

  private void runProducer(int producer) {
    double rate = (double) config.actionRate() / config.producerThreads();
    double perMs = rate / 1_000.0;
    double carry = 0.0;
    long windowStart = System.nanoTime();
    long window = 0L;
    long sequence = producer;

    while (running.get()) {
      long target = windowStart + window * 1_000_000L;
      long now = System.nanoTime();
      if (now < target) LockSupport.parkNanos(target - now);
      else if (now - target > 100_000_000L) windowStart = now - window * 1_000_000L;

      carry += perMs;
      int batch = (int) carry;
      carry -= batch;
      for (int i = 0; i < batch && running.get(); i++) {
        int session = (int) Math.floorMod(sequence, config.sessions());
        sequence += config.producerThreads();
        long enqueued = System.nanoTime();
        boolean ok = runtime.offerAction(session, enqueued);
        recorder.offered(ok);
      }
      window++;
    }
  }

  List<Long> threadIds() {
    return threads.stream().map(Thread::getId).toList();
  }

  @Override public void close() throws InterruptedException {
    running.set(false);
    for (Thread thread : threads) thread.join(1_000L);
  }
}
