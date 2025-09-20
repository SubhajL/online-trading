package binance

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/auth"
	"router/internal/rest"
)

// Test configuration for Binance testnet
const (
	testnetSpotURL    = "https://testnet.binance.vision"
	testnetFuturesURL = "https://testnet.binancefuture.com"
)

// getTestCredentials gets testnet credentials from environment
func getTestCredentials(t *testing.T) (apiKey, secretKey string) {
	apiKey = os.Getenv("BINANCE_TESTNET_API_KEY")
	secretKey = os.Getenv("BINANCE_TESTNET_SECRET_KEY")


	if apiKey == "" || secretKey == "" {
		t.Skip("BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_SECRET_KEY must be set")
	}

	return apiKey, secretKey
}

// createTestnetClient creates a real testnet client
func createTestnetClient(t *testing.T) *Client {
	t.Helper()

	apiKey, secretKey := getTestCredentials(t)
	signer := auth.NewSigner(apiKey, secretKey)
	restClient := rest.NewClient(
		testnetSpotURL,
		signer,
		rest.WithTimeout(30*time.Second),
		rest.WithMaxRetries(3),
	)
	logger := zerolog.New(zerolog.NewTestWriter(t)).Level(zerolog.DebugLevel)

	client, err := NewClient(testnetSpotURL, signer, restClient, logger)
	require.NoError(t, err)

	// Set up exchange info cache
	client.exchangeInfoCache = NewExchangeInfoCache(
		restClient,
		nil,
		5*time.Minute,
		logger.With().Str("component", "exchange_info").Logger(),
	)

	return client
}

// createTestnetFuturesClient creates a real futures testnet client
func createTestnetFuturesClient(t *testing.T) *Client {
	t.Skip("Futures testnet not implemented yet")
	return nil
}

// TestTestnetConnection verifies we can connect to testnet
func TestTestnetConnection(t *testing.T) {
	client := createTestnetClient(t)
	ctx := context.Background()

	// Try to get exchange info
	info, err := client.restClient.GetExchangeInfo(ctx)
	require.NoError(t, err)
	assert.NotNil(t, info)
	assert.Greater(t, len(info.Symbols), 0)

	t.Logf("Connected to testnet, found %d symbols", len(info.Symbols))
}

// TestTestnetAccountInfo tests getting account info from testnet
func TestTestnetAccountInfo(t *testing.T) {
	client := createTestnetClient(t)
	ctx := context.Background()

	account, err := client.GetAccountInfo(ctx)
	require.NoError(t, err)
	assert.NotNil(t, account)
	assert.True(t, account.CanTrade)

	// Log balances
	for _, balance := range account.Balances {
		if !balance.Free.IsZero() || !balance.Locked.IsZero() {
			t.Logf("Balance: %s - Free: %s, Locked: %s",
				balance.Asset, balance.Free.String(), balance.Locked.String())
		}
	}
}


// findTestSymbol finds a suitable symbol for testing
func findTestSymbol(t *testing.T, client *Client) string {
	ctx := context.Background()

	// Get exchange info
	info, err := client.restClient.GetExchangeInfo(ctx)
	require.NoError(t, err)

	// Look for common test symbols
	testSymbols := []string{"BTCUSDT", "ETHUSDT", "BNBUSDT"}

	for _, symbol := range testSymbols {
		for _, s := range info.Symbols {
			if s.Symbol == symbol && s.Status == "TRADING" {
				t.Logf("Using test symbol: %s", symbol)
				return symbol
			}
		}
	}

	// If none found, use first trading symbol
	for _, s := range info.Symbols {
		if s.Status == "TRADING" && s.IsSpotTradingAllowed {
			t.Logf("Using first available symbol: %s", s.Symbol)
			return s.Symbol
		}
	}

	t.Fatal("No trading symbols available on testnet")
	return ""
}