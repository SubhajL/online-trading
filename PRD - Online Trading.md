Got it. Here’s a concrete, production-grade architecture and tech-stack blueprint for **PRD v1.1 (Spot \+ Futures-ready)** that you can hand to engineering and start building tomorrow.

# **1\) High-level architecture (three planes)**

**Data plane (real-time)**

WS ingestors → Feature/SMC bots → Regime/News/Funding guards → Decision engine → Order router → Exchange

**Control plane (batch & ops)**

Backtester & Paper broker → Parameter store → Risk limits → Calendars/Funding schedules → A/B & reporting

**Experience plane (operator & alerts)**

Next.js UI (charts, overlays, PB) → BFF API/WS → Telegram & LINE alerts

           ┌─────────────┐       ┌──────────────────┐  
WS (Spot/Fut)│ Ingestors   │  ──▶  │ Feature Engine   │──┐  
(Binance)    └─────────────┘       └──────────────────┘  │  
            REST backfill      ┌──────────────────┐      │  Kafka/NATS  
                               │ SMC Engine       │──┐   ▼  
                               └──────────────────┘  │  ┌────────────────┐  
                     ┌──────────────────┐            ├─▶│ Decision Engine │─▶ Order Router ─▶ Binance  
                     │ Retest Analyzer  │────────────┘  └────────────────┘  
                     └──────────────────┘    ▲  ▲   Guards: News/Vol/Funding/ATR  
                                             │  │  
                       ┌──────────────────┐  │  └───────────┐  
                       │ Regime/Vol Bot   │──┘              │  
                       └──────────────────┘                  │  
                       ┌──────────────────┐                  │  
                       │ News Calendar    │──────────────────┘  
                       └──────────────────┘  
     UI (Next.js) ─▶ BFF API/WS ─▶ TimescaleDB/Redis ◀─ Backtester/Paper Broker

# **2\) Tech stack (battle-tested choices)**

**Languages**

* **Python** (signals, backtests, SMC logic; rich quant ecosystem)

* **TypeScript/Node** (BFF/API, alerts, lightweight services)

* **Go** *(optional but recommended)* for the **Order Router** (latency, concurrency, strong HTTP/TLS)

**Frameworks & libs**

* Python: **FastAPI**, **pydantic**, **numpy/pandas/numba**, **vectorbt** (or **backtrader**) for backtests

* TypeScript: **NestJS** or **Express** (BFF), **BullMQ** for jobs (if needed)

* Go: stdlib \+ **fiber/chi** (router), **go-hmac** for signing

* Charting: **Lightweight Charts** (TradingView’s open library) in Next.js; custom overlays for SMC zones

* Indicators: **pandas-ta** (EMA/RSI/MACD/ATR/BB); custom SMC module (ZigZag, FVG, OB)

* Messaging: **Redpanda/Kafka** (prod) or **NATS** (simpler); **Redis Streams** if you want minimal footprint

* Storage: **PostgreSQL \+ TimescaleDB** (candles/indicators/orders), **Redis** (hot state), **MinIO/S3** (backtests/reports)

* Secrets: **HashiCorp Vault** or cloud KMS; local dev via **doppler** or **1Password CLI**

* Observability: **OpenTelemetry** \+ **Prometheus/Grafana** (metrics), **Loki** (logs), **Tempo/Jaeger** (traces)

* Deploy: **Docker** (+ Compose for dev), **Kubernetes** (+ Helm) for prod, **GitHub Actions** CI/CD

# **3\) Services (clear responsibilities & APIs)**

## **3.1 WS Ingestors (Spot & Futures)**

* **Python asyncio** processes; one per venue:

  * **binance\_spot\_ingestor**: wss://stream.binance.com/stream?streams=btcusdt@kline\_1m/...

  * **binance\_usdm\_ingestor**: wss://fstream.binance.com/stream?...

* Behavior:

  * Dedup on (symbol, tf, open\_time)

  * Only emit candle when k.x \== true (closed)

  * On reconnect: **REST backfill** to fill gaps

* Output:

  * Topic candles.v1 (Kafka/NATS) and **upserts** to candles\_\* tables

