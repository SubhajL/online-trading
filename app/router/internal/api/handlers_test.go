package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	"router/internal/orders"
)

// MockOrderManager is a mock implementation of the order manager interface
type MockOrderManager struct {
	mock.Mock
}

func (m *MockOrderManager) PlaceBracketOrder(ctx context.Context, req *orders.PlaceBracketRequest) (*orders.PlaceBracketResponse, error) {
	args := m.Called(ctx, req)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*orders.PlaceBracketResponse), args.Error(1)
}

func (m *MockOrderManager) CancelOrder(ctx context.Context, req *orders.CancelRequest) error {
	args := m.Called(ctx, req)
	return args.Error(0)
}

func (m *MockOrderManager) CloseAllPositions(ctx context.Context, req *orders.CloseAllRequest) error {
	args := m.Called(ctx, req)
	return args.Error(0)
}

func (m *MockOrderManager) CancelOpenOrders(ctx context.Context, req *orders.CancelOpenOrdersRequest) (*orders.CancelOpenOrdersResponse, error) {
	args := m.Called(ctx, req)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*orders.CancelOpenOrdersResponse), args.Error(1)
}

func (m *MockOrderManager) ClosePositions(ctx context.Context, req *orders.ClosePositionsRequest) (*orders.ClosePositionsResponse, error) {
	args := m.Called(ctx, req)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*orders.ClosePositionsResponse), args.Error(1)
}

func (m *MockOrderManager) ReconcileOrder(ctx context.Context, clientOrderID string) error {
	args := m.Called(ctx, clientOrderID)
	return args.Error(0)
}

func TestHealthzHandler(t *testing.T) {
	logger := zerolog.Nop()
	mockManager := new(MockOrderManager)
	handlers := NewHandlers(mockManager, logger, nil, nil)

	tests := []struct {
		name       string
		method     string
		wantStatus int
		wantBody   map[string]string
	}{
		{
			name:       "successful health check",
			method:     http.MethodGet,
			wantStatus: http.StatusOK,
			wantBody: map[string]string{
				"status":  "healthy",
				"service": "order-router",
			},
		},
		{
			name:       "invalid method",
			method:     http.MethodPost,
			wantStatus: http.StatusMethodNotAllowed,
			wantBody: map[string]string{
				"error": "Method not allowed",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(tt.method, "/healthz", nil)
			w := httptest.NewRecorder()

			handlers.HealthzHandler(w, req)

			assert.Equal(t, tt.wantStatus, w.Code)

			var response map[string]string
			err := json.Unmarshal(w.Body.Bytes(), &response)
			assert.NoError(t, err)
			assert.Equal(t, tt.wantBody, response)
		})
	}
}

func TestReadyzHandler(t *testing.T) {
	logger := zerolog.Nop()
	mockManager := new(MockOrderManager)
	handlers := NewHandlers(mockManager, logger, nil, nil)

	tests := []struct {
		name       string
		method     string
		wantStatus int
		wantBody   map[string]string
	}{
		{
			name:       "successful readiness check",
			method:     http.MethodGet,
			wantStatus: http.StatusOK,
			wantBody: map[string]string{
				"status":  "ready",
				"service": "order-router",
			},
		},
		{
			name:       "invalid method",
			method:     http.MethodPost,
			wantStatus: http.StatusMethodNotAllowed,
			wantBody: map[string]string{
				"error": "Method not allowed",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(tt.method, "/readyz", nil)
			w := httptest.NewRecorder()

			handlers.ReadyzHandler(w, req)

			assert.Equal(t, tt.wantStatus, w.Code)

			var response map[string]string
			err := json.Unmarshal(w.Body.Bytes(), &response)
			assert.NoError(t, err)
			assert.Equal(t, tt.wantBody, response)
		})
	}
}

