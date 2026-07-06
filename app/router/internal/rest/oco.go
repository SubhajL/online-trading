package rest

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"

	"github.com/shopspring/decimal"
)

// OCORequest describes a spot One-Cancels-the-Other exit pair: a LIMIT_MAKER
// take-profit and a STOP_LOSS_LIMIT stop, sharing one quantity.
type OCORequest struct {
	Symbol   string
	Side     string // exit side (SELL for a BUY entry)
	Quantity decimal.Decimal
	Price    decimal.Decimal // take-profit price (trigger, for BUY exits)
	// PriceLimit is the take-profit's limit price when the leg is a trigger
	// type (BUY exits use TAKE_PROFIT_LIMIT): set marketably past the
	// trigger so activation converts to a fill, since the OCO sibling is
	// cancelled on activation rather than on fill. Ignored for LIMIT_MAKER
	// take-profits; falls back to Price when zero.
	PriceLimit         decimal.Decimal
	StopPrice          decimal.Decimal // stop trigger
	StopLimitPrice     decimal.Decimal // stop limit price
	ListClientOrderID  string
	LimitClientOrderID string
	StopClientOrderID  string
}

type OCOOrderRef struct {
	Symbol        string `json:"symbol"`
	OrderID       int64  `json:"orderId"`
	ClientOrderID string `json:"clientOrderId"`
}

type OCOOrderReport struct {
	Symbol        string          `json:"symbol"`
	OrderID       int64           `json:"orderId"`
	ClientOrderID string          `json:"clientOrderId"`
	Type          string          `json:"type"`
	Status        string          `json:"status"`
	Price         decimal.Decimal `json:"price"`
	StopPrice     decimal.Decimal `json:"stopPrice"`
	OrigQty       decimal.Decimal `json:"origQty"`
}

type OCOResponse struct {
	OrderListID       int64            `json:"orderListId"`
	ListClientOrderID string           `json:"listClientOrderId"`
	ListOrderStatus   string           `json:"listOrderStatus"`
	Orders            []OCOOrderRef    `json:"orders"`
	OrderReports      []OCOOrderReport `json:"orderReports"`
}

// PlaceSpotOCO places a spot OCO exit pair. Only meaningful on the spot
// venue; the exchange cancels the sibling when either leg executes.
//
// /api/v3/orderList/oco describes the pair as an "above" and a "below"
// order relative to the last traded price. A SELL exit protecting a long
// puts the LIMIT_MAKER take-profit above and the STOP_LOSS_LIMIT below. A
// BUY exit mirrors that, except LIMIT_MAKER is not a supported belowType,
// so the take-profit becomes a TAKE_PROFIT_LIMIT triggering at its own
// limit price.
func (c *Client) PlaceSpotOCO(ctx context.Context, req OCORequest) (*OCOResponse, error) {
	if c.signer == nil {
		return nil, fmt.Errorf("signer required for PlaceSpotOCO")
	}
	if req.Symbol == "" || req.Side == "" {
		return nil, fmt.Errorf("symbol and side are required")
	}
	if !req.Quantity.IsPositive() {
		return nil, fmt.Errorf("quantity must be positive")
	}
	if !req.Price.IsPositive() || !req.StopPrice.IsPositive() || !req.StopLimitPrice.IsPositive() {
		return nil, fmt.Errorf("price, stopPrice and stopLimitPrice are required")
	}

	params := url.Values{}
	params.Set("symbol", req.Symbol)
	params.Set("side", req.Side)
	params.Set("quantity", req.Quantity.String())
	if req.ListClientOrderID != "" {
		params.Set("listClientOrderId", req.ListClientOrderID)
	}
	switch req.Side {
	case "SELL":
		params.Set("aboveType", "LIMIT_MAKER")
		params.Set("abovePrice", req.Price.String())
		params.Set("belowType", "STOP_LOSS_LIMIT")
		params.Set("belowPrice", req.StopLimitPrice.String())
		params.Set("belowStopPrice", req.StopPrice.String())
		params.Set("belowTimeInForce", "GTC")
		if req.LimitClientOrderID != "" {
			params.Set("aboveClientOrderId", req.LimitClientOrderID)
		}
		if req.StopClientOrderID != "" {
			params.Set("belowClientOrderId", req.StopClientOrderID)
		}
	case "BUY":
		takeProfitLimit := req.PriceLimit
		if !takeProfitLimit.IsPositive() {
			takeProfitLimit = req.Price
		}
		params.Set("aboveType", "STOP_LOSS_LIMIT")
		params.Set("abovePrice", req.StopLimitPrice.String())
		params.Set("aboveStopPrice", req.StopPrice.String())
		params.Set("aboveTimeInForce", "GTC")
		params.Set("belowType", "TAKE_PROFIT_LIMIT")
		params.Set("belowPrice", takeProfitLimit.String())
		params.Set("belowStopPrice", req.Price.String())
		params.Set("belowTimeInForce", "GTC")
		if req.StopClientOrderID != "" {
			params.Set("aboveClientOrderId", req.StopClientOrderID)
		}
		if req.LimitClientOrderID != "" {
			params.Set("belowClientOrderId", req.LimitClientOrderID)
		}
	default:
		return nil, fmt.Errorf("unsupported OCO side %q", req.Side)
	}

	body, err := c.doRequest(ctx, "POST", "/api/v3/orderList/oco", params, true)
	if err != nil {
		return nil, ErrorWithContext(err, "PlaceSpotOCO")
	}

	var resp OCOResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, ErrorWithContext(err, "PlaceSpotOCO")
	}
	return &resp, nil
}

// GetOCOByListClientOrderID resolves an OCO's state by its list client order
// id — the recovery path when a placement outcome is ambiguous.
func (c *Client) GetOCOByListClientOrderID(ctx context.Context, listClientOrderID string) (*OCOResponse, error) {
	params := url.Values{}
	params.Set("origClientOrderId", listClientOrderID)

	body, err := c.doRequest(ctx, "GET", "/api/v3/orderList", params, true)
	if err != nil {
		return nil, ErrorWithContext(err, "GetOCOByListClientOrderID")
	}

	var resp OCOResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, ErrorWithContext(err, "GetOCOByListClientOrderID")
	}
	return &resp, nil
}
