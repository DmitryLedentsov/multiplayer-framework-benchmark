package dev.dimka.mfbenchmark;

final class RuntimeFactory {
  private RuntimeFactory() {}

  static RuntimeAdapter create(BenchConfig config, MeasurementRecorder recorder) {
    return switch (config.runtime().toLowerCase()) {
      case "mf", "framework", "r6" -> new MfRuntime(config, recorder);
      case "s1", "executor-per-session" -> new S1PerSessionRuntime(config, recorder);
      case "s2", "shared-serial" -> new S2SharedSerialRuntime(config, recorder);
      case "pekko", "s3" -> new PekkoRuntime(config, recorder);
      default -> throw new IllegalArgumentException("Unknown runtime: " + config.runtime());
    };
  }
}