func TestPlaceBracketHandler(t *testing.T) {
	logger := zerolog.Nop()
	mockManager := new(MockOrderManager)
	handlers := NewHandlers(mockManager, logger, nil, nil)

	tests := []struct {
		name       string
		method     string
		body       interface{}
		setupMock  func()
		wantStatus int
		wantErr    string
	}{
		{
			name:   "successful bracket order",
			method: http.MethodPost,
			body: &orders.PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "BUY",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
				StopLossPrice:    decimal.RequireFromString("49000"),
			},
			setupMock: func() {
				mockManager.On("PlaceBracketOrder", mock.Anything, mock.AnythingOfType("*orders.PlaceBracketRequest")).
					Return(&orders.PlaceBracketResponse{
						BracketOrderID: "test-bracket-id",
						Symbol:         "BTCUSDT",
						Side:           "BUY",
						Quantity:       decimal.RequireFromString("0.001"),
						ClientOrderIDs: orders.ClientOrderIDs{
							Main:        "main-order-id",
							TakeProfits: []string{"tp1-id"},
							StopLoss:    "sl-id",
						},
					}, nil).Once()
			},
			wantStatus: http.StatusOK,
		},
		{
			name:       "invalid method",
			method:     http.MethodGet,
			body:       nil,
			setupMock:  func() {},
			wantStatus: http.StatusMethodNotAllowed,
			wantErr:    "Method not allowed",
		},
		{
			name:       "invalid request body",
			method:     http.MethodPost,
			body:       "invalid json",
			setupMock:  func() {},
			wantStatus: http.StatusBadRequest,
			wantErr:    "Invalid request body",
		},
		{
			name:   "order placement error",
			method: http.MethodPost,
			body: &orders.PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "BUY",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
				StopLossPrice:    decimal.RequireFromString("49000"),
			},
			setupMock: func() {
				mockManager.On("PlaceBracketOrder", mock.Anything, mock.AnythingOfType("*orders.PlaceBracketRequest")).
					Return(nil, errors.New("insufficient balance")).Once()
			},
			wantStatus: http.StatusBadRequest,
			wantErr:    "insufficient balance",
		},
		{
			name:   "market order with zero entry price",
			method: http.MethodPost,
			body: &orders.PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "BUY",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.Zero,
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
				StopLossPrice:    decimal.RequireFromString("49000"),
			},
			setupMock: func() {
				mockManager.On("PlaceBracketOrder", mock.Anything, mock.MatchedBy(func(req *orders.PlaceBracketRequest) bool {
					return req.OrderType == "MARKET"
				})).Return(&orders.PlaceBracketResponse{
					BracketOrderID: "test-bracket-id",
					Symbol:         "BTCUSDT",
					Side:           "BUY",
					Quantity:       decimal.RequireFromString("0.001"),
				}, nil).Once()
			},
			wantStatus: http.StatusOK,
		},
		{
			name:   "partial failure response",
			method: http.MethodPost,
			body: &orders.PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "BUY",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
				StopLossPrice:    decimal.RequireFromString("49000"),
			},
			setupMock: func() {
				mockManager.On("PlaceBracketOrder", mock.Anything, mock.AnythingOfType("*orders.PlaceBracketRequest")).
					Return(&orders.PlaceBracketResponse{
						BracketOrderID: "test-bracket-id",
						Symbol:         "BTCUSDT",
						Side:           "BUY",
						Quantity:       decimal.RequireFromString("0.001"),
						PartialFailure: true,
						Errors:         []string{"SL: insufficient balance"},
					}, nil).Once()
			},
			wantStatus: http.StatusOK,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mockManager.ExpectedCalls = nil
			tt.setupMock()

			var body io.Reader
			if tt.body != nil {
				data, err := json.Marshal(tt.body)
				assert.NoError(t, err)
				body = bytes.NewReader(data)
			}

			req := httptest.NewRequest(tt.method, "/place_bracket", body)
			w := httptest.NewRecorder()

			handlers.PlaceBracketHandler(w, req)

			assert.Equal(t, tt.wantStatus, w.Code)

			if tt.wantErr != "" {
				var response map[string]string
				err := json.Unmarshal(w.Body.Bytes(), &response)
				assert.NoError(t, err)
				assert.Equal(t, tt.wantErr, response["error"])
			}

			mockManager.AssertExpectations(t)
		})
	}
}

