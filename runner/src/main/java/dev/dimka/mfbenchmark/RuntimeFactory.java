package dev.dimka.mfbenchmark;

final class RuntimeFactory {
  private RuntimeFactory() {}

  static RuntimeAdapter create(BenchConfig config, MeasurementRecorder recorder) {
    return switch (config.runtime().toLowerCase()) {
      case "mf", "framework", "r6" -> framework(config, recorder);
      case "s1", "executor-per-session" -> new S1PerSessionRuntime(config, recorder);
      case "s2", "shared-serial" -> new S2SharedSerialRuntime(config, recorder);
      case "pekko", "s3" -> new PekkoRuntime(config, recorder);
      default -> throw new IllegalArgumentException("Unknown runtime: " + config.runtime());
    };
  }

  private static RuntimeAdapter framework(BenchConfig config, MeasurementRecorder recorder) {
    try {
      Class<?> type = Class.forName("dev.dimka.mfbenchmark.MfRuntime");
      return (RuntimeAdapter) type
          .getConstructor(BenchConfig.class, MeasurementRecorder.class)
          .newInstance(config, recorder);
    } catch (ReflectiveOperationException e) {
      throw new IllegalStateException(
          "Multiplayer Framework adapter is not packaged. Build the runner with Maven profile -Pframework.",
          e
      );
    }
  }
}
