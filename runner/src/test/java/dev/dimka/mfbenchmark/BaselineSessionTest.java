package dev.dimka.mfbenchmark;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class BaselineSessionTest {
  @Test
  void enforcesCapacityAndBudgetedProgress() {
    BenchConfig config = new BenchConfig("s2", 1, 0, 50, 20, 1, 3, 2, 0, 1, 1, 1000, "target/test-run");
    MeasurementRecorder recorder = new MeasurementRecorder();
    BaselineSession session = new BaselineSession(config, recorder);
    long now = System.nanoTime();
    assertTrue(session.offer(now));
    assertTrue(session.offer(now));
    assertTrue(session.offer(now));
    assertFalse(session.offer(now));
    assertEquals(3, session.pending());
    session.step();
    assertEquals(1, session.pending());
    session.step();
    assertEquals(0, session.pending());
  }
}
