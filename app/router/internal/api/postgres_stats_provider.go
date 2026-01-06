package api

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"router/internal/storage"
)

type PostgresStatsProvider struct {
	pool *pgxpool.Pool
}

func NewPostgresStatsProvider(pool *pgxpool.Pool) *PostgresStatsProvider {
	return &PostgresStatsProvider{pool: pool}
}

func (p *PostgresStatsProvider) ComputeStats(ctx context.Context) (RouterStats, error) {
	if p == nil || p.pool == nil {
		return RouterStats{}, fmt.Errorf("pool is required")
	}

	var stats RouterStats
	err := storage.RunInTx(ctx, p.pool, func(tx pgx.Tx) error {
		var err error
		stats, err = p.computeStatsTx(ctx, tx)
		return err
	})
	if err != nil {
		return RouterStats{}, err
	}

	if stats.TotalTrades > 0 {
		stats.WinRate = float64(stats.WinCount) / float64(stats.TotalTrades)
	}
	return stats, nil
}

func (p *PostgresStatsProvider) computeStatsTx(ctx context.Context, tx pgx.Tx) (RouterStats, error) {
	row := tx.QueryRow(ctx, `
		WITH closed AS (
			SELECT
				COALESCE(realized_pnl, 0) AS realized,
				COALESCE(commission_paid, 0) AS fees,
				COALESCE(funding_paid, 0) AS funding,
				COALESCE(slippage_paid, 0) AS slippage,
				(COALESCE(realized_pnl, 0) - COALESCE(commission_paid, 0) - COALESCE(slippage_paid, 0) + COALESCE(funding_paid, 0)) AS net
			FROM positions
			WHERE is_active = FALSE
		),
		agg AS (
			SELECT
				COUNT(*)::int AS total_trades,
				COALESCE(SUM(CASE WHEN net > 0 THEN 1 ELSE 0 END), 0)::int AS win_count,
				COALESCE(SUM(CASE WHEN net <= 0 THEN 1 ELSE 0 END), 0)::int AS loss_count,
				COALESCE(SUM(realized), 0) AS total_realized,
				COALESCE(SUM(fees), 0) AS total_fees,
				COALESCE(SUM(funding), 0) AS total_funding,
				COALESCE(SUM(slippage), 0) AS total_slippage,
				COALESCE(SUM(net), 0) AS net_pnl,
				COALESCE(SUM(CASE WHEN net > 0 THEN net ELSE 0 END), 0) AS gross_profit,
				ABS(COALESCE(SUM(CASE WHEN net < 0 THEN net ELSE 0 END), 0)) AS gross_loss
			FROM closed
		)
		SELECT
			total_trades,
			win_count,
			loss_count,
			total_realized::text,
			total_fees::text,
			total_funding::text,
			total_slippage::text,
			net_pnl::text,
			CASE WHEN gross_loss = 0 THEN 0::float8 ELSE (gross_profit / gross_loss)::float8 END AS profit_factor
		FROM agg
	`)

	var stats RouterStats
	if err := row.Scan(
		&stats.TotalTrades,
		&stats.WinCount,
		&stats.LossCount,
		&stats.TotalPnL,
		&stats.TotalFees,
		&stats.TotalFunding,
		&stats.TotalSlippage,
		&stats.NetPnL,
		&stats.ProfitFactor,
	); err != nil {
		return RouterStats{}, fmt.Errorf("scan stats: %w", err)
	}

	return stats, nil
}
