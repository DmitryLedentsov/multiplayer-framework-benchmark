package dev.dimka.mfbenchmark;

import org.HdrHistogram.ConcurrentHistogram;

import java.util.concurrent.atomic.LongAdder;

public final class MeasurementRecorder {
  private static final long MAX_US = 120_000_000L;
  private final ConcurrentHistogram actionLatencyUs = new ConcurrentHistogram(1, MAX_US, 3);
  private final ConcurrentHistogram stepLatenessUs = new ConcurrentHistogram(1, MAX_US, 3);
  private final LongAdder offered = new LongAdder();
  private final LongAdder accepted = new LongAdder();
  private final LongAdder rejected = new LongAdder();
  private final LongAdder processed = new LongAdder();
  private final LongAdder steps = new LongAdder();
  private final LongAdder publications = new LongAdder();
  private volatile boolean measuring;
  private volatile long measurementStartNanos = Long.MAX_VALUE;

  public void startMeasurement(long startNanos) {
    measuring = false;
    actionLatencyUs.reset();
    stepLatenessUs.reset();
    offered.reset(); accepted.reset(); rejected.reset(); processed.reset(); steps.reset(); publications.reset();
    measurementStartNanos = startNanos;
    measuring = true;
  }

  public void stopMeasurement() {
    measuring = false;
  }

  public void offered(long enqueuedNanos, boolean ok) {
    if (!measuring || enqueuedNanos < measurementStartNanos) return;
    offered.increment();
    if (ok) accepted.increment(); else rejected.increment();
  }

  public void actionProcessed(long enqueuedNanos, long nowNanos) {
    if (!measuring || enqueuedNanos < measurementStartNanos) return;
    long us = Math.max(1L, Math.min(MAX_US, (nowNanos - enqueuedNanos) / 1_000L));
    actionLatencyUs.recordValue(us);
    processed.increment();
  }

  public void step(long latenessNanos) {
    if (!measuring) return;
    long us = Math.max(1L, Math.min(MAX_US, latenessNanos / 1_000L));
    stepLatenessUs.recordValue(us);
    steps.increment();
  }

  public void publication() {
    if (measuring) publications.increment();
  }

  public Snapshot snapshot(double processCpuPercent, long heapUsedBytes, int threadCount, double elapsedSeconds) {
    long acceptedCount = accepted.sum();
    long processedCount = processed.sum();
    return new Snapshot(
        offered.sum(), acceptedCount, rejected.sum(), processedCount,
        Math.max(0L, acceptedCount - processedCount), steps.sum(), publications.sum(),
        percentileMs(actionLatencyUs, 50), percentileMs(actionLatencyUs, 95), percentileMs(actionLatencyUs, 99),
        percentileMs(stepLatenessUs, 50), percentileMs(stepLatenessUs, 95), percentileMs(stepLatenessUs, 99),
        processCpuPercent, heapUsedBytes, threadCount,
        elapsedSeconds > 0 ? processedCount / elapsedSeconds : 0.0,
        elapsedSeconds > 0 ? steps.sum() / elapsedSeconds : 0.0
    );
  }

  private static double percentileMs(ConcurrentHistogram histogram, double percentile) {
    if (histogram.getTotalCount() == 0) return 0.0;
    return histogram.getValueAtPercentile(percentile) / 1_000.0;
  }

  public record Snapshot(
      long offeredActions, long acceptedActions, long rejectedActions, long processedActions, long backlog,
      long steps, long publications,
      double actionP50Ms, double actionP95Ms, double actionP99Ms,
      double stepP50Ms, double stepP95Ms, double stepP99Ms,
      double processCpuPercent, long heapUsedBytes, int threadCount,
      double actionsPerSecond, double stepsPerSecond
  ) {}
}