## **3.2 Feature Engine**

* Consumes candles.v1, computes **EMA20/50/200, RSI14, MACD(12/26/9), ATR14, BB(20,2), VWAP/VWMA**

* Emits features.v1 events and writes to indicators table

* Stateless; idempotent on (symbol, tf, ts)

## **3.3 SMC Engine**

* Input: candles.v1 (closed), optionally features.v1 (ATR for thresholds)

* Logic:

  * Pivots via **ZigZag** (ATR-scaled) or **N-bar pivots (N=3–5)**

  * Maintain **HH/HL vs LH/LL** state

  * **CHOCH**: close across **last HL/LH**; **BOS**: close across **prior external swing**

  * **FVG**: 3-bar rule; **OB**: last opposite candle range preceding BOS

* Output:

  * swings.v1, smc\_events.v1 (CHOCH/BOS), zones.v1 (OB/FVG)

## **3.4 Retest Analyzer**

* Waits up to **N bars** after BOS (default ≤8 on 15m) for price to **enter** OB/FVG band (tolerance 0.25×ATR)

* Confirms with close in direction or micro-BOS on sub-TF \+ **MACD hist uptick** \+ **RSI 40–55 bounce**

* Emits signals\_raw.v1 with candidate entry, SL proposal, and 1.5R/2R/3R skeleton TPs

## **3.5 Regime/Volatility Bot**

* Computes **trend vs range** classifier (e.g., ADX/BB-width/ATR percentiles)

* Emits regime.v1 (TREND/RANGE/SHOCK), used as gate

## **3.6 News/Funding Guards**

* **Calendar service**: JSON/CSV/Google Sheet → events (ts\_start, ts\_end, severity HIGH/MED)

* **Funding scheduler** (Futures): pulls predicted/next funding; issues funding\_window.v1

* A tiny **guard** library exposed to Decision engine:

  * news\_guard(now) → SAFE/BLOCK

  * funding\_guard(symbol, now) → SAFE/BLOCK

  * vol\_guard(symbol, now) → OK/CHOP/SHOCK

## **3.7 Decision Engine**

* Inputs: latest signals\_raw.v1, regime.v1, guards, current positions & risk budget

* Rules (defaults from PRD):

  * **News SAFE** & not CHOP → require **Structure setup** (CHOCH→BOS) **AND** (**Retest OK** OR **Indicator confluence**)

  * Build order **bracket** (entry/SL \+ TP ladder)

  * Position size: **fixed-fractional 0.5%** per trade, ATR-scaled; symbol & daily DD caps enforced

  * **Futures-aware**: leverage ≤3×, ReduceOnly TPs, STOP\_MARKET SL, funding guard

* Output: decision.v1 → Order Router

## **3.8 Order Router (Spot \+ USD-M Futures)**

* **Go** (preferred) or Node/TS service; lowest latency; strict idempotency

* Adapters:

  * **Spot**: POST /api/v3/order (LIMIT/MARKET, **simulate bracket** with multiple TP limits \+ stop-limit)

  * **USD-M Futures**: POST /fapi/v1/order (leverage, ReduceOnly, STOP\_MARKET)

* Responsibilities:

  * **Rounding** with exchangeInfo (PRICE\_FILTER, LOT\_SIZE, MIN\_NOTIONAL)

  * **Idempotent** newClientOrderId

  * Reconcile fills → orders & positions tables; publish order\_update.v1

  * **Kill-switch** on error bursts / DD breach / guard events

## **3.9 Backtester & Paper Broker**

* **Backtester** (Python): shared feature/SMC library; vectorized \+ event-driven intrabar fill model; fees & slippage; walk-forward

* **Paper broker**: mimics Router API, fills from market data with slippage; separate DB schema paper\_\*

## **3.10 BFF API/WS \+ Front-End**

* **BFF (NestJS/FastAPI)**:

  * REST: /symbols, /candles, /indicators, /zones, /signals, /decisions, /orders

  * WS: push updates (new candles closed, signals, decisions)

  * Auth (JWT) \+ RBAC (view/trade/admin)

