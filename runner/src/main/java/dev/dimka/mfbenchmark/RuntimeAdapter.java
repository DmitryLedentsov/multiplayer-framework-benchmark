package dev.dimka.mfbenchmark;

public interface RuntimeAdapter extends AutoCloseable {
  String id();
  void start() throws Exception;
  boolean offerAction(int sessionIndex, long enqueuedNanos);
  default long pendingActions() { return -1L; }
  @Override void close() throws Exception;
}
