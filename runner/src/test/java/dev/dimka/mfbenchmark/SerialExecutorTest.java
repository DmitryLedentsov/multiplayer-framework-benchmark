package dev.dimka.mfbenchmark;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SerialExecutorTest {
  @Test
  void preservesPerSessionOrder() throws Exception {
    var pool = Executors.newFixedThreadPool(4);
    try {
      SerialExecutor serial = new SerialExecutor(pool);
      List<Integer> values = java.util.Collections.synchronizedList(new ArrayList<>());
      CountDownLatch latch = new CountDownLatch(100);
      for (int i = 0; i < 100; i++) {
        int value = i;
        serial.execute(() -> { values.add(value); latch.countDown(); });
      }
      assertTrue(latch.await(3, TimeUnit.SECONDS));
      for (int i = 0; i < 100; i++) assertEquals(i, values.get(i));
    } finally {
      pool.shutdownNow();
    }
  }
}
