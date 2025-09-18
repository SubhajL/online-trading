package handlers

import (
	"bytes"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/models"
)

func TestSubscribeToMarketData(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("subscribes to market data successfully", func(t *testing.T) {
		manager := &mockSubscriptionManager{
			subscribeResponse: &models.SubscriptionResponse{
				Success:      true,
				Symbol:       "BTCUSDT",
				Streams:      []string{"depth", "ticker"},
				SubscribedAt: time.Now(),
			},
		}

		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/subscribe", handler.SubscribeToMarketData())

		reqBody := models.SubscribeRequest{
			Symbol:  "BTCUSDT",
			Streams: []string{"depth", "ticker"},
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams/stream-123/subscribe", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.SubscriptionResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.True(t, resp.Success)
		assert.Equal(t, "BTCUSDT", resp.Symbol)
		assert.Len(t, resp.Streams, 2)
	})

	t.Run("returns 400 for invalid request", func(t *testing.T) {
		manager := &mockSubscriptionManager{}
		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/subscribe", handler.SubscribeToMarketData())

		reqBody := models.SubscribeRequest{
			Symbol: "", // Missing symbol
			Streams: []string{"depth"},
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams/stream-123/subscribe", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusBadRequest, w.Code)

		var resp models.ErrorResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, "VALIDATION_ERROR", resp.Error)
	})

	t.Run("returns 404 for non-existent stream", func(t *testing.T) {
		manager := &mockSubscriptionManager{
			subscribeError: errors.New("stream not found"),
		}

		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/subscribe", handler.SubscribeToMarketData())

		reqBody := models.SubscribeRequest{
			Symbol:  "BTCUSDT",
			Streams: []string{"depth"},
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams/invalid-id/subscribe", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusNotFound, w.Code)
	})

	t.Run("returns 409 for already subscribed", func(t *testing.T) {
		manager := &mockSubscriptionManager{
			subscribeError: errors.New("already subscribed"),
		}

		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/subscribe", handler.SubscribeToMarketData())

		reqBody := models.SubscribeRequest{
			Symbol:  "BTCUSDT",
			Streams: []string{"depth"},
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams/stream-123/subscribe", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusConflict, w.Code)
	})
}

func TestSubscribeToUserData(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("subscribes to user data successfully", func(t *testing.T) {
		manager := &mockSubscriptionManager{
			userDataResponse: &models.SubscriptionResponse{
				Success:      true,
				SubscribedAt: time.Now(),
			},
		}

		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/user-data", handler.SubscribeToUserData())

		reqBody := models.UserDataRequest{
			ListenKey: "valid-listen-key",
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams/stream-123/user-data", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.SubscriptionResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("returns 400 for missing listen key", func(t *testing.T) {
		manager := &mockSubscriptionManager{}
		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/user-data", handler.SubscribeToUserData())

		reqBody := models.UserDataRequest{
			ListenKey: "", // Missing listen key
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams/stream-123/user-data", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusBadRequest, w.Code)
	})

	t.Run("returns 401 for invalid listen key", func(t *testing.T) {
		manager := &mockSubscriptionManager{
			userDataError: errors.New("invalid listen key"),
		}

		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/user-data", handler.SubscribeToUserData())

		reqBody := models.UserDataRequest{
			ListenKey: "invalid-key",
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams/stream-123/user-data", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusUnauthorized, w.Code)
	})
}

func TestUnsubscribe(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("unsubscribes by symbol and streams", func(t *testing.T) {
		manager := &mockSubscriptionManager{
			unsubscribeSuccess: true,
		}

		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/unsubscribe", handler.Unsubscribe())

		reqBody := models.UnsubscribeRequest{
			Symbol:  "BTCUSDT",
			Streams: []string{"depth"},
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams/stream-123/unsubscribe", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.SubscriptionResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.True(t, resp.Success)
	})

	t.Run("unsubscribes by stream ID", func(t *testing.T) {
		manager := &mockSubscriptionManager{
			unsubscribeSuccess: true,
		}

		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/unsubscribe", handler.Unsubscribe())

		reqBody := models.UnsubscribeRequest{
			StreamID: "sub-456",
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams/stream-123/unsubscribe", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)
	})

	t.Run("returns 400 for invalid request", func(t *testing.T) {
		manager := &mockSubscriptionManager{}
		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/unsubscribe", handler.Unsubscribe())

		reqBody := models.UnsubscribeRequest{} // Missing required fields
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams/stream-123/unsubscribe", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusBadRequest, w.Code)
	})

	t.Run("returns 404 for not subscribed", func(t *testing.T) {
		manager := &mockSubscriptionManager{
			unsubscribeError: errors.New("subscription not found"),
		}

		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/unsubscribe", handler.Unsubscribe())

		reqBody := models.UnsubscribeRequest{
			Symbol:  "ETHUSDT",
			Streams: []string{"ticker"},
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams/stream-123/unsubscribe", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusNotFound, w.Code)
	})
}

func TestListSubscriptions(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("returns list of subscriptions", func(t *testing.T) {
		subscriptions := []models.SubscriptionResponse{
			{Success: true, Symbol: "BTCUSDT", Streams: []string{"depth"}},
			{Success: true, Symbol: "ETHUSDT", Streams: []string{"ticker", "trades"}},
		}

		manager := &mockSubscriptionManager{
			listResponse: subscriptions,
		}

		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.GET("/streams/:id/subscriptions", handler.ListSubscriptions())

		req := httptest.NewRequest("GET", "/streams/stream-123/subscriptions", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp []models.SubscriptionResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Len(t, resp, 2)
		assert.Equal(t, "BTCUSDT", resp[0].Symbol)
	})

	t.Run("returns empty list for no subscriptions", func(t *testing.T) {
		manager := &mockSubscriptionManager{
			listResponse: []models.SubscriptionResponse{},
		}

		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.GET("/streams/:id/subscriptions", handler.ListSubscriptions())

		req := httptest.NewRequest("GET", "/streams/stream-123/subscriptions", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp []models.SubscriptionResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Empty(t, resp)
	})

	t.Run("returns 404 for non-existent stream", func(t *testing.T) {
		manager := &mockSubscriptionManager{
			listError: errors.New("stream not found"),
		}

		handler := NewSubscriptionHandlers(manager)
		router := gin.New()
		router.GET("/streams/:id/subscriptions", handler.ListSubscriptions())

		req := httptest.NewRequest("GET", "/streams/invalid-id/subscriptions", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusNotFound, w.Code)
	})
}

// Mock subscription manager for testing
type mockSubscriptionManager struct {
	subscribeResponse  *models.SubscriptionResponse
	subscribeError     error
	userDataResponse   *models.SubscriptionResponse
	userDataError      error
	unsubscribeSuccess bool
	unsubscribeError   error
	listResponse       []models.SubscriptionResponse
	listError          error
}

func (m *mockSubscriptionManager) SubscribeToMarketData(streamID, symbol string, streams []string) (*models.SubscriptionResponse, error) {
	if m.subscribeError != nil {
		return nil, m.subscribeError
	}
	return m.subscribeResponse, nil
}

func (m *mockSubscriptionManager) SubscribeToUserData(streamID, listenKey string) (*models.SubscriptionResponse, error) {
	if m.userDataError != nil {
		return nil, m.userDataError
	}
	return m.userDataResponse, nil
}

func (m *mockSubscriptionManager) Unsubscribe(streamID string, req models.UnsubscribeRequest) (*models.SubscriptionResponse, error) {
	if m.unsubscribeError != nil {
		return nil, m.unsubscribeError
	}
	return &models.SubscriptionResponse{Success: m.unsubscribeSuccess}, nil
}

func (m *mockSubscriptionManager) ListSubscriptions(streamID string) ([]models.SubscriptionResponse, error) {
	if m.listError != nil {
		return nil, m.listError
	}
	return m.listResponse, nil
}