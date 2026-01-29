from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.engine.models import RiskParameters


@dataclass(frozen=True)
class RiskSnapshot:
    equity: Decimal
    equity_ts: datetime
    start_of_day_equity: Decimal
    peak_equity: Decimal
    open_positions_count: int
    total_exposure_usd: Decimal
    symbol_exposure_usd: dict[str, Decimal]


@dataclass(frozen=True)
class RiskSnapshotError:
    error_type: str
    message: str


async def build_risk_snapshot(
    *,
    db_adapter: object,
    venue: str,
    now: datetime,
    risk: RiskParameters,
) -> tuple[RiskSnapshot | None, list[RiskSnapshotError]]:
    get_latest_equity_sample = getattr(db_adapter, "get_latest_equity_sample", None)
    get_equity_sample_at_or_after = getattr(
        db_adapter,
        "get_equity_sample_at_or_after",
        None,
    )
    get_peak_equity_since = getattr(db_adapter, "get_peak_equity_since", None)
    get_active_positions = getattr(db_adapter, "get_active_positions", None)

    missing = []
    if not callable(get_latest_equity_sample):
        missing.append("get_latest_equity_sample")
    if not callable(get_equity_sample_at_or_after):
        missing.append("get_equity_sample_at_or_after")
    if not callable(get_peak_equity_since):
        missing.append("get_peak_equity_since")
    if not callable(get_active_positions):
        missing.append("get_active_positions")
    if missing:
        return None, [
            RiskSnapshotError(
                error_type="missing_db_adapter_methods",
                message=f"DB adapter missing methods: {', '.join(missing)}",
            ),
        ]

    latest = await get_latest_equity_sample()
    if latest is None:
        return None, [
            RiskSnapshotError(
                error_type="missing_equity_sample",
                message="No equity_samples row available",
            ),
        ]

    equity, equity_ts = latest
    if equity_ts.tzinfo is None:
        equity_ts = equity_ts.replace(tzinfo=UTC)

    max_age = timedelta(seconds=risk.risk_data_max_age_seconds)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    if now - equity_ts > max_age:
        return None, [
            RiskSnapshotError(
                error_type="stale_equity_sample",
                message=(
                    f"Latest equity sample too old: age={(now - equity_ts).total_seconds():.0f}s "
                    f"> max_age={risk.risk_data_max_age_seconds}s"
                ),
            ),
        ]

    day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    start_of_day_equity = await get_equity_sample_at_or_after(day_start)
    if start_of_day_equity is None:
        return None, [
            RiskSnapshotError(
                error_type="missing_start_of_day_equity",
                message="No equity_samples row found at or after UTC midnight",
            ),
        ]

    lookback_start = now - timedelta(days=risk.drawdown_lookback_days)
    peak_equity = await get_peak_equity_since(lookback_start)
    if peak_equity is None:
        peak_equity = equity

    rows = await get_active_positions(venue)
    symbol_exposure: dict[str, Decimal] = {}
    total_exposure = Decimal(0)
    open_positions_count = 0

    for row in rows:
        symbol = str(row.get("symbol", ""))
        if not symbol:
            continue
        size = row.get("size")
        current_price = row.get("current_price")
        if size is None or current_price is None:
            continue
        try:
            notional = abs(Decimal(str(size)) * Decimal(str(current_price)))
        except Exception:
            continue
        if notional <= 0:
            continue
        open_positions_count += 1
        total_exposure += notional
        symbol_exposure[symbol] = symbol_exposure.get(symbol, Decimal(0)) + notional

    return (
        RiskSnapshot(
            equity=equity,
            equity_ts=equity_ts,
            start_of_day_equity=start_of_day_equity,
            peak_equity=peak_equity,
            open_positions_count=open_positions_count,
            total_exposure_usd=total_exposure,
            symbol_exposure_usd=symbol_exposure,
        ),
        [],
    )
