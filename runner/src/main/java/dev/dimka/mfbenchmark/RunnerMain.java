package dev.dimka.mfbenchmark;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.io.BufferedWriter;
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public final class RunnerMain {
  private static final ObjectMapper MAPPER = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);

  public static void main(String[] args) throws Exception {
    if (args.length == 1 && "--describe".equals(args[0])) {
      System.out.println(MAPPER.writeValueAsString(environment()));
      return;
    }
    if (args.length != 2 || !"--config".equals(args[0])) {
      System.err.println("Usage: java -jar benchmark-runner.jar --config /path/run.json");
      System.exit(2);
    }

    BenchConfig config = MAPPER.readValue(Path.of(args[1]).toFile(), BenchConfig.class);
    Files.createDirectories(config.outputPath());
    MeasurementRecorder recorder = new MeasurementRecorder();
    long startedEpochMs = System.currentTimeMillis();

    try (RuntimeAdapter runtime = RuntimeFactory.create(config, recorder)) {
      runtime.start();
      try (ActionGenerator generator = new ActionGenerator(config, runtime, recorder)) {
        generator.start();
        sleepSeconds(config.warmupSeconds());
        long measurementStart = System.nanoTime();
        recorder.startMeasurement(measurementStart);
        double generatorCpuPercent = sample(config, recorder, runtime, generator, measurementStart);
        recorder.stopMeasurement();
        generator.close();
        double elapsed = (System.nanoTime() - measurementStart) / 1_000_000_000.0;
        MeasurementRecorder.Snapshot finalSnapshot = recorder.snapshot(cpuPercent(), heapUsed(), threadCount(), elapsed);
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("status", "completed");
        summary.put("startedAtEpochMs", startedEpochMs);
        summary.put("finishedAtEpochMs", System.currentTimeMillis());
        summary.put("runtime", runtime.id());
        summary.put("config", config);
        summary.put("environment", environment());
        summary.put("metrics", finalSnapshot);
        summary.put("generatorCpuPercent", generatorCpuPercent);
        MAPPER.writeValue(config.outputPath().resolve("summary.json").toFile(), summary);
      }
    } catch (Throwable failure) {
      Map<String, Object> failed = new LinkedHashMap<>();
      failed.put("status", "failed");
      failed.put("runtime", config.runtime());
      failed.put("config", config);
      failed.put("environment", environment());
      failed.put("error", failure.getClass().getName() + ": " + failure.getMessage());
      MAPPER.writeValue(config.outputPath().resolve("summary.json").toFile(), failed);
      throw failure;
    }
  }

  private static double sample(BenchConfig config, MeasurementRecorder recorder, RuntimeAdapter runtime, ActionGenerator generator, long measurementStart) throws Exception {
    Path csv = config.outputPath().resolve("samples.csv");
    var threadMx = ManagementFactory.getThreadMXBean();
    if (threadMx.isThreadCpuTimeSupported() && !threadMx.isThreadCpuTimeEnabled()) {
      threadMx.setThreadCpuTimeEnabled(true);
    }
    long generatorCpuStart = sumThreadCpu(threadMx, generator.threadIds());
    try (BufferedWriter writer = Files.newBufferedWriter(csv)) {
      writer.write("elapsed_s,cpu_percent,generator_cpu_percent,heap_used_bytes,threads,offered,accepted,rejected,processed,backlog,actions_per_s,steps_per_s,action_p50_ms,action_p95_ms,action_p99_ms,step_p50_ms,step_p95_ms,step_p99_ms,pending_runtime\n");
      long end = measurementStart + config.measurementSeconds() * 1_000_000_000L;
      while (System.nanoTime() < end) {
        Thread.sleep(config.sampleIntervalMs());
        long now = System.nanoTime();
        double elapsed = (now - measurementStart) / 1_000_000_000.0;
        double generatorCpu = normalizedThreadCpuPercent(
            threadMx, generator.threadIds(), generatorCpuStart, now - measurementStart);
        MeasurementRecorder.Snapshot s = recorder.snapshot(cpuPercent(), heapUsed(), threadCount(), elapsed);
        writer.write(String.join(",",
            f(elapsed), f(s.processCpuPercent()), f(generatorCpu),
            Long.toString(s.heapUsedBytes()), Integer.toString(s.threadCount()),
            Long.toString(s.offeredActions()), Long.toString(s.acceptedActions()), Long.toString(s.rejectedActions()),
            Long.toString(s.processedActions()), Long.toString(s.backlog()), f(s.actionsPerSecond()), f(s.stepsPerSecond()),
            f(s.actionP50Ms()), f(s.actionP95Ms()), f(s.actionP99Ms()),
            f(s.stepP50Ms()), f(s.stepP95Ms()), f(s.stepP99Ms()),
            Long.toString(runtime.pendingActions())));
        writer.write("\n");
        writer.flush();
      }
    }
    long elapsedNanos = Math.max(1L, System.nanoTime() - measurementStart);
    return normalizedThreadCpuPercent(
        threadMx, generator.threadIds(), generatorCpuStart, elapsedNanos);
  }

  private static long sumThreadCpu(java.lang.management.ThreadMXBean bean, java.util.List<Long> ids) {
    if (!bean.isThreadCpuTimeSupported()) return -1L;
    long total = 0L;
    for (long id : ids) {
      long value = bean.getThreadCpuTime(id);
      if (value > 0L) total += value;
    }
    return total;
  }

  private static double normalizedThreadCpuPercent(
      java.lang.management.ThreadMXBean bean,
      java.util.List<Long> ids,
      long startCpu,
      long elapsedNanos
  ) {
    if (startCpu < 0L || elapsedNanos <= 0L) return -1.0;
    long current = sumThreadCpu(bean, ids);
    if (current < 0L) return -1.0;
    int processors = Math.max(1, Runtime.getRuntime().availableProcessors());
    return Math.max(0.0, (current - startCpu) * 100.0 / elapsedNanos / processors);
  }

  private static String f(double value) { return String.format(java.util.Locale.ROOT, "%.6f", value); }
  private static void sleepSeconds(int seconds) throws InterruptedException { if (seconds > 0) Thread.sleep(seconds * 1_000L); }
  private static long heapUsed() { Runtime r = Runtime.getRuntime(); return r.totalMemory() - r.freeMemory(); }
  private static int threadCount() { return ManagementFactory.getThreadMXBean().getThreadCount(); }

  private static double cpuPercent() {
    var os = ManagementFactory.getOperatingSystemMXBean();
    if (os instanceof com.sun.management.OperatingSystemMXBean sun) {
      double load = sun.getProcessCpuLoad();
      return load < 0 ? -1.0 : load * 100.0;
    }
    return -1.0;
  }

  private static Map<String, Object> environment() {
    Map<String, Object> env = new LinkedHashMap<>();
    env.put("capturedAt", Instant.now().toString());
    env.put("javaVersion", System.getProperty("java.version"));
    env.put("javaVm", System.getProperty("java.vm.name"));
    env.put("osName", System.getProperty("os.name"));
    env.put("osVersion", System.getProperty("os.version"));
    env.put("osArch", System.getProperty("os.arch"));
    env.put("availableProcessors", Runtime.getRuntime().availableProcessors());
    env.put("maxHeapBytes", Runtime.getRuntime().maxMemory());
    env.put("inputArguments", ManagementFactory.getRuntimeMXBean().getInputArguments());
    env.put("frameworkPackageVersion", versionOf("com.mf.gameserver.runtime.worker.GameWorker"));
    env.put("pekkoPackageVersion", versionOf("org.apache.pekko.actor.ActorSystem"));
    return env;
  }

  private static String versionOf(String className) {
    try {
      Class<?> type = Class.forName(className);
      String version = type.getPackage().getImplementationVersion();
      return version == null ? "unknown" : version;
    } catch (ClassNotFoundException e) {
      return "not-packaged";
    }
  }
}
