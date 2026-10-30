# Соответствие стенда Практической работе №3

- **SUT:** реальный Multiplayer Framework runtime + matched baselines.
- **Источник воздействия:** Java Action generator с фиксируемым offered rate.
- **Сбор измерений:** HdrHistogram + JVM/OS MXBeans + per-second raw samples.
- **Хранилище:** persistent volume, run manifest, raw CSV, summary, logs, SHA-256.
- **Анализ:** `scripts/analyze.py`.
- **Архитектура как код:** `docs/architecture.mmd` (Mermaid).
- **Версии:** Maven/Python dependencies pinned; Java 17; Compose/Dockerfile.
- **Конфигурация вне кода:** JSON presets + request manifest.
- **Случайность:** order seed фиксируется в manifest; workload распределяется детерминированно.
- **Одна команда:** `make smoke`, `make aa`, `make full` после deployment.
- **Метаданные:** environment snapshot + runtime package versions + run config.
- **CI:** Python tests + Java Maven build/tests.
- **Повторения:** full = 10 на configuration.
- **Warm-up/measurement:** 120 s / 180 s full plan.
- **Порядок:** deterministic randomized order.
- **Единица анализа:** independently restarted JVM run.
- **Статистика:** median, range, bootstrap 95% CI; A/A permutation test.
- **A/A:** `configs/aa.json`.
- **Generator sanity:** offered/accepted/processed/backlog записываются.
- **Threats:** таблица в `docs/experimental-stand.md`.

Шаги 1-3 практической работы (подбор научных статей, синтез, RQ/H0/H1 и критерии научности) относятся к тексту отчёта, а не к программному коду стенда; их нужно оформить отдельным отчётом поверх этого артефакта.
