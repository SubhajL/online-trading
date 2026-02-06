package api

import (
	"context"
	"fmt"
	"time"

	"github.com/shopspring/decimal"
	"router/internal/binance"
)

type BinanceEquityProvider struct {
	spotClient    *binance.Client
	futuresClient *binance.Client
	nowFn         func() time.Time
}

func NewBinanceEquityProvider(spotClient, futuresClient *binance.Client) *BinanceEquityProvider {
	return &BinanceEquityProvider{
		spotClient:    spotClient,
		futuresClient: futuresClient,
		nowFn:         func() time.Time { return time.Now().UTC() },
	}
}

func (p *BinanceEquityProvider) GetEquity(ctx context.Context, venue EquityVenue) (EquitySnapshot, error) {
	if venue == "" {
		if p.futuresClient != nil {
			venue = EquityVenueUSDM
		} else {
			venue = EquityVenueSpot
		}
	}

	switch venue {
	case EquityVenueSpot:
		if p.spotClient == nil {
			return EquitySnapshot{}, fmt.Errorf("spot client not configured")
		}

		account, err := p.spotClient.GetAccountInfo(ctx)
		if err != nil {
			return EquitySnapshot{}, err
		}

		equity := decimal.Zero
		for _, bal := range account.Balances {
			if bal.Asset != "USDT" {
				continue
			}
			equity = equity.Add(bal.Free).Add(bal.Locked)
			break
		}

		ts := p.nowFn()
		if account.UpdateTime > 0 {
			ts = time.UnixMilli(account.UpdateTime).UTC()
		}

		return EquitySnapshot{
			Venue:     EquityVenueSpot,
			EquityUSD: equity,
			Timestamp: ts,
			Source:    "binance_spot_account_usdt",
		}, nil

	case EquityVenueUSDM:
		if p.futuresClient == nil {
			return EquitySnapshot{}, fmt.Errorf("futures client not configured")
		}

		account, err := p.futuresClient.GetFuturesAccount(ctx)
		if err != nil {
			return EquitySnapshot{}, err
		}

		ts := p.nowFn()
		if account.UpdateTime > 0 {
			ts = time.UnixMilli(account.UpdateTime).UTC()
		}

		return EquitySnapshot{
			Venue:     EquityVenueUSDM,
			EquityUSD: account.TotalMarginBalance,
			Timestamp: ts,
			Source:    "binance_futures_total_margin_balance",
		}, nil

	default:
		return EquitySnapshot{}, fmt.Errorf("unsupported venue: %s", string(venue))
	}
}
