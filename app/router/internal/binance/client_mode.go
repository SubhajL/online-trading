package binance

import (
	"github.com/rs/zerolog"
	"router/internal/auth"
	"router/internal/rest"
)

func NewSpotClient(baseURL string, signer *auth.Signer, restClient *rest.Client, logger zerolog.Logger) (*Client, error) {
	client, err := NewClient(baseURL, signer, restClient, logger)
	if err != nil {
		return nil, err
	}
	client.isFutures = false
	return client, nil
}

func NewFuturesClient(baseURL string, signer *auth.Signer, restClient *rest.Client, logger zerolog.Logger) (*Client, error) {
	client, err := NewClient(baseURL, signer, restClient, logger)
	if err != nil {
		return nil, err
	}
	client.isFutures = true
	return client, nil
}
