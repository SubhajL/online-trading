package api

import (
	"context"
	"testing"
	"time"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"router/internal/binance"
)

type _FakeSpotClient struct {
	account           *binance.AccountResponse
	prices            map[string]decimal.Decimal
	tickerPricesCalls int
}

func (c *_FakeSpotClient) GetAccountInfo(_ context.Context) (*binance.AccountResponse, error) {
	return c.account, nil
}

func (c *_FakeSpotClient) GetTickerPrices(_ context.Context) (map[string]decimal.Decimal, error) {
	c.tickerPricesCalls++
	out := make(map[string]decimal.Decimal, len(c.prices))
	for symbol, price := range c.prices {
		out[symbol] = price
	}
	return out, nil
}

func TestBinanceEquityProvider_SpotNetLiqValue(t *testing.T) {
	updateMs := int64(1730000000000) // fixed timestamp
	fake := &_FakeSpotClient{
		account: &binance.AccountResponse{
			UpdateTime: updateMs,
			Balances: []binance.Balance{
				{Asset: "USDT", Free: decimal.RequireFromString("1000"), Locked: decimal.Zero},
				{Asset: "BTC", Free: decimal.RequireFromString("0.01"), Locked: decimal.Zero},
				{Asset: "ETH", Free: decimal.RequireFromString("0.1"), Locked: decimal.Zero},
			},
		},
		prices: map[string]decimal.Decimal{
			"BTCUSDT": decimal.RequireFromString("60000"),
			"ETHUSDT": decimal.RequireFromString("2000"),
		},
	}

	p := &BinanceEquityProvider{
		spotClient: fake,
		nowFn:      func() time.Time { return time.Unix(0, 0).UTC() },
	}

	snap, err := p.GetEquity(context.Background(), EquityVenueSpot)
	assert.NoError(t, err)

	// Net liq = 1000 + 0.01*60000 + 0.1*2000 = 1800
	assert.True(t, snap.EquityUSD.Equal(decimal.RequireFromString("1800")))
	assert.Equal(t, "binance_spot_net_liq", snap.Source)
	assert.Equal(t, time.UnixMilli(updateMs).UTC(), snap.Timestamp)
	assert.Equal(t, 1, fake.tickerPricesCalls)
}

func TestBinanceEquityProvider_SpotNetLiqUsesCachedPrices(t *testing.T) {
	updateMs := int64(1730000000000)
	fake := &_FakeSpotClient{
		account: &binance.AccountResponse{
			UpdateTime: updateMs,
			Balances: []binance.Balance{
				{Asset: "BTC", Free: decimal.RequireFromString("0.01"), Locked: decimal.Zero},
			},
		},
		prices: map[string]decimal.Decimal{
			"BTCUSDT": decimal.RequireFromString("60000"),
		},
	}

	now := time.Unix(0, 0).UTC()
	p := &BinanceEquityProvider{
		spotClient:    fake,
		nowFn:         func() time.Time { return now },
		priceCacheTTL: 30 * time.Second,
	}

	first, err := p.GetEquity(context.Background(), EquityVenueSpot)
	assert.NoError(t, err)
	second, err := p.GetEquity(context.Background(), EquityVenueSpot)
	assert.NoError(t, err)

	assert.True(t, first.EquityUSD.Equal(decimal.RequireFromString("600")))
	assert.True(t, second.EquityUSD.Equal(decimal.RequireFromString("600")))
	assert.Equal(t, 1, fake.tickerPricesCalls)
}

func TestBinanceEquityProvider_SpotNetLiqSkipsUnpriceableAssets(t *testing.T) {
	updateMs := int64(1730000000000)
	fake := &_FakeSpotClient{
		account: &binance.AccountResponse{
			UpdateTime: updateMs,
			Balances: []binance.Balance{
				{Asset: "USDT", Free: decimal.RequireFromString("100"), Locked: decimal.Zero},
				{Asset: "BTC", Free: decimal.RequireFromString("0.01"), Locked: decimal.Zero},
				{Asset: "DOGE", Free: decimal.RequireFromString("100"), Locked: decimal.Zero},
			},
		},
		prices: map[string]decimal.Decimal{
			"BTCUSDT": decimal.RequireFromString("60000"),
		},
	}

	p := &BinanceEquityProvider{
		spotClient: fake,
		nowFn:      func() time.Time { return time.Unix(0, 0).UTC() },
	}

	snap, err := p.GetEquity(context.Background(), EquityVenueSpot)
	assert.NoError(t, err)

	assert.True(t, snap.EquityUSD.Equal(decimal.RequireFromString("700")))
	assert.Equal(t, 1, fake.tickerPricesCalls)
}

func TestBinanceEquityProvider_DefaultVenuePrefersSpotWhenFuturesNil(t *testing.T) {
	fake := &_FakeSpotClient{
		account: &binance.AccountResponse{
			Balances: []binance.Balance{
				{Asset: "USDT", Free: decimal.RequireFromString("1"), Locked: decimal.Zero},
			},
		},
		prices: map[string]decimal.Decimal{},
	}

	p := &BinanceEquityProvider{
		spotClient:    fake,
		futuresClient: nil,
		nowFn:         func() time.Time { return time.Now().UTC() },
	}

	snap, err := p.GetEquity(context.Background(), "")
	assert.NoError(t, err)
	assert.Equal(t, EquityVenueSpot, snap.Venue)
}
