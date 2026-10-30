package dev.dimka.mfbenchmark;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.LongNode;
import com.mf.gameserver.runtime.publication.BufferedEventSink;
import com.mf.gameserver.runtime.publication.StateStore;
import com.mf.gameserver.runtime.session.GameSessionActor;
import com.mf.gameserver.runtime.session.SessionDispatcher;
import com.mf.gameserver.runtime.session.SessionScheduler;
import com.mf.gameserver.runtime.worker.GameWorker;
import com.mf.protocol.ws.ActionMessage;
import com.mf.sdk.GameAction;
import com.mf.sdk.GameSession;
import com.mf.sdk.Player;
import com.mf.sdk.Tick;

import java.util.ArrayList;
import java.util.List;

/**
 * Adapter that executes the real Multiplayer Framework worker/actor runtime.
 * This source is included only by Maven profile "framework" because the SUT package is private.
 */
public final class MfRuntime implements RuntimeAdapter {
  private final BenchConfig config;
  private final MeasurementRecorder recorder;
  private final ObjectMapper mapper = new ObjectMapper();
  private final List<GameWorker> workers = new ArrayList<>();
  private final List<Thread> workerThreads = new ArrayList<>();
  private final List<GameSessionActor> actors = new ArrayList<>();

  public MfRuntime(BenchConfig config, MeasurementRecorder recorder) {
    this.config = config;
    this.recorder = recorder;
  }

  @Override public String id() { return "mf"; }

  @Override public void start() {
    for (int i = 0; i < config.workers(); i++) {
      GameWorker worker = new GameWorker("bench-mf-" + i, config.tickRate(), (id, error) -> {});
      Thread thread = new Thread(worker, "bench-mf-" + i);
      thread.setDaemon(true);
      workers.add(worker);
      workerThreads.add(thread);
      thread.start();
    }

    for (int i = 0; i < config.sessions(); i++) {
      SyntheticLogic logic = new SyntheticLogic(recorder, config);
      GameSession game = new GameSession() {
        @Override public void onAction(Player player, GameAction action) {
          Object payload = action.payload();
          if (payload instanceof Number number) logic.onAction(number.longValue());
        }
        @Override public void tick(Tick tick) { logic.onTick(System.nanoTime(), false); }
      };
      GameSessionActor actor = new GameSessionActor(
          "session-" + i,
          game,
          1,
          null,
          new StateStore(),
          new BufferedEventSink(),
          new SessionDispatcher(),
          new SessionScheduler(),
          config.publicationRate(),
          config.capacity(),
          config.budget(),
          publication -> { if (publication.regularPublication()) recorder.publication(); },
          mapper
      );
      actor.join(new Player("p", "p"));
      actors.add(actor);
      workers.get(i % workers.size()).addSession("session-" + i, actor);
    }
  }

  @Override public boolean offerAction(int sessionIndex, long enqueuedNanos) {
    GameSessionActor actor = actors.get(sessionIndex);
    return actor.enqueue(new ActionMessage("session-" + sessionIndex, "p", "move", LongNode.valueOf(enqueuedNanos)));
  }

  @Override public long pendingActions() { return -1L; }

  @Override public void close() throws InterruptedException {
    workers.forEach(GameWorker::shutdown);
    for (Thread thread : workerThreads) thread.join(2_000L);
  }
}