type stubIntentPersister struct {
	called bool
}

func (s *stubIntentPersister) PersistBracketIntent(
	_ctx context.Context,
	_req orders.PlaceBracketRequest,
	_resp orders.PlaceBracketResponse,
) error {
	s.called = true
	return nil
}

type stubSpotExecutionPersister struct {
	called    bool
	snapshots []orders.SpotExecutionSnapshot
}

func (s *stubSpotExecutionPersister) PersistSpotExecution(
	_ctx context.Context,
	snapshot orders.SpotExecutionSnapshot,
) error {
	s.called = true
	s.snapshots = append(s.snapshots, snapshot)
	return nil
}

func TestPlaceBracketHandler_PersistsIntentsWhenConfigured(t *testing.T) {
	logger := zerolog.Nop()
	mockManager := new(MockOrderManager)
	stub := &stubIntentPersister{}
	handlers := NewHandlers(mockManager, logger, stub, nil)

	mockManager.On("PlaceBracketOrder", mock.Anything, mock.AnythingOfType("*orders.PlaceBracketRequest")).
		Return(&orders.PlaceBracketResponse{
			BracketOrderID: "test-bracket-id",
			Symbol:         "BTCUSDT",
			Side:           "BUY",
			Quantity:       decimal.RequireFromString("0.001"),
			ClientOrderIDs: orders.ClientOrderIDs{
				Main:        "main-order-id",
				TakeProfits: []string{"tp1-id"},
				StopLoss:    "sl-id",
			},
		}, nil).Once()

	body := &orders.PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.001"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
		StopLossPrice:    decimal.RequireFromString("49000"),
		IsFutures:        true,
	}
	raw, err := json.Marshal(body)
	require.NoError(t, err)

	req := httptest.NewRequest(http.MethodPost, "/place_bracket", bytes.NewReader(raw))
	w := httptest.NewRecorder()
	handlers.PlaceBracketHandler(w, req)

	require.Equal(t, http.StatusOK, w.Code)
	require.True(t, stub.called)
}

func TestPlaceBracketHandler_PersistsSpotExecutionsAfterIntentPersistence(t *testing.T) {
	logger := zerolog.Nop()
	mockManager := new(MockOrderManager)
	intentPersister := &stubIntentPersister{}
	executionPersister := &stubSpotExecutionPersister{}
	handlers := NewHandlers(mockManager, logger, intentPersister, executionPersister)

	mockManager.On("PlaceBracketOrder", mock.Anything, mock.AnythingOfType("*orders.PlaceBracketRequest")).
		Return(&orders.PlaceBracketResponse{
			BracketOrderID: "test-bracket-id",
			Symbol:         "BTCUSDT",
			Side:           "BUY",
			Quantity:       decimal.RequireFromString("0.001"),
			ClientOrderIDs: orders.ClientOrderIDs{
				Main:        "main-order-id",
				TakeProfits: []string{"tp1-id"},
				StopLoss:    "sl-id",
			},
			SpotExecutionSnapshots: []orders.SpotExecutionSnapshot{
				{
					Symbol:        "BTCUSDT",
					OrderID:       100,
					ClientOrderID: "main-order-id",
					Side:          "BUY",
					OrderType:     "LIMIT",
					Price:         decimal.RequireFromString("50000"),
					Quantity:      decimal.RequireFromString("0.001"),
					ExecutedQty:   decimal.RequireFromString("0.001"),
					Status:        "FILLED",
					UpdateTime:    time.Now().UTC(),
				},
			},
		}, nil).Once()

	body := &orders.PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.001"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
		StopLossPrice:    decimal.RequireFromString("49000"),
	}
	raw, err := json.Marshal(body)
	require.NoError(t, err)

	req := httptest.NewRequest(http.MethodPost, "/place_bracket", bytes.NewReader(raw))
	w := httptest.NewRecorder()
	handlers.PlaceBracketHandler(w, req)

	require.Equal(t, http.StatusOK, w.Code)
	require.True(t, intentPersister.called)
	require.True(t, executionPersister.called)
	require.Len(t, executionPersister.snapshots, 1)
	assert.Equal(t, "main-order-id", executionPersister.snapshots[0].ClientOrderID)
}

