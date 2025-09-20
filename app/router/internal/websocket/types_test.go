package websocket

import (
	"encoding/json"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
)

func TestStreamMessage(t *testing.T) {
	t.Run("unmarshals JSON correctly", func(t *testing.T) {
		jsonData := `{
			"stream": "btcusdt@depth",
			"data": {
				"e": "depthUpdate",
				"s": "BTCUSDT"
			}
		}`

		var msg StreamMessage
		err := json.Unmarshal([]byte(jsonData), &msg)

		assert.NoError(t, err)
		assert.Equal(t, "btcusdt@depth", msg.Stream)
		assert.NotNil(t, msg.Data)

		// Check that data can be unmarshaled to specific event
		var dataMap map[string]interface{}
		err = json.Unmarshal(msg.Data, &dataMap)
		assert.NoError(t, err)
		assert.Equal(t, "depthUpdate", dataMap["e"])
		assert.Equal(t, "BTCUSDT", dataMap["s"])
	})

	t.Run("marshals to JSON correctly", func(t *testing.T) {
		data := json.RawMessage(`{"test":"value"}`)
		msg := StreamMessage{
			Stream: "test@stream",
			Data:   data,
		}

		jsonBytes, err := json.Marshal(msg)
		assert.NoError(t, err)

		var unmarshaled StreamMessage
		err = json.Unmarshal(jsonBytes, &unmarshaled)
		assert.NoError(t, err)
		assert.Equal(t, "test@stream", unmarshaled.Stream)

		// Compare the JSON content, not the byte representation
		var expectedData, actualData map[string]interface{}
		err = json.Unmarshal(data, &expectedData)
		assert.NoError(t, err)
		err = json.Unmarshal(unmarshaled.Data, &actualData)
		assert.NoError(t, err)
		assert.Equal(t, expectedData, actualData)
	})

	t.Run("handles empty data", func(t *testing.T) {
		msg := StreamMessage{
			Stream: "empty@stream",
			Data:   nil,
		}

		jsonBytes, err := json.Marshal(msg)
		assert.NoError(t, err)
		assert.Contains(t, string(jsonBytes), "empty@stream")
	})
}

func TestSubscriptionRequest(t *testing.T) {
	t.Run("marshals subscription request correctly", func(t *testing.T) {
		req := SubscriptionRequest{
			Method: "SUBSCRIBE",
			Params: []string{"btcusdt@depth", "ethusdt@ticker"},
			ID:     123,
		}

		jsonBytes, err := json.Marshal(req)
		assert.NoError(t, err)

		expectedJSON := `{"method":"SUBSCRIBE","params":["btcusdt@depth","ethusdt@ticker"],"id":123}`
		assert.JSONEq(t, expectedJSON, string(jsonBytes))
	})

	t.Run("handles empty parameters", func(t *testing.T) {
		req := SubscriptionRequest{
			Method: "UNSUBSCRIBE",
			Params: []string{},
			ID:     456,
		}

		jsonBytes, err := json.Marshal(req)
		assert.NoError(t, err)

		var unmarshaled SubscriptionRequest
		err = json.Unmarshal(jsonBytes, &unmarshaled)
		assert.NoError(t, err)
		assert.Equal(t, "UNSUBSCRIBE", unmarshaled.Method)
		assert.Empty(t, unmarshaled.Params)
		assert.Equal(t, 456, unmarshaled.ID)
	})
}

