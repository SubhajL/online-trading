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

func TestCreateStream(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("creates public stream successfully", func(t *testing.T) {
		manager := &mockStreamManager{
			createResponse: &models.StreamResponse{
				ID:        "stream-123",
				Type:      "public",
				Status:    "connected",
				CreatedAt: time.Now(),
			},
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.POST("/streams", handler.CreateStream())

		reqBody := models.CreateStreamRequest{
			Type:          "public",
			Subscriptions: []string{"btcusdt@ticker"},
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusCreated, w.Code)

		var resp models.StreamResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, "stream-123", resp.ID)
		assert.Equal(t, "public", resp.Type)
	})

	t.Run("creates user data stream successfully", func(t *testing.T) {
		manager := &mockStreamManager{
			createResponse: &models.StreamResponse{
				ID:        "user-stream-456",
				Type:      "user",
				Status:    "connected",
				CreatedAt: time.Now(),
			},
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.POST("/streams", handler.CreateStream())

		reqBody := models.CreateStreamRequest{
			Type: "user",
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusCreated, w.Code)

		var resp models.StreamResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, "user", resp.Type)
	})

	t.Run("returns 400 for invalid request", func(t *testing.T) {
		manager := &mockStreamManager{}
		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.POST("/streams", handler.CreateStream())

		reqBody := models.CreateStreamRequest{
			Type: "invalid",
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusBadRequest, w.Code)

		var resp models.ErrorResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, "VALIDATION_ERROR", resp.Error)
	})

	t.Run("returns 503 when stream creation fails", func(t *testing.T) {
		manager := &mockStreamManager{
			createError: errors.New("connection failed"),
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.POST("/streams", handler.CreateStream())

		reqBody := models.CreateStreamRequest{
			Type: "public",
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("POST", "/streams", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusServiceUnavailable, w.Code)
	})
}

func TestGetStream(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("returns stream details successfully", func(t *testing.T) {
		manager := &mockStreamManager{
			getResponse: &models.StreamResponse{
				ID:            "stream-123",
				Type:          "public",
				Status:        "connected",
				CreatedAt:     time.Now(),
				Subscriptions: []string{"btcusdt@ticker", "ethusdt@depth"},
				Metrics: &models.StreamMetrics{
					MessagesReceived: 1000,
					MessagesSent:     50,
					BytesReceived:    100000,
					BytesSent:        5000,
					ConnectedSince:   time.Now().Add(-1 * time.Hour),
					LastActivity:     time.Now(),
				},
			},
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.GET("/streams/:id", handler.GetStream())

		req := httptest.NewRequest("GET", "/streams/stream-123", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.StreamResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, "stream-123", resp.ID)
		assert.Len(t, resp.Subscriptions, 2)
		assert.NotNil(t, resp.Metrics)
	})

	t.Run("returns 404 for non-existent stream", func(t *testing.T) {
		manager := &mockStreamManager{
			getError: errors.New("stream not found"),
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.GET("/streams/:id", handler.GetStream())

		req := httptest.NewRequest("GET", "/streams/invalid-id", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusNotFound, w.Code)

		var resp models.ErrorResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, "NOT_FOUND", resp.Error)
	})
}

func TestListStreams(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("returns list of streams with pagination", func(t *testing.T) {
		streams := []models.StreamResponse{
			{ID: "stream-1", Type: "public", Status: "connected"},
			{ID: "stream-2", Type: "public", Status: "connected"},
			{ID: "stream-3", Type: "user", Status: "connected"},
		}

		manager := &mockStreamManager{
			listResponse: streams,
			totalCount:   10,
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.GET("/streams", handler.ListStreams())

		req := httptest.NewRequest("GET", "/streams?page=1&limit=3", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.ListResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, 3, resp.Count)
		assert.Equal(t, 10, resp.Total)
		assert.Equal(t, 1, resp.Page)
		assert.Equal(t, 3, resp.PageSize)
	})

	t.Run("filters streams by type", func(t *testing.T) {
		publicStreams := []models.StreamResponse{
			{ID: "stream-1", Type: "public", Status: "connected"},
			{ID: "stream-2", Type: "public", Status: "connected"},
		}

		manager := &mockStreamManager{
			listResponse: publicStreams,
			totalCount:   2,
			filterType:   "public",
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.GET("/streams", handler.ListStreams())

		req := httptest.NewRequest("GET", "/streams?type=public", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.ListResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, 2, resp.Count)
	})

	t.Run("uses default pagination values", func(t *testing.T) {
		manager := &mockStreamManager{
			listResponse: []models.StreamResponse{},
			totalCount:   0,
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.GET("/streams", handler.ListStreams())

		req := httptest.NewRequest("GET", "/streams", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.ListResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, 1, resp.Page)
		assert.Equal(t, 10, resp.PageSize)
	})
}

func TestCloseStream(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("closes stream successfully", func(t *testing.T) {
		manager := &mockStreamManager{
			closeSuccess: true,
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.DELETE("/streams/:id", handler.CloseStream())

		req := httptest.NewRequest("DELETE", "/streams/stream-123", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusNoContent, w.Code)
		assert.Equal(t, "stream-123", manager.closedStreamID)
	})

	t.Run("returns 404 for non-existent stream", func(t *testing.T) {
		manager := &mockStreamManager{
			closeError: errors.New("stream not found"),
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.DELETE("/streams/:id", handler.CloseStream())

		req := httptest.NewRequest("DELETE", "/streams/invalid-id", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusNotFound, w.Code)
	})

	t.Run("returns 500 for unexpected errors", func(t *testing.T) {
		manager := &mockStreamManager{
			closeError: errors.New("internal error"),
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.DELETE("/streams/:id", handler.CloseStream())

		req := httptest.NewRequest("DELETE", "/streams/stream-123", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusInternalServerError, w.Code)
	})
}

func TestReconnectStream(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("reconnects stream successfully", func(t *testing.T) {
		manager := &mockStreamManager{
			reconnectResponse: &models.StreamResponse{
				ID:        "stream-123",
				Type:      "public",
				Status:    "connected",
				CreatedAt: time.Now(),
			},
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/reconnect", handler.ReconnectStream())

		req := httptest.NewRequest("POST", "/streams/stream-123/reconnect", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.StreamResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, "connected", resp.Status)
	})

	t.Run("returns 404 for non-existent stream", func(t *testing.T) {
		manager := &mockStreamManager{
			reconnectError: errors.New("stream not found"),
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/reconnect", handler.ReconnectStream())

		req := httptest.NewRequest("POST", "/streams/invalid-id/reconnect", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusNotFound, w.Code)
	})

	t.Run("returns 503 when reconnection fails", func(t *testing.T) {
		manager := &mockStreamManager{
			reconnectError: errors.New("connection failed"),
		}

		handler := NewStreamHandlers(manager)
		router := gin.New()
		router.POST("/streams/:id/reconnect", handler.ReconnectStream())

		req := httptest.NewRequest("POST", "/streams/stream-123/reconnect", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusServiceUnavailable, w.Code)
	})
}

// Mock stream manager for testing
type mockStreamManager struct {
	createResponse    *models.StreamResponse
	createError       error
	getResponse       *models.StreamResponse
	getError          error
	listResponse      []models.StreamResponse
	totalCount        int
	filterType        string
	closeSuccess      bool
	closeError        error
	closedStreamID    string
	reconnectResponse *models.StreamResponse
	reconnectError    error
}

func (m *mockStreamManager) CreateStream(streamType string, subscriptions []string) (*models.StreamResponse, error) {
	if m.createError != nil {
		return nil, m.createError
	}
	return m.createResponse, nil
}

func (m *mockStreamManager) GetStream(id string) (*models.StreamResponse, error) {
	if m.getError != nil {
		return nil, m.getError
	}
	return m.getResponse, nil
}

func (m *mockStreamManager) ListStreams(filterType string, page, limit int) ([]models.StreamResponse, int, error) {
	m.filterType = filterType
	return m.listResponse, m.totalCount, nil
}

func (m *mockStreamManager) CloseStream(id string) error {
	m.closedStreamID = id
	return m.closeError
}

func (m *mockStreamManager) ReconnectStream(id string) (*models.StreamResponse, error) {
	if m.reconnectError != nil {
		return nil, m.reconnectError
	}
	return m.reconnectResponse, nil
}