func TestPlaceBracketHandler_PersistsSnapshotsOnErrorWhenResponseExists(t *testing.T) {
	logger := zerolog.Nop()
	mockManager := new(MockOrderManager)
	intentPersister := &stubIntentPersister{}
	executionPersister := &stubSpotExecutionPersister{}
	handlers := NewHandlers(mockManager, logger, intentPersister, executionPersister)

	mockManager.On("PlaceBracketOrder", mock.Anything, mock.AnythingOfType("*orders.PlaceBracketRequest")).
		Return(&orders.PlaceBracketResponse{
			BracketOrderID: "test-bracket-id",
			Symbol:         "BTCUSDT",
			Side:           "BUY",
			Quantity:       decimal.RequireFromString("0.001"),
			ClientOrderIDs: orders.ClientOrderIDs{
				Main:        "main-order-id",
				TakeProfits: []string{"tp1-id"},
				StopLoss:    "sl-id",
			},
			SpotExecutionSnapshots: []orders.SpotExecutionSnapshot{
				{
					Symbol:        "BTCUSDT",
					OrderID:       100,
					ClientOrderID: "main-order-id",
					Side:          "BUY",
					OrderType:     "LIMIT",
					Price:         decimal.RequireFromString("50000"),
					Quantity:      decimal.RequireFromString("0.001"),
					ExecutedQty:   decimal.RequireFromString("0.001"),
					Status:        "FILLED",
					UpdateTime:    time.Now().UTC(),
				},
			},
		}, errors.New("critical bracket placement failure")).Once()

	body := &orders.PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.001"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
		StopLossPrice:    decimal.RequireFromString("49000"),
	}
	raw, err := json.Marshal(body)
	require.NoError(t, err)

	req := httptest.NewRequest(http.MethodPost, "/place_bracket", bytes.NewReader(raw))
	w := httptest.NewRecorder()
	handlers.PlaceBracketHandler(w, req)

	require.Equal(t, http.StatusBadRequest, w.Code)
	require.True(t, intentPersister.called)
	require.True(t, executionPersister.called)
	require.Len(t, executionPersister.snapshots, 1)
}

func TestCancelHandler(t *testing.T) {
	logger := zerolog.Nop()
	mockManager := new(MockOrderManager)
	handlers := NewHandlers(mockManager, logger, nil, nil)

	tests := []struct {
		name       string
		method     string
		body       interface{}
		setupMock  func()
		wantStatus int
		wantErr    string
	}{
		{
			name:   "successful cancel",
			method: http.MethodPost,
			body: &orders.CancelRequest{
				Symbol:  "BTCUSDT",
				OrderID: 123456,
			},
			setupMock: func() {
				mockManager.On("CancelOrder", mock.Anything, mock.AnythingOfType("*orders.CancelRequest")).
					Return(nil).Once()
			},
			wantStatus: http.StatusOK,
		},
		{
			name:       "invalid method",
			method:     http.MethodGet,
			body:       nil,
			setupMock:  func() {},
			wantStatus: http.StatusMethodNotAllowed,
			wantErr:    "Method not allowed",
		},
		{
			name:       "invalid request body",
			method:     http.MethodPost,
			body:       "invalid json",
			setupMock:  func() {},
			wantStatus: http.StatusBadRequest,
			wantErr:    "Invalid request body",
		},
		{
			name:   "cancel error",
			method: http.MethodPost,
			body: &orders.CancelRequest{
				Symbol:  "BTCUSDT",
				OrderID: 123456,
			},
			setupMock: func() {
				mockManager.On("CancelOrder", mock.Anything, mock.AnythingOfType("*orders.CancelRequest")).
					Return(errors.New("order not found")).Once()
			},
			wantStatus: http.StatusBadRequest,
			wantErr:    "order not found",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mockManager.ExpectedCalls = nil
			tt.setupMock()

			var body io.Reader
			if tt.body != nil {
				data, err := json.Marshal(tt.body)
				assert.NoError(t, err)
				body = bytes.NewReader(data)
			}

			req := httptest.NewRequest(tt.method, "/cancel", body)
			w := httptest.NewRecorder()

			handlers.CancelHandler(w, req)

			assert.Equal(t, tt.wantStatus, w.Code)

			if tt.wantErr != "" {
				var response map[string]string
				err := json.Unmarshal(w.Body.Bytes(), &response)
				assert.NoError(t, err)
				assert.Equal(t, tt.wantErr, response["error"])
			}

			mockManager.AssertExpectations(t)
		})
	}
}

