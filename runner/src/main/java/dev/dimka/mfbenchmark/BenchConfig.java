package dev.dimka.mfbenchmark;

import java.nio.file.Path;

public record BenchConfig(
    String runtime,
    int sessions,
    int actionRate,
    int tickRate,
    int publicationRate,
    int workers,
    int capacity,
    int budget,
    int warmupSeconds,
    int measurementSeconds,
    int producerThreads,
    int sampleIntervalMs,
    String outputDir
) {
  public BenchConfig {
    if (runtime == null || runtime.isBlank()) throw new IllegalArgumentException("runtime is required");
    if (sessions < 1) throw new IllegalArgumentException("sessions must be >= 1");
    if (actionRate < 0) throw new IllegalArgumentException("actionRate must be >= 0");
    if (tickRate < 1) throw new IllegalArgumentException("tickRate must be >= 1");
    if (publicationRate < 1) throw new IllegalArgumentException("publicationRate must be >= 1");
    if (workers < 1) throw new IllegalArgumentException("workers must be >= 1");
    if (capacity < 1) throw new IllegalArgumentException("capacity must be >= 1");
    if (budget < 1) throw new IllegalArgumentException("budget must be >= 1");
    if (warmupSeconds < 0) throw new IllegalArgumentException("warmupSeconds must be >= 0");
    if (measurementSeconds < 1) throw new IllegalArgumentException("measurementSeconds must be >= 1");
    if (producerThreads < 1) throw new IllegalArgumentException("producerThreads must be >= 1");
    if (sampleIntervalMs < 100) throw new IllegalArgumentException("sampleIntervalMs must be >= 100");
    if (outputDir == null || outputDir.isBlank()) throw new IllegalArgumentException("outputDir is required");
  }

  public Path outputPath() { return Path.of(outputDir); }
  public long tickIntervalNanos() { return 1_000_000_000L / tickRate; }
  public long publicationIntervalNanos() { return 1_000_000_000L / publicationRate; }
}