func TestSubscriptionResponse(t *testing.T) {
	t.Run("unmarshals successful response", func(t *testing.T) {
		jsonData := `{
			"result": null,
			"id": 123
		}`

		var resp SubscriptionResponse
		err := json.Unmarshal([]byte(jsonData), &resp)

		assert.NoError(t, err)
		assert.Equal(t, 123, resp.ID)
		assert.Nil(t, resp.Error)
	})

	t.Run("unmarshals error response", func(t *testing.T) {
		jsonData := `{
			"result": null,
			"id": 456,
			"error": {
				"code": -2011,
				"msg": "Invalid symbol."
			}
		}`

		var resp SubscriptionResponse
		err := json.Unmarshal([]byte(jsonData), &resp)

		assert.NoError(t, err)
		assert.Equal(t, 456, resp.ID)
		assert.NotNil(t, resp.Error)
		assert.Equal(t, -2011, resp.Error.Code)
		assert.Equal(t, "Invalid symbol.", resp.Error.Msg)
	})
}

func TestDepthUpdateEvent(t *testing.T) {
	t.Run("unmarshals depth update correctly", func(t *testing.T) {
		jsonData := `{
			"e": "depthUpdate",
			"E": 1499404630606,
			"s": "BTCUSDT",
			"U": 157,
			"u": 160,
			"b": [
				["0.0024", "10"],
				["0.0025", "20"]
			],
			"a": [
				["0.0026", "100"],
				["0.0027", "200"]
			]
		}`

		var event DepthUpdateEvent
		err := json.Unmarshal([]byte(jsonData), &event)

		assert.NoError(t, err)
		assert.Equal(t, "depthUpdate", event.EventType)
		assert.Equal(t, int64(1499404630606), event.EventTime)
		assert.Equal(t, "BTCUSDT", event.Symbol)
		assert.Equal(t, int64(157), event.FirstUpdateID)
		assert.Equal(t, int64(160), event.FinalUpdateID)

		// Check bids
		assert.Len(t, event.Bids, 2)
		expectedBidPrice := decimal.NewFromFloat(0.0024)
		expectedBidQty := decimal.NewFromFloat(10)
		assert.True(t, expectedBidPrice.Equal(event.Bids[0].Price))
		assert.True(t, expectedBidQty.Equal(event.Bids[0].Quantity))

		// Check asks
		assert.Len(t, event.Asks, 2)
		expectedAskPrice := decimal.NewFromFloat(0.0026)
		expectedAskQty := decimal.NewFromFloat(100)
		assert.True(t, expectedAskPrice.Equal(event.Asks[0].Price))
		assert.True(t, expectedAskQty.Equal(event.Asks[0].Quantity))
	})

	t.Run("handles empty bids and asks", func(t *testing.T) {
		jsonData := `{
			"e": "depthUpdate",
			"E": 1499404630606,
			"s": "BTCUSDT",
			"U": 157,
			"u": 160,
			"b": [],
			"a": []
		}`

		var event DepthUpdateEvent
		err := json.Unmarshal([]byte(jsonData), &event)

		assert.NoError(t, err)
		assert.Empty(t, event.Bids)
		assert.Empty(t, event.Asks)
	})
}

func TestPriceLevel(t *testing.T) {
	t.Run("unmarshals from string array", func(t *testing.T) {
		// Test custom unmarshaling for Binance format
		jsonData := `["0.00123456", "789.12345678"]`

		var level []string
		err := json.Unmarshal([]byte(jsonData), &level)
		assert.NoError(t, err)

		// Manual conversion (this is what we'll implement in the real types)
		price, err := decimal.NewFromString(level[0])
		assert.NoError(t, err)
		quantity, err := decimal.NewFromString(level[1])
		assert.NoError(t, err)

		priceLevel := PriceLevel{Price: price, Quantity: quantity}

		expectedPrice := decimal.NewFromFloat(0.00123456)
		expectedQty := decimal.NewFromFloat(789.12345678)
		assert.True(t, expectedPrice.Equal(priceLevel.Price))
		assert.True(t, expectedQty.Equal(priceLevel.Quantity))
	})

	t.Run("marshals to JSON correctly", func(t *testing.T) {
		level := PriceLevel{
			Price:    decimal.NewFromFloat(50000.12),
			Quantity: decimal.NewFromFloat(1.5),
		}

		jsonBytes, err := json.Marshal(level)
		assert.NoError(t, err)

		var unmarshaled PriceLevel
		err = json.Unmarshal(jsonBytes, &unmarshaled)
		assert.NoError(t, err)
		assert.True(t, level.Price.Equal(unmarshaled.Price))
		assert.True(t, level.Quantity.Equal(unmarshaled.Quantity))
	})
}