func TestCloseAllHandler(t *testing.T) {
	logger := zerolog.Nop()
	mockManager := new(MockOrderManager)
	handlers := NewHandlers(mockManager, logger, nil, nil)

	tests := []struct {
		name       string
		method     string
		body       interface{}
		setupMock  func()
		wantStatus int
		wantErr    string
	}{
		{
			name:   "successful close all",
			method: http.MethodPost,
			body: &orders.CloseAllRequest{
				Symbol:    "BTCUSDT",
				IsFutures: true,
			},
			setupMock: func() {
				mockManager.On("CloseAllPositions", mock.Anything, mock.AnythingOfType("*orders.CloseAllRequest")).
					Return(nil).Once()
			},
			wantStatus: http.StatusOK,
		},
		{
			name:       "invalid method",
			method:     http.MethodGet,
			body:       nil,
			setupMock:  func() {},
			wantStatus: http.StatusMethodNotAllowed,
			wantErr:    "Method not allowed",
		},
		{
			name:       "invalid request body",
			method:     http.MethodPost,
			body:       "invalid json",
			setupMock:  func() {},
			wantStatus: http.StatusBadRequest,
			wantErr:    "Invalid request body",
		},
		{
			name:   "close all error",
			method: http.MethodPost,
			body: &orders.CloseAllRequest{
				Symbol:    "BTCUSDT",
				IsFutures: false,
			},
			setupMock: func() {
				mockManager.On("CloseAllPositions", mock.Anything, mock.AnythingOfType("*orders.CloseAllRequest")).
					Return(errors.New("no positions to close")).Once()
			},
			wantStatus: http.StatusBadRequest,
			wantErr:    "no positions to close",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mockManager.ExpectedCalls = nil
			tt.setupMock()

			var body io.Reader
			if tt.body != nil {
				data, err := json.Marshal(tt.body)
				assert.NoError(t, err)
				body = bytes.NewReader(data)
			}

			req := httptest.NewRequest(tt.method, "/close_all", body)
			w := httptest.NewRecorder()

			handlers.CloseAllHandler(w, req)

			assert.Equal(t, tt.wantStatus, w.Code)

			if tt.wantErr != "" {
				var response map[string]string
				err := json.Unmarshal(w.Body.Bytes(), &response)
				assert.NoError(t, err)
				assert.Equal(t, tt.wantErr, response["error"])
			} else if tt.wantStatus == http.StatusOK {
				var response map[string]string
				err := json.Unmarshal(w.Body.Bytes(), &response)
				assert.NoError(t, err)
				assert.Equal(t, "success", response["status"])
			}

			mockManager.AssertExpectations(t)
		})
	}
}

