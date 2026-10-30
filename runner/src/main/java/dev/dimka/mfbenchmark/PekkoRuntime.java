package dev.dimka.mfbenchmark;

import com.typesafe.config.Config;
import com.typesafe.config.ConfigFactory;
import org.apache.pekko.actor.AbstractActor;
import org.apache.pekko.actor.ActorRef;
import org.apache.pekko.actor.ActorSystem;
import org.apache.pekko.actor.Cancellable;
import org.apache.pekko.actor.Props;
import org.apache.pekko.japi.Creator;

import java.time.Duration;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Queue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

final class PekkoRuntime implements RuntimeAdapter {
  private final BenchConfig config;
  private final MeasurementRecorder recorder;
  private final List<ActorRef> actors = new ArrayList<>();
  private final List<AtomicInteger> pending = new ArrayList<>();
  private final List<Cancellable> timers = new ArrayList<>();
  private ActorSystem system;

  PekkoRuntime(BenchConfig config, MeasurementRecorder recorder) {
    this.config = config;
    this.recorder = recorder;
  }

  @Override public String id() { return "pekko"; }

  @Override public void start() {
    String conf = "pekko.actor.default-dispatcher.fork-join-executor.parallelism-min=" + config.workers() + "\n" +
        "pekko.actor.default-dispatcher.fork-join-executor.parallelism-max=" + config.workers() + "\n" +
        "pekko.actor.default-dispatcher.fork-join-executor.parallelism-factor=1.0\n" +
        "pekko.loglevel=WARNING\n";
    Config pekkoConfig = ConfigFactory.parseString(conf).withFallback(ConfigFactory.load());
    system = ActorSystem.create("mf-benchmark-pekko", pekkoConfig);
    Duration interval = Duration.ofNanos(config.tickIntervalNanos());

    for (int i = 0; i < config.sessions(); i++) {
      AtomicInteger reservation = new AtomicInteger();
      pending.add(reservation);
      ActorRef ref = system.actorOf(Props.create(SessionActor.class,
          (Creator<SessionActor>) () -> new SessionActor(config, recorder, reservation)), "session-" + i);
      actors.add(ref);
      timers.add(system.scheduler().scheduleAtFixedRate(
          Duration.ZERO, interval, ref, Tick.INSTANCE, system.dispatcher(), ActorRef.noSender()));
    }
  }

  @Override public boolean offerAction(int sessionIndex, long enqueuedNanos) {
    AtomicInteger reservation = pending.get(sessionIndex);
    int queued = reservation.incrementAndGet();
    if (queued > config.capacity()) {
      reservation.decrementAndGet();
      return false;
    }
    actors.get(sessionIndex).tell(new Action(enqueuedNanos), ActorRef.noSender());
    return true;
  }

  @Override public long pendingActions() { return pending.stream().mapToLong(AtomicInteger::get).sum(); }

  @Override public void close() throws Exception {
    timers.forEach(Cancellable::cancel);
    if (system != null) {
      system.terminate();
      system.getWhenTerminated().toCompletableFuture().get(5, TimeUnit.SECONDS);
    }
  }

  public enum Tick { INSTANCE }
  public record Action(long enqueuedNanos) {}

  public static final class SessionActor extends AbstractActor {
    private final int budget;
    private final Queue<Long> actions = new ArrayDeque<>();
    private final AtomicInteger pending;
    private final SyntheticLogic logic;

    public SessionActor(BenchConfig config, MeasurementRecorder recorder, AtomicInteger pending) {
      this.budget = config.budget();
      this.pending = pending;
      this.logic = new SyntheticLogic(recorder, config);
    }

    @Override public Receive createReceive() {
      return receiveBuilder()
          .match(Action.class, action -> actions.offer(action.enqueuedNanos()))
          .matchEquals(Tick.INSTANCE, ignored -> step())
          .build();
    }

    private void step() {
      for (int i = 0; i < budget; i++) {
        Long enqueued = actions.poll();
        if (enqueued == null) break;
        pending.decrementAndGet();
        logic.onAction(enqueued);
      }
      logic.onTick(System.nanoTime(), true);
    }
  }
}