func TestTickerEvent(t *testing.T) {
	t.Run("unmarshals ticker event correctly", func(t *testing.T) {
		jsonData := `{
			"e": "24hrTicker",
			"E": 1499404630606,
			"s": "BTCUSDT",
			"p": "100.00000000",
			"P": "2.000",
			"w": "45000.00000000",
			"x": "44900.00000000",
			"c": "45000.00000000",
			"Q": "1.00000000",
			"b": "44999.00000000",
			"B": "10.00000000",
			"a": "45001.00000000",
			"A": "5.00000000",
			"o": "44900.00000000",
			"h": "45100.00000000",
			"l": "44800.00000000",
			"v": "1000.00000000",
			"q": "45000000.00000000",
			"O": 1499404630606,
			"C": 1499404630606,
			"F": 1,
			"L": 1000,
			"n": 1000
		}`

		var event TickerEvent
		err := json.Unmarshal([]byte(jsonData), &event)

		assert.NoError(t, err)
		assert.Equal(t, "24hrTicker", event.EventType)
		assert.Equal(t, "BTCUSDT", event.Symbol)

		expectedPrice := decimal.NewFromFloat(100.0)
		assert.True(t, expectedPrice.Equal(event.PriceChange))

		expectedLastPrice := decimal.NewFromFloat(45000.0)
		assert.True(t, expectedLastPrice.Equal(event.LastPrice))

		assert.Equal(t, int64(1000), event.Count)
	})
}

func TestAccountUpdateEvent(t *testing.T) {
	t.Run("unmarshals account update correctly", func(t *testing.T) {
		jsonData := `{
			"e": "outboundAccountPosition",
			"E": 1499404630606,
			"u": 1499404630606,
			"B": [
				{
					"a": "BTC",
					"f": "1.00000000",
					"l": "0.00000000"
				},
				{
					"a": "USDT",
					"f": "1000.00000000",
					"l": "500.00000000"
				}
			]
		}`

		var event AccountUpdateEvent
		err := json.Unmarshal([]byte(jsonData), &event)

		assert.NoError(t, err)
		assert.Equal(t, "outboundAccountPosition", event.EventType)
		assert.Equal(t, int64(1499404630606), event.EventTime)
		assert.Len(t, event.Balances, 2)

		// Check BTC balance
		btc := event.Balances[0]
		assert.Equal(t, "BTC", btc.Asset)
		expectedFree := decimal.NewFromFloat(1.0)
		assert.True(t, expectedFree.Equal(btc.Free))
		assert.True(t, decimal.Zero.Equal(btc.Locked))

		// Check USDT balance
		usdt := event.Balances[1]
		assert.Equal(t, "USDT", usdt.Asset)
		expectedUsdtFree := decimal.NewFromFloat(1000.0)
		expectedUsdtLocked := decimal.NewFromFloat(500.0)
		assert.True(t, expectedUsdtFree.Equal(usdt.Free))
		assert.True(t, expectedUsdtLocked.Equal(usdt.Locked))
	})
}