func TestCancelOpenOrdersHandler(t *testing.T) {
	logger := zerolog.Nop()
	mockManager := new(MockOrderManager)
	handlers := NewHandlers(mockManager, logger, nil, nil)

	tests := []struct {
		name       string
		method     string
		body       interface{}
		setupMock  func()
		wantStatus int
		wantErr    string
		wantBody   *orders.CancelOpenOrdersResponse
	}{
		{
			name:   "successful cancel open orders",
			method: http.MethodPost,
			body: &orders.CancelOpenOrdersRequest{
				Scope:   orders.EmergencyScopeAll,
				Symbols: []string{"BTCUSDT", "ETHUSDT"},
			},
			setupMock: func() {
				mockManager.On("CancelOpenOrders", mock.Anything, mock.AnythingOfType("*orders.CancelOpenOrdersRequest")).
					Return(&orders.CancelOpenOrdersResponse{CanceledOrders: 3}, nil).Once()
			},
			wantStatus: http.StatusOK,
			wantBody:   &orders.CancelOpenOrdersResponse{CanceledOrders: 3},
		},
		{
			name:       "invalid method",
			method:     http.MethodGet,
			setupMock:  func() {},
			wantStatus: http.StatusMethodNotAllowed,
			wantErr:    "Method not allowed",
		},
		{
			name:       "invalid request body",
			method:     http.MethodPost,
			body:       "invalid json",
			setupMock:  func() {},
			wantStatus: http.StatusBadRequest,
			wantErr:    "Invalid request body",
		},
		{
			name:   "cancel open orders error",
			method: http.MethodPost,
			body: &orders.CancelOpenOrdersRequest{
				Scope: orders.EmergencyScopeFutures,
			},
			setupMock: func() {
				mockManager.On("CancelOpenOrders", mock.Anything, mock.AnythingOfType("*orders.CancelOpenOrdersRequest")).
					Return(nil, errors.New("futures cancel not supported")).Once()
			},
			wantStatus: http.StatusBadRequest,
			wantErr:    "futures cancel not supported",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mockManager.ExpectedCalls = nil
			tt.setupMock()

			var body io.Reader
			if tt.body != nil {
				data, err := json.Marshal(tt.body)
				assert.NoError(t, err)
				body = bytes.NewReader(data)
			}

			req := httptest.NewRequest(tt.method, "/cancel_open_orders", body)
			w := httptest.NewRecorder()

			handlers.CancelOpenOrdersHandler(w, req)

			assert.Equal(t, tt.wantStatus, w.Code)

			if tt.wantErr != "" {
				var response map[string]string
				err := json.Unmarshal(w.Body.Bytes(), &response)
				assert.NoError(t, err)
				assert.Equal(t, tt.wantErr, response["error"])
			} else if tt.wantBody != nil {
				var response orders.CancelOpenOrdersResponse
				err := json.Unmarshal(w.Body.Bytes(), &response)
				assert.NoError(t, err)
				assert.Equal(t, *tt.wantBody, response)
			}

			mockManager.AssertExpectations(t)
		})
	}
}

func TestClosePositionsHandler(t *testing.T) {
	logger := zerolog.Nop()
	mockManager := new(MockOrderManager)
	handlers := NewHandlers(mockManager, logger, nil, nil)

	tests := []struct {
		name       string
		method     string
		body       interface{}
		setupMock  func()
		wantStatus int
		wantErr    string
		wantBody   *orders.ClosePositionsResponse
	}{
		{
			name:   "successful close positions",
			method: http.MethodPost,
			body: &orders.ClosePositionsRequest{
				Scope:   orders.EmergencyScopeFutures,
				Symbols: []string{"BTCUSDT"},
			},
			setupMock: func() {
				mockManager.On("ClosePositions", mock.Anything, mock.AnythingOfType("*orders.ClosePositionsRequest")).
					Return(&orders.ClosePositionsResponse{ClosedPositions: 2}, nil).Once()
			},
			wantStatus: http.StatusOK,
			wantBody:   &orders.ClosePositionsResponse{ClosedPositions: 2},
		},
		{
			name:       "invalid method",
			method:     http.MethodGet,
			setupMock:  func() {},
			wantStatus: http.StatusMethodNotAllowed,
			wantErr:    "Method not allowed",
		},
		{
			name:       "invalid request body",
			method:     http.MethodPost,
			body:       "invalid json",
			setupMock:  func() {},
			wantStatus: http.StatusBadRequest,
			wantErr:    "Invalid request body",
		},
		{
			name:   "close positions error",
			method: http.MethodPost,
			body: &orders.ClosePositionsRequest{
				Scope: orders.EmergencyScopeSpot,
			},
			setupMock: func() {
				mockManager.On("ClosePositions", mock.Anything, mock.AnythingOfType("*orders.ClosePositionsRequest")).
					Return(nil, errors.New("spot close not supported")).Once()
			},
			wantStatus: http.StatusBadRequest,
			wantErr:    "spot close not supported",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mockManager.ExpectedCalls = nil
			tt.setupMock()

			var body io.Reader
			if tt.body != nil {
				data, err := json.Marshal(tt.body)
				assert.NoError(t, err)
				body = bytes.NewReader(data)
			}

			req := httptest.NewRequest(tt.method, "/close_positions", body)
			w := httptest.NewRecorder()

			handlers.ClosePositionsHandler(w, req)

			assert.Equal(t, tt.wantStatus, w.Code)

			if tt.wantErr != "" {
				var response map[string]string
				err := json.Unmarshal(w.Body.Bytes(), &response)
				assert.NoError(t, err)
				assert.Equal(t, tt.wantErr, response["error"])
			} else if tt.wantBody != nil {
				var response orders.ClosePositionsResponse
				err := json.Unmarshal(w.Body.Bytes(), &response)
				assert.NoError(t, err)
				assert.Equal(t, *tt.wantBody, response)
			}

			mockManager.AssertExpectations(t)
		})
	}
}

func TestParseDecimalArray(t *testing.T) {
	tests := []struct {
		name    string
		values  []interface{}
		want    []decimal.Decimal
		wantErr bool
	}{
		{
			name:   "string decimals",
			values: []interface{}{"50000", "51000", "52000"},
			want: []decimal.Decimal{
				decimal.RequireFromString("50000"),
				decimal.RequireFromString("51000"),
				decimal.RequireFromString("52000"),
			},
			wantErr: false,
		},
		{
			name:   "float64 decimals",
			values: []interface{}{50000.0, 51000.0, 52000.0},
			want: []decimal.Decimal{
				decimal.RequireFromString("50000"),
				decimal.RequireFromString("51000"),
				decimal.RequireFromString("52000"),
			},
			wantErr: false,
		},
		{
			name:   "mixed types",
			values: []interface{}{"50000", 51000.0, "52000"},
			want: []decimal.Decimal{
				decimal.RequireFromString("50000"),
				decimal.RequireFromString("51000"),
				decimal.RequireFromString("52000"),
			},
			wantErr: false,
		},
		{
			name:    "invalid string",
			values:  []interface{}{"50000", "invalid", "52000"},
			wantErr: true,
		},
		{
			name:   "skip unsupported types",
			values: []interface{}{"50000", true, 51000.0, nil},
			want: []decimal.Decimal{
				decimal.RequireFromString("50000"),
				decimal.RequireFromString("51000"),
			},
			wantErr: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseDecimalArray(tt.values)
			if tt.wantErr {
				assert.Error(t, err)
			} else {
				assert.NoError(t, err)
				assert.Equal(t, len(tt.want), len(got))
				for i := range tt.want {
					assert.True(t, tt.want[i].Equal(got[i]))
				}
			}
		})
	}
}

func TestHealthzHandler_IncludesExecutionEnv(t *testing.T) {
	logger := zerolog.Nop()
	handlers := NewHandlers(new(MockOrderManager), logger, nil, nil)
	handlers.SetExecutionEnv("testnet")

	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rr := httptest.NewRecorder()
	handlers.HealthzHandler(rr, req)

	var body map[string]string
	require.NoError(t, json.Unmarshal(rr.Body.Bytes(), &body))
	assert.Equal(t, map[string]string{
		"status":        "healthy",
		"service":       "order-router",
		"execution_env": "testnet",
	}, body)
}