* **UI (Next.js \+ Tailwind \+ shadcn/ui)**:

  * **Candlestick \+ overlays** (HH/HL/LH/LL, CHOCH/BOS, OB/FVG; EMA/RSI/MACD toggles)

  * Decision panel (PB “Buy/Sell”), risk badges (News/Vol/Funding)

  * Backtest runner & equity curves; trade blotter; error console

# **4\) Data model (TimescaleDB core tables & key indexes)**

\-- Candles  
CREATE TABLE candles (  
  venue TEXT, symbol TEXT, tf TEXT,  
  open\_time TIMESTAMPTZ, close\_time TIMESTAMPTZ,  
  open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC,  
  volume NUMERIC, trades INT, taker\_buy\_vol NUMERIC, quote\_vol NUMERIC,  
  PRIMARY KEY (venue, symbol, tf, open\_time)  
);  
SELECT create\_hypertable('candles','open\_time');

\-- Indicators  
CREATE TABLE indicators (  
  venue TEXT, symbol TEXT, tf TEXT, ts TIMESTAMPTZ,  
  ema20 NUMERIC, ema50 NUMERIC, ema200 NUMERIC,  
  rsi14 NUMERIC, macd NUMERIC, macd\_signal NUMERIC, macd\_hist NUMERIC,  
  atr14 NUMERIC, bb\_upper NUMERIC, bb\_lower NUMERIC, vwap NUMERIC,  
  PRIMARY KEY (venue, symbol, tf, ts)  
);

\-- Swings/SMC  
CREATE TABLE swings (  
  venue TEXT, symbol TEXT, tf TEXT, ts TIMESTAMPTZ,  
  kind TEXT CHECK (kind IN ('HIGH','LOW')),  
  price NUMERIC, left\_n INT, right\_n INT,  
  PRIMARY KEY (venue, symbol, tf, ts, kind)  
);  
CREATE TABLE smc\_events (  
  venue TEXT, symbol TEXT, tf TEXT, ts TIMESTAMPTZ,  
  kind TEXT CHECK (kind IN ('CHOCH\_UP','CHOCH\_DN','BOS\_UP','BOS\_DN')),  
  ref\_ts TIMESTAMPTZ,  
  PRIMARY KEY (venue, symbol, tf, ts, kind)  
);  
CREATE TABLE zones (  
  venue TEXT, symbol TEXT, tf TEXT,  
  kind TEXT CHECK (kind IN ('OB','FVG')), side TEXT CHECK (side IN ('LONG','SHORT')),  
  price\_lo NUMERIC, price\_hi NUMERIC, created\_ts TIMESTAMPTZ, expiry\_bars INT,  
  PRIMARY KEY (venue, symbol, tf, kind, created\_ts)  
);

\-- Signals & Decisions  
CREATE TABLE signals\_raw (...);   \-- agent, score, features JSONB, ttl  
CREATE TABLE decisions (...);     \-- side, confidence, rule\_id, risk JSONB

\-- Orders & Positions  
CREATE TABLE orders (...);        \-- ext\_id, clientId, entry, stop, tps\_json, status  
CREATE TABLE positions (...);     \-- avg\_price, qty, unrealized PnL, risk bucket

**Indexes you’ll want**

* candles (symbol, tf, open\_time DESC)

* indicators (symbol, tf, ts DESC)

* smc\_events (symbol, tf, ts DESC)

* orders (symbol, created\_ts DESC)

# **5\) Contracts (events you pass around)**

**candles.v1**

{"venue":"binance\_spot","symbol":"BTCUSDT","tf":"15m",  
 "open\_time":"2025-09-16T09:00:00Z", "open":..., "high":..., "low":..., "close":..., "volume":...}

**features.v1** (ema, rsi, macd, atr, bb…)

**smc\_events.v1** (kind, ref\_ts)

**zones.v1** (kind OB/FVG, side, price\_lo, price\_hi, expiry\_bars)

**signals\_raw.v1**

{"agent":"retest","symbol":"BTCUSDT","tf":"15m","side\_hint":"LONG",  
 "entry\_hint":60250,"sl\_hint":59550,"tpR":\[1.5,2,3\],  
 "features":{"ema200\_up":true,"macd\_hist\_up":true,"rsi\_mid\_rebound":true},  
 "score":0.74,"ttl\_bars":6}

