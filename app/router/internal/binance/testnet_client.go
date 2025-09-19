package binance

import (
	"github.com/rs/zerolog"
	"router/internal/auth"
	"router/internal/config"
	"router/internal/rest"
)

// TestnetURLs contains testnet endpoints
type TestnetURLs struct {
	SpotBaseURL    string
	FuturesBaseURL string
}

// GetTestnetURLs returns the testnet URLs
func GetTestnetURLs() TestnetURLs {
	return TestnetURLs{
		SpotBaseURL:    "https://testnet.binance.vision",
		FuturesBaseURL: "https://testnet.binancefuture.com",
	}
}

// NewTestnetSpotClient creates a new testnet spot client
func NewTestnetSpotClient(config *config.BinanceConfig, logger zerolog.Logger) (*Client, error) {
	urls := GetTestnetURLs()
	signer := auth.NewSignerWithRecvWindow(config.SpotAPIKey, config.SpotSecretKey, config.RecvWindow)
	restClient := rest.NewClient(
		urls.SpotBaseURL,
		signer,
		rest.WithTimeout(config.Timeout),
		rest.WithMaxRetries(config.MaxRetries),
	)

	client, err := NewClient(urls.SpotBaseURL, signer, restClient, logger)
	if err != nil {
		return nil, err
	}

	client.isFutures = false

	// Create exchange info cache
	client.exchangeInfoCache = NewExchangeInfoCache(restClient, nil, config.ExchangeInfoCacheTTL, logger.With().Str("component", "exchange_info").Logger())

	return client, nil
}

// NewTestnetFuturesClient creates a new testnet futures client
func NewTestnetFuturesClient(config *config.BinanceConfig, logger zerolog.Logger) (*Client, error) {
	urls := GetTestnetURLs()
	signer := auth.NewSignerWithRecvWindow(config.FuturesAPIKey, config.FuturesSecretKey, config.RecvWindow)
	restClient := rest.NewClient(
		urls.FuturesBaseURL,
		signer,
		rest.WithTimeout(config.Timeout),
		rest.WithMaxRetries(config.MaxRetries),
	)

	client, err := NewClient(urls.FuturesBaseURL, signer, restClient, logger)
	if err != nil {
		return nil, err
	}

	client.isFutures = true

	// Create exchange info cache (futures client doesn't have spot client)
	client.exchangeInfoCache = NewExchangeInfoCache(nil, restClient, config.ExchangeInfoCacheTTL, logger.With().Str("component", "exchange_info").Logger())

	return client, nil
}