func TestOrderUpdateEvent(t *testing.T) {
	t.Run("unmarshals order update correctly", func(t *testing.T) {
		jsonData := `{
			"e": "executionReport",
			"E": 1499404630606,
			"s": "BTCUSDT",
			"c": "my-order-id",
			"S": "BUY",
			"o": "LIMIT",
			"f": "GTC",
			"q": "1.00000000",
			"p": "50000.00000000",
			"P": "0.00000000",
			"F": "0.00000000",
			"g": -1,
			"C": "",
			"x": "NEW",
			"X": "NEW",
			"r": "NONE",
			"i": 123456,
			"l": "0.00000000",
			"z": "0.00000000",
			"L": "0.00000000",
			"n": "0.00000000",
			"N": "",
			"T": 1499404630606,
			"t": -1,
			"w": true,
			"m": false
		}`

		var event OrderUpdateEvent
		err := json.Unmarshal([]byte(jsonData), &event)

		assert.NoError(t, err)
		assert.Equal(t, "executionReport", event.EventType)
		assert.Equal(t, "BTCUSDT", event.Symbol)
		assert.Equal(t, "my-order-id", event.ClientOrderID)
		assert.Equal(t, "BUY", event.Side)
		assert.Equal(t, "LIMIT", event.OrderType)
		assert.Equal(t, "NEW", event.OrderStatus)
		assert.Equal(t, int64(123456), event.OrderID)
		assert.True(t, event.IsOrderWorking)
		assert.False(t, event.IsMaker)

		expectedQty := decimal.NewFromFloat(1.0)
		expectedPrice := decimal.NewFromFloat(50000.0)
		assert.True(t, expectedQty.Equal(event.Quantity))
		assert.True(t, expectedPrice.Equal(event.Price))
	})
}

func TestConnectionState(t *testing.T) {
	t.Run("string representation is correct", func(t *testing.T) {
		testCases := []struct {
			state    ConnectionState
			expected string
		}{
			{StateDisconnected, "disconnected"},
			{StateConnecting, "connecting"},
			{StateConnected, "connected"},
			{StateReconnecting, "reconnecting"},
			{StateClosed, "closed"},
			{ConnectionState(999), "unknown"},
		}

		for _, tc := range testCases {
			assert.Equal(t, tc.expected, tc.state.String())
		}
	})

	t.Run("constants have correct values", func(t *testing.T) {
		assert.Equal(t, ConnectionState(0), StateDisconnected)
		assert.Equal(t, ConnectionState(1), StateConnecting)
		assert.Equal(t, ConnectionState(2), StateConnected)
		assert.Equal(t, ConnectionState(3), StateReconnecting)
		assert.Equal(t, ConnectionState(4), StateClosed)
	})
}

func TestEventHandlerInterfaces(t *testing.T) {
	t.Run("EventHandler interface is defined", func(t *testing.T) {
		// Test that the interface exists by creating a mock implementation
		var handler EventHandler = &mockEventHandler{}
		assert.NotNil(t, handler)
	})

	t.Run("DepthHandler interface is defined", func(t *testing.T) {
		var handler DepthHandler = &mockDepthHandler{}
		assert.NotNil(t, handler)
	})

	t.Run("TickerHandler interface is defined", func(t *testing.T) {
		var handler TickerHandler = &mockTickerHandler{}
		assert.NotNil(t, handler)
	})

	t.Run("UserStreamHandler interface is defined", func(t *testing.T) {
		var handler UserStreamHandler = &mockUserStreamHandler{}
		assert.NotNil(t, handler)
	})
}

// Mock implementations for interface testing
type mockEventHandler struct{}

func (m *mockEventHandler) HandleEvent(eventType string, data json.RawMessage) error {
	return nil
}

type mockDepthHandler struct{}

func (m *mockDepthHandler) HandleDepthUpdate(event *DepthUpdateEvent) error {
	return nil
}

type mockTickerHandler struct{}

func (m *mockTickerHandler) HandleTickerUpdate(event *TickerEvent) error {
	return nil
}

type mockUserStreamHandler struct{}

func (m *mockUserStreamHandler) HandleAccountUpdate(event *AccountUpdateEvent) error {
	return nil
}

func (m *mockUserStreamHandler) HandleOrderUpdate(event *OrderUpdateEvent) error {
	return nil
}

func (m *mockUserStreamHandler) HandleListenKeyExpired() error {
	return nil
}