**decision.v1** (final side, size, entry/SL/TP ladder, risk JSON)

**order\_update.v1** (ACK, PARTIAL, FILLED, CANCELED, REJECTED, with exchange IDs)

# **6\) Security & compliance**

* **API keys**: separate Spot vs Futures; **no withdrawal scope**; **IP allow-listed**; rotated every 60–90 days

* **Secrets**: Vault/KMS; **never** in env files; least privileges per service

* **Idempotency**: every order request includes a unique newClientOrderId; DB unique constraint to prevent dupes

* **Auditing**: log every decision, payloads, and router response with timestamps; immutable storage for 2 years

* **Kill-switches**: drawdown breach, error spikes, WS outage, exchange incident → halt new entries; cancel open (ReduceOnly exits for perps)

# **7\) Performance budgets**

* WS candle close → features/SMC signals: **≤ 500 ms p95**

* Decision build → router POST: **≤ 200–300 ms p95**

* Backfill gaps after reconnect: **\< 5 s** to parity (using REST klines batch)

* UI new candle → overlay redraw: **\< 150 ms** (on reasonable dataset window)

# **8\) Observability**

* **Metrics**: per-service latency, queue lag, dropped messages, WS reconnect count, order ACK latency, fill ratio, slippage, error rate; DD & exposure gauges

* **Logs**: structured JSON; include trace\_id across pipeline

* **Traces**: WS ingest → Decision → Router round-trip to spot bottlenecks

* **Dashboards**: Live equity/PnL in **R**, PF/Calmar, trade heatmap, alert health, news/funding guards timeline

# **9\) Environments & deployment**

* **Dev**: Docker Compose (TimescaleDB, Redis, NATS/Kafka, MinIO, services)

* **Staging**: K8s small cluster; testnet keys; chaos tests (WS drop)

* **Prod**: K8s w/ auto-scaling (HPA), rolling deploy via GitHub Actions; network policies locked down

* **IaC**: Terraform modules (VPC, K8s, DB, secrets, monitoring)

# **10\) CI/CD & quality**

* **PR checks**: unit tests (SMC math & indicator parity), mypy/ruff (py), eslint/prettier (ts), go vet/linters (go)

* **Contract tests**: event schemas (JSONSchema) validated in CI

* **Backtest parity tests**: golden vectors for EMA/RSI/MACD/ATR \+ SMC events across sample data

* **Load tests**: WS fan-in of 16+ streams; decision throughput

# **11\) Failure modes & resilience**

* **WS disconnect**: exponential backoff \+ REST backfill; do not emit partial candles

* **Router failures**: retry with jitter; switch to **ReduceOnly** exits if repeated errors; alert & pause new entries

* **Data skew**: clock drift alarm; NTP enforced; reject \-1021 timestamp drift by enlarging recvWindow within safe bounds

# **12\) Build order (6-week plan)**

1. **Week 1–2**: Ingestors \+ TimescaleDB \+ Feature Engine \+ UI chart (candles/indicators)

2. **Week 3**: SMC Engine \+ overlays; Retest Analyzer; guards scaffolding

3. **Week 4**: Decision Engine \+ **Spot** Order Router (testnet); Alerts (Telegram/LINE) \+ PB panel

4. **Week 5**: Backtester & Paper broker; risk caps; reports

5. **Week 6**: **Futures** Router \+ Funding scheduler; staging soak; live-small go/no-go

---

# **13\) Modular Monolith Layout (non-microservice option)**

## **13.1 Runtime topology (3 processes, everything else in-process)**

* **Core Engine (Python, single process)**

  * Modules (in-process): ingest, features, smc, retest, regime\_vol, news\_funding\_guards, decision, paper, backtest, plugins

  * In-proc event bus (async queues) for pub/sub between modules

* **Order Router (Go or Node, separate small process)**

  * Signs & sends Spot / USD-M REST orders; reconciliation; idempotency

