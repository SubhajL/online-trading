package funding

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"

	"router/internal/rest"
	"router/internal/storage"
)

type Poller struct {
	client   *rest.Client
	pool     *pgxpool.Pool
	logger   zerolog.Logger
	interval time.Duration

	lastFetch time.Time
}

func NewFundingPoller(
	client *rest.Client,
	pool *pgxpool.Pool,
	interval time.Duration,
	logger zerolog.Logger,
) (*Poller, error) {
	if client == nil {
		return nil, fmt.Errorf("client is required")
	}
	if pool == nil {
		return nil, fmt.Errorf("pool is required")
	}
	if interval <= 0 {
		return nil, fmt.Errorf("interval must be positive")
	}

	return &Poller{
		client:    client,
		pool:      pool,
		logger:    logger,
		interval:  interval,
		lastFetch: time.Now().Add(-interval),
	}, nil
}

func (p *Poller) Start(ctx context.Context) {
	ticker := time.NewTicker(p.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := p.pollOnce(ctx); err != nil {
				p.logger.Error().Err(err).Msg("funding poll failed")
			}
		}
	}
}

func (p *Poller) pollOnce(ctx context.Context) error {
	from := p.lastFetch
	to := time.Now()

	records, err := p.client.GetFuturesIncome(ctx, rest.FuturesIncomeQuery{
		IncomeType: "FUNDING_FEE",
		StartTime:  from.UnixMilli(),
		EndTime:    to.UnixMilli(),
		Limit:      1000,
	})
	if err != nil {
		return err
	}

	if len(records) == 0 {
		p.lastFetch = to
		return nil
	}

	err = storage.RunInTx(ctx, p.pool, func(tx pgx.Tx) error {
		return applyFundingIncomeTx(ctx, tx, records)
	})
	if err != nil {
		return err
	}

	p.lastFetch = to
	return nil
}

func applyFundingIncomeTx(ctx context.Context, tx pgx.Tx, records []rest.FuturesIncomeRecord) error {
	for _, record := range records {
		if record.IncomeType != "FUNDING_FEE" {
			continue
		}
		if record.Symbol == "" || record.Income == "" {
			continue
		}
		amount, err := decimal.NewFromString(record.Income)
		if err != nil {
			return fmt.Errorf("parse funding income: %w", err)
		}

		_, err = tx.Exec(
			ctx,
			`UPDATE positions
			    SET funding_paid = COALESCE(funding_paid, 0) + $1
			  WHERE venue = 'futures' AND symbol = $2 AND is_active = TRUE`,
			amount,
			record.Symbol,
		)
		if err != nil {
			return fmt.Errorf("apply funding: %w", err)
		}
	}
	return nil
}
