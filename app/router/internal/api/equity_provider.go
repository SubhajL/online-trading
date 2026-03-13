package api

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/shopspring/decimal"
	"router/internal/binance"
	"router/internal/rest"
)

type _SpotEquityClient interface {
	GetAccountInfo(ctx context.Context) (*binance.AccountResponse, error)
	GetTickerPrices(ctx context.Context) (map[string]decimal.Decimal, error)
}

type _FuturesEquityClient interface {
	GetFuturesAccount(ctx context.Context) (*rest.FuturesAccountResponse, error)
}

type BinanceEquityProvider struct {
	spotClient    _SpotEquityClient
	futuresClient _FuturesEquityClient
	nowFn         func() time.Time

	priceCacheMu  sync.Mutex
	priceCache    map[string]cachedPrice
	priceCacheTTL time.Duration
}

type cachedPrice struct {
	price     decimal.Decimal
	fetchedAt time.Time
}

func NewBinanceEquityProvider(spotClient, futuresClient *binance.Client) *BinanceEquityProvider {
	var spot _SpotEquityClient
	if spotClient != nil {
		spot = spotClient
	}
	var futures _FuturesEquityClient
	if futuresClient != nil {
		futures = futuresClient
	}

	return &BinanceEquityProvider{
		spotClient:    spot,
		futuresClient: futures,
		nowFn:         func() time.Time { return time.Now().UTC() },
		priceCache:    make(map[string]cachedPrice),
		priceCacheTTL: 30 * time.Second,
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

		// Keep this endpoint responsive even when Binance REST is slow.
		// Using a short budget ensures engine equity sampling doesn't stall risk checks.
		budgetCtx, cancelBudget := context.WithTimeout(ctx, 2*time.Second)
		defer cancelBudget()

		account, err := p.spotClient.GetAccountInfo(budgetCtx)
		if err != nil {
			return EquitySnapshot{}, err
		}

		equity := decimal.Zero
		requiredSymbols := make(map[string]struct{})
		for _, bal := range account.Balances {
			total := bal.Free.Add(bal.Locked)
			if total.LessThanOrEqual(decimal.Zero) {
				continue
			}

			if bal.Asset == "USDT" {
				equity = equity.Add(total)
				continue
			}

			requiredSymbols[bal.Asset+"USDT"] = struct{}{}
		}

		snapshotFetched := false
		for _, bal := range account.Balances {
			total := bal.Free.Add(bal.Locked)
			if total.LessThanOrEqual(decimal.Zero) || bal.Asset == "USDT" {
				continue
			}

			symbol := bal.Asset + "USDT"
			lastPrice, ok := p.getCachedLastPrice(symbol)
			if !ok && !snapshotFetched {
				priceCtx, cancel := context.WithTimeout(budgetCtx, 500*time.Millisecond)
				prices, err := p.spotClient.GetTickerPrices(priceCtx)
				cancel()
				snapshotFetched = true
				if err == nil {
					for snapshotSymbol, price := range prices {
						if _, needed := requiredSymbols[snapshotSymbol]; needed && price.GreaterThan(decimal.Zero) {
							p.setCachedLastPrice(snapshotSymbol, price)
						}
					}
				}
				lastPrice, ok = p.getCachedLastPrice(symbol)
			}

			if ok && lastPrice.GreaterThan(decimal.Zero) {
				equity = equity.Add(total.Mul(lastPrice))
			}
		}

		ts := p.nowFn()
		if account.UpdateTime > 0 {
			ts = time.UnixMilli(account.UpdateTime).UTC()
		}

		return EquitySnapshot{
			Venue:     EquityVenueSpot,
			EquityUSD: equity,
			Timestamp: ts,
			Source:    "binance_spot_net_liq",
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

func (p *BinanceEquityProvider) getCachedLastPrice(symbol string) (decimal.Decimal, bool) {
	if symbol == "" {
		return decimal.Zero, false
	}
	now := p.nowFn()

	p.priceCacheMu.Lock()
	defer p.priceCacheMu.Unlock()
	if p.priceCache == nil {
		return decimal.Zero, false
	}
	c, ok := p.priceCache[symbol]
	if !ok {
		return decimal.Zero, false
	}
	if now.Sub(c.fetchedAt) > p.priceCacheTTL {
		return decimal.Zero, false
	}
	return c.price, true
}

func (p *BinanceEquityProvider) setCachedLastPrice(symbol string, price decimal.Decimal) {
	if symbol == "" {
		return
	}
	now := p.nowFn()
	p.priceCacheMu.Lock()
	defer p.priceCacheMu.Unlock()
	if p.priceCache == nil {
		p.priceCache = make(map[string]cachedPrice)
	}
	p.priceCache[symbol] = cachedPrice{price: price, fetchedAt: now}
}
