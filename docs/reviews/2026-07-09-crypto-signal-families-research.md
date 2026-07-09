# Which Signal Families Actually Work on BTC/ETH? — Evidence Review

**Date:** 2026-07-09 · **Method:** deep-research harness, 25 claims adversarially verified (3-vote): 20 confirmed, 1 refuted, 4 unverified (infra errors).
**Companion to:** `2026-07-07-smc-efficacy-research.md` (SMC null result) and `docs/plans/2026-07-09-signal-family-v3-trend-experiment.md`.

## Bottom line

The best-evidenced family for a retail BTC/ETH spot trader is **long-only (long/cash), daily-bar trend-following** — price-vs-SMA rules or time-series momentum with **~10–65-day lookbacks** (150/200-day for cost robustness). Top-journal support (Liu & Tsyvinski, _RFS_ 2021), documented breakeven costs (57–66 bps) comfortably above ~10 bps retail fees, and repeated net-of-cost survival. Its realistic payoff is **drawdown reduction at roughly buy-and-hold returns — not return outperformance** — with net Sharpe plausibly **0.5–1.0** (the documented 1.5 is an in-sample-selected optimistic ceiling) and material decay risk.

## Confirmed findings (all 3-0 unless noted)

1. **TSMOM is the best-documented crypto-specific predictor** — Liu & Tsyvinski (_RFS_ 2021): past returns predict 1–8 weeks ahead for BTC/XRP/ETH (weaker for ETH; sample ends ~2018; gross of costs).
2. **The beta trap is real and quantified** — Han, Kang & Ryu (2013–2023 sample incl. the 2022 bear): the short side of crypto TSM loses in **19 of 20** lookback/holding combos _pre-cost_; momentum is insignificant in bear regimes; a market-neutral long-short crypto momentum strategy is judged "unattainable." Reported crypto momentum performance is largely _timed long-BTC beta_.
3. **Decay since 2020–21 is corroborated by 3 independent studies** — cross-sectional momentum significant only pre-July-2020 (Grobys et al., _FMPM_ 2025); large-cap momentum flat after early 2021 (Han et al.); BTC technical rules already negative out-of-sample in H1 2018 (Hudson & Urquhart, _Annals of OR_). **No verified sample extends past Aug 2023.**
4. **Daily long/cash SMA rules worked net of costs** — hold when price > 20/65/150/200-day SMA else cash: gross Sharpe up to 1.89 (BTC-65d) / 2.64 (ETH-20d); all four still beat B&H on Sharpe even at 0.5%/trade. Short lookbacks earn more but bleed most to costs (BTC-20d: −0.43 Sharpe at 0.5% vs −0.06/−0.07 for 150/200d) → **low turnover + maker fees favored** (Le & Ruthbah, Monash WP).
5. **Headline crypto trend numbers are often zero-friction artifacts** — the widely-cited 73,700% SMA-crossover backtest assumed _no_ fees/spread/slippage; its useful residue: ~10/40-day SMA windows consistent (gross Sharpe 0.5–1.5, one losing year), performance already fading pre-2020, and no profitable intraday windows.
6. **Large-scale in-sample rule evidence doesn't survive OOS on BTC** — 14,919 rules (Hudson & Urquhart): all families significant in-sample with breakeven costs 57–66 bps (filter/channel-breakout best); outperformance vs B&H shows up mainly on **Calmar/Sortino (drawdown avoidance)**, not raw return; H1-2018 OOS turned negative.
7. **Vol-managed sizing helps in-sample but doesn't fix tails** — Barroso–Santa-Clara-style scaling raises average payoffs >200% with significant alphas (Grobys et al. 2025), but the power-law tail exponent (~3, undefined variance) is unchanged — Sharpe alone is misleading. Gross-of-cost, cross-sectional, equal-weighted; transfer to single-asset spot TSM is plausible but unproven.
8. **Net-of-cost Sharpe ceiling ≈ 1.5, explicitly optimistic** — best combo (28d/5d, long-only TSM, 15 bps/trade incl. measured slippage) selected in-sample; authors call it a best-case.
9. **Cross-sectional altcoin momentum is a poor retail candidate** — 5 of 21 portfolios liquidated in-sample; only 6 beat market; profits from the long leg; post-2020 decay.
10. **The most honest OOS test is the template for expectations** — walk-forward-optimized EMA cross on BTC, run once on unseen Nov 2019–Aug 2021 with 0.1% fees (Mroziewicz & Ślepaczuk 2026): ~matched B&H (Sharpe 1.11 vs 1.13) with **maxDD 52% vs 62%** and higher Information Ratio. _Drawdown reduction, not return outperformance._ (Companion claim that it "survives fees with 0.4% breakeven" was REFUTED 0-3.)
11. **Timeframe: daily-to-multi-day bars only** (2-0 + corroboration) — Borgards (_NAJEF_ 2021): TSM profitable net of 0.2% fees at 1-day and 1-hour frequencies, but at 5-min fees consume all gross profit. No verified support for 15m-class trend rules.

