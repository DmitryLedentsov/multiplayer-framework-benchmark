package dev.dimka.mfbenchmark;

public final class SyntheticLogic {
  private final MeasurementRecorder recorder;
  private final long tickIntervalNanos;
  private final long publicationIntervalNanos;
  private long expectedTickNanos;
  private long nextPublicationNanos;
  private long checksum;
  private long ticks;

  public SyntheticLogic(MeasurementRecorder recorder, BenchConfig config) {
    this.recorder = recorder;
    this.tickIntervalNanos = config.tickIntervalNanos();
    this.publicationIntervalNanos = config.publicationIntervalNanos();
  }

  public void onAction(long enqueuedNanos) {
    long now = System.nanoTime();
    checksum = Long.rotateLeft(checksum ^ enqueuedNanos ^ 0x9E3779B97F4A7C15L, 13) + 17;
    recorder.actionProcessed(enqueuedNanos, now);
  }

  public void onTick(long nowNanos, boolean baselineOwnsPublicationCadence) {
    if (expectedTickNanos == 0L) {
      expectedTickNanos = nowNanos;
      nextPublicationNanos = nowNanos;
    }
    long lateness = Math.max(0L, nowNanos - expectedTickNanos);
    recorder.step(lateness);
    // Measure the missed opportunity, then rebase the next deadline when the
    // session fell more than one target interval behind. One delayed step
    // must not turn into permanent artificial deadline debt.
    expectedTickNanos = lateness > tickIntervalNanos
        ? nowNanos + tickIntervalNanos
        : expectedTickNanos + tickIntervalNanos;
    ticks++;
    checksum ^= (ticks * 31L) + Long.rotateLeft(checksum, 7);

    if (baselineOwnsPublicationCadence && nowNanos >= nextPublicationNanos) {
      recorder.publication();
      long intervals = Math.max(0L, nowNanos - nextPublicationNanos) / publicationIntervalNanos + 1L;
      nextPublicationNanos += intervals * publicationIntervalNanos;
    }
  }

  public long checksum() { return checksum; }
}
