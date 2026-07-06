package binance

import (
	"context"
	"fmt"

	"router/internal/rest"
)

// PlaceSpotOCO places a spot OCO exit pair (take-profit + stop) whose legs
// the exchange sibling-cancels natively.
func (c *Client) PlaceSpotOCO(ctx context.Context, req rest.OCORequest) (*rest.OCOResponse, error) {
	if c.restClient == nil {
		return nil, fmt.Errorf("rest client not available")
	}
	if c.isFutures {
		return nil, fmt.Errorf("OCO order lists are spot-only")
	}
	resp, err := c.restClient.PlaceSpotOCO(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("failed to place spot OCO: %w", err)
	}
	return resp, nil
}

// GetOCOByListClientOrderID resolves an OCO's state by list client order id.
func (c *Client) GetOCOByListClientOrderID(ctx context.Context, listClientOrderID string) (*rest.OCOResponse, error) {
	if c.restClient == nil {
		return nil, fmt.Errorf("rest client not available")
	}
	resp, err := c.restClient.GetOCOByListClientOrderID(ctx, listClientOrderID)
	if err != nil {
		return nil, fmt.Errorf("failed to query spot OCO: %w", err)
	}
	return resp, nil
}