## Refuted / unverified

- ❌ REFUTED (0-3): "Warsaw EMA strategy survives retail taker fees with ~0.4% breakeven."
- ❓ Unverified (verifier infra errors, not disproven): no-profitable-intraday finding's details; walk-forward fragility pre-2021; Han et al.'s headline net Sharpe 1.51 decomposition.
- **Zero surviving claims** for: regime filters (ADX/HMM/GMM), perp funding carry, on-chain (MVRV/SOPR/flows), sentiment, seasonality, short-horizon mean reversion — open questions, not disproofs.

## What this changes for the v3 experiment

1. **Primary arm = daily bars, long/cash** (`allow_short: false`). The GO bar must NOT require a winning long/short arm — the short side is documented to lose; long/short runs become a _diagnostic_ expected to underperform.
2. **Success = risk-adjusted**: Sharpe ≥ B&H with maxDD materially lower (template: 62%→52%) at roughly comparable return. Requiring return outperformance would fail strategies the literature calls successful.
3. **Add the price-vs-SMA family** (the most-evidenced rule shape) alongside TSMOM/EMA-cross/Donchian; ex-ante lookbacks 20d/65d/200d + 10/40d cross + 28d TSM.
4. **Get longer daily history** — resampling our 2-yr 1h data yields only ~530 tradable daily bars after a 200d warmup and contains no full bear; fetch ~7 years of 1d klines via the existing Binance downloader so the drawdown-protection claim is actually testable (2022 bear).
5. **1h becomes the secondary arm** (partial support: Borgards net-positive at 1h through 2019); **15m dropped** (no supporting evidence at retail fees).
6. Expectation setting: net Sharpe 0.5–1.0, at least one losing year, decay risk — post-2023 samples don't exist, so our 2024–26 result is itself novel evidence.

## Key sources

- Liu & Tsyvinski, _Risks and Returns of Cryptocurrency_, RFS 2021 — ssrn.com/abstract=3226952
- Han, Kang & Ryu, _TS & CS Momentum in Crypto_ (incl. internet appendix) — SSRN 4675565
- Grobys et al., _FMPM_ 2025 — doi 10.1007/s11408-025-00474-9
- Hudson & Urquhart, _Technical Trading and Cryptocurrencies_, Annals of OR — doi 10.1007/s10479-019-03357-1
- Le & Ruthbah (Monash), _Trend-following Strategies for Crypto Investors_ — monash.edu WP
- Mroziewicz & Ślepaczuk (Warsaw 2026), OOS EMA-cross on BTC — arXiv 2602.10785
- Borgards, _NAJEF_ 2021 — doi 10.1016/j.najef.2021.101385
- arXiv 2009.12155 (zero-friction SMA-cross caveats)