* **BFF/API \+ UI (TypeScript: NestJS \+ Next.js, separate process)**

  * Charts/overlays, PB buttons, alerts, reports

       ┌─────────────────────────────────────────────────────────────┐  
        │                  Core Engine (Python)                        │  
        │  ingest → features → smc → retest → decision  → alert        │  
        │             ↑       ↑      ↑           ↑                     │  
        │       regime/vol  news/funding      paper/backtest           │  
        │        (guards)     (guards)                                   │  
        │         └─────────── in-proc async event bus ───────────────┘  
        └──────────────────────────────────────────────────────────────┘  
                 │                                     │  
                 │ HTTP/JSON                           │ REST/WS  
                 ▼                                     ▼  
         Order Router (Go)                       BFF/API (NestJS) → UI (Next.js)  
                 │  
            Binance APIs

**Why this works now**

* **Lowest latency** (no network hops between bots): typical **≤ 700–900 ms p95** from candle close → order POST.

* **Fastest iteration**: one repo, one deploy for the engine; easy debugging and parity between backtest/paper/live.

* **Safety**: Router is isolated (separate process), so a bot bug can’t fire uncontrolled orders.

## **13.2 Repo layout (single monorepo)**

/app  
  /engine                       \# Python (FastAPI for health/metrics if you want)  
    bus.py                      \# in-proc pub/sub abstraction (asyncio queues)  
    types.py                    \# pydantic models (events, bars, signals, decisions)  
    config.yaml                 \# symbols/TFs, risk, guards, router URL, etc.  
    ingest/                     \# Binance WS/REST, gap backfill, k.x==true close  
    features/                   \# EMA/RSI/MACD/ATR/BB/VWAP etc.  
    smc/                        \# pivots, HH/HL/LH/LL, CHOCH/BOS, OB/FVG  
    retest/                     \# good-retest logic (window, tolerance, confirms)  
    regime\_vol/                 \# trend vs range classifier (ADX/BB/ATR pctl)  
    news\_funding\_guards/        \# calendars, funding windows → SAFE/BLOCK  
    decision/                   \# fusion, sizing, bracket builder (Spot & Futures-aware)  
    paper/                      \# paper fills, slippage model  
    backtest/                   \# vectorized \+ intrabar simulator (shared math with live)  
    plugins/                    \# optional: pairs, carry, AI-RSI, etc.  
    adapters/  
      db/                       \# TimescaleDB writes/reads  
      redis/                    \# hot state (optional)  
      router\_client/            \# HTTP client to Order Router (idempotent)  
    tests/                      \# unit \+ parity tests (golden vectors)  
  /router                       \# Go/Node router service (tiny)  
  /bff                          \# NestJS/FastAPI BFF (REST/WS)  
  /ui                           \# Next.js (Lightweight Charts \+ overlays \+ PB)  
  /infra                        \# docker-compose.yml, Timescale, Redis, Prometheus, Grafana

**Plugin SDK (bots as plug-ins)**

* Simple interface so you can add more analyses without touching core:

class Bot(Protocol):  
    name: str  
    inputs: set\[str\]                 \# e.g., {"candles.15m","ind.macd","smc.zones"}  
    def on\_bar(self, ctx, bar, feats, state) \-\> list\[Signal\]: ...

* Bots discovered via plugins/ folder (or entry-points). Errors in one bot are caught and quarantined.

## **13.3 Concurrency model**

* **asyncio** tasks per (symbol × TF) pipeline; bounded queues to apply back-pressure.

* CPU-heavy backtests run in **process pool**; everything else remains non-blocking.

* Router calls are **HTTP** to the separate Router process (short-lived, idempotent).

## **13.4 Deployment (single host)**

* **Docker Compose**: engine, router, bff, ui, **TimescaleDB**, **Redis**, **Prometheus/Grafana**.

* Secrets via **.env → Doppler/1Password CLI** in dev; consider **Vault/KMS** in prod even for monolith.

## **13.5 SLOs (monolith)**

* Candle close → signals: **≤ 500 ms p95**

* Decision → Router POST: **≤ 300 ms p95**

* REST backfill after WS drop: **\< 5 s**

* UI redraw: **\< 150 ms** for windowed views