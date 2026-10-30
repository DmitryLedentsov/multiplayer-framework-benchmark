# Multiplayer Framework Benchmark

Воспроизводимый экспериментальный стенд для ВКР по backend-фреймворку масштабируемых мультиплеерных Web-приложений.

Стенд отделён от `tank-game` и от production runtime: он разворачивается как самостоятельный Docker Compose project через **Dimka Project Manager (DPM)**, запускает каждый repetition в новой Java 17 JVM, сохраняет raw data и метаданные, а затем агрегирует независимые прогоны.

## Что исследуется

Основной SUT - `multiplayer-framework` (`GameWorker` + `GameSessionActor`). Для matched comparison реализованы:

- `mf` - фактический runtime Multiplayer Framework;
- `s1` - single scheduled executor per session;
- `s2` - fixed shared pool + serial queue per session;
- `pekko` - Apache Pekko actor per session на shared dispatcher.

Все четыре runtime получают одинаковый lightweight synthetic workload: одинаковые 50 Hz session steps, Action capacity `C`, per-step Action budget `B`, Action rate и callback arithmetic. WebSocket/STOMP, БД, внешний I/O и игровая физика не входят в scheduler benchmark.

## Метрики

Каждый run сохраняет:

- Action latency p50/p95/p99 (admission → callback);
- simulation step lateness p50/p95/p99;
- accepted/rejected Actions и rejection rate;
- processed Actions/s;
- backlog (`accepted - processed`) и его динамику;
- achieved steps/s;
- JVM process CPU, heap, live threads;
- конфигурацию, Java/OS metadata и runtime versions.

Единица анализа - **один независимо перезапущенный JVM-run**, а не отдельный Action.

## Быстрый запуск

Нужен Maven access к `DmitryLedentsov/multiplayer-framework` GitHub Packages.

```bash
cp compose.env.example /etc/multiplayer-framework-benchmark/compose.env
# Указать MAVEN_SETTINGS_FILE с GitHub Packages credentials.
docker compose up -d --build
curl http://localhost:8080/benchmark/api/health
```

UI: `http://localhost:8080/benchmark`

Smoke experiment:

```bash
make smoke
```

A/A:

```bash
make aa
```

Полный план ВКР:

```bash
make full
```

Полный план по умолчанию: 4 runtime × 7 session levels × 10 repetitions = 280 fresh-JVM runs; warm-up 120 s и measurement 180 s на run. Это длинный научный прогон, не demo-команда.

## DPM deployment

Репозиторий содержит стандартный `compose.yml`, поэтому добавляется в DPM как обычный project:

```bash
dpm project add \
  git@github.com:DmitryLedentsov/multiplayer-framework-benchmark.git \
  --branch master \
  --compose-file compose.yml
```

DPM выполняет Git checkout, Compose validation/build/up и healthcheck. Named volume `benchmark-results` не удаляется при redeploy, поэтому результаты переживают обновление стенда.

Проект использует общий `dpm-proxy` и публикуется под `/benchmark`.

## Артефакты эксперимента

```text
/data/results/<experiment-id>/
├── manifest.json
├── status.json
├── analysis.json
├── analysis.csv
├── checksums.sha256
└── runs/
    └── run-001-mf-s500-r01/
        ├── run-config.json
        ├── samples.csv
        ├── summary.json
        ├── runner.log
        └── checksums.sha256
```

`manifest.json` фиксирует план, randomization seed и окружение. `samples.csv` - raw time series. `summary.json` - итог одного run. `analysis.py` агрегирует runs по конфигурациям и считает median, min-max, deterministic bootstrap 95% CI. Для A/A дополнительно выполняется permutation test между двумя половинами repetitions.

## Критерий sustained load point

Load point считается sustained, если конфигурация удовлетворяет одновременно:

- p99 step lateness < 10 ms;
- p99 Action latency < 30 ms;
- rejection rate ≤ 0.1%;
- achieved session-step cadence ≥ 98% target;
- backlog slope в конце окна ≤ 1 Action/s.

Пороги зафиксированы в `scripts/analyze.py` и описаны в `docs/experimental-stand.md`.

## Важное ограничение reproducibility

Сейчас `multiplayer-framework` подключается как `0.5.0-SNAPSHOT`, поскольку так опубликован текущий проект. Snapshot может измениться. **Перед итоговыми экспериментами ВКР необходимо выпустить fixed Maven release/tag** и заменить `mf.version` в `runner/pom.xml`. Стенд уже записывает Maven coordinate и package version в metadata, но immutable release будет сильнее.

Также итоговые performance-runs следует проводить на выделенной 4 vCPU / 8 GB VM либо остановить остальные DPM projects, чтобы фоновая нагрузка не искажала CPU/latency.

## Структура

```text
multiplayer-framework-benchmark/
├── controller/              # Web UI + experiment orchestration
├── runner/                  # Java benchmark runner and runtime adapters
├── configs/                 # smoke / A-A / full experimental plans
├── scripts/analyze.py       # statistical aggregation
├── docs/
│   ├── architecture.mmd
│   └── experimental-stand.md
├── compose.yml
├── Dockerfile
└── .github/workflows/ci.yml
```

Подробное соответствие требованиям ПР3, план, метрики, A/A и threats to validity: [`docs/experimental-stand.md`](docs/experimental-stand.md).
