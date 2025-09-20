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

func TestGetConfig(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("returns current configuration", func(t *testing.T) {
		manager := &mockConfigManager{
			config: &models.ConfigResponse{
				RateLimit:      100,
				MaxConnections: 10,
				UpdatedAt:      time.Now(),
			},
		}

		handler := NewAdminHandlers(manager)
		router := gin.New()
		router.GET("/admin/config", handler.GetConfig())

		req := httptest.NewRequest("GET", "/admin/config", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.ConfigResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, 100, resp.RateLimit)
		assert.Equal(t, 10, resp.MaxConnections)
	})

	t.Run("returns 500 on error", func(t *testing.T) {
		manager := &mockConfigManager{
			getError: errors.New("config error"),
		}

		handler := NewAdminHandlers(manager)
		router := gin.New()
		router.GET("/admin/config", handler.GetConfig())

		req := httptest.NewRequest("GET", "/admin/config", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusInternalServerError, w.Code)
	})
}

func TestUpdateConfig(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("updates configuration successfully", func(t *testing.T) {
		manager := &mockConfigManager{
			updatedConfig: &models.ConfigResponse{
				RateLimit:      200,
				MaxConnections: 20,
				UpdatedAt:      time.Now(),
			},
		}

		handler := NewAdminHandlers(manager)
		router := gin.New()
		router.PUT("/admin/config", handler.UpdateConfig())

		rateLimit := 200
		maxConn := 20
		reqBody := models.ConfigUpdateRequest{
			RateLimit:      &rateLimit,
			MaxConnections: &maxConn,
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("PUT", "/admin/config", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.ConfigResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, 200, resp.RateLimit)
		assert.Equal(t, 20, resp.MaxConnections)
	})

	t.Run("returns 400 for invalid values", func(t *testing.T) {
		manager := &mockConfigManager{}
		handler := NewAdminHandlers(manager)
		router := gin.New()
		router.PUT("/admin/config", handler.UpdateConfig())

		invalidRate := -1
		reqBody := models.ConfigUpdateRequest{
			RateLimit: &invalidRate,
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("PUT", "/admin/config", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusBadRequest, w.Code)
	})

	t.Run("allows partial updates", func(t *testing.T) {
		manager := &mockConfigManager{
			updatedConfig: &models.ConfigResponse{
				RateLimit:      150,
				MaxConnections: 10, // Unchanged
				UpdatedAt:      time.Now(),
			},
		}

		handler := NewAdminHandlers(manager)
		router := gin.New()
		router.PUT("/admin/config", handler.UpdateConfig())

		rateLimit := 150
		reqBody := models.ConfigUpdateRequest{
			RateLimit: &rateLimit,
			// MaxConnections not provided
		}
		body, _ := json.Marshal(reqBody)

		req := httptest.NewRequest("PUT", "/admin/config", bytes.NewBuffer(body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.ConfigResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, 150, resp.RateLimit)
	})
}

func TestGetStreamStats(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("returns stream statistics", func(t *testing.T) {
		stats := map[string]interface{}{
			"total_streams":      5,
			"active_streams":     3,
			"total_connections":  10,
			"messages_processed": 100000,
			"uptime_seconds":     3600,
		}

		manager := &mockConfigManager{
			stats: stats,
		}

		handler := NewAdminHandlers(manager)
		router := gin.New()
		router.GET("/admin/stats", handler.GetStreamStats())

		req := httptest.NewRequest("GET", "/admin/stats", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp map[string]interface{}
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, float64(5), resp["total_streams"])
		assert.Equal(t, float64(3), resp["active_streams"])
	})

	t.Run("returns empty stats when none available", func(t *testing.T) {
		manager := &mockConfigManager{
			stats: map[string]interface{}{},
		}

		handler := NewAdminHandlers(manager)
		router := gin.New()
		router.GET("/admin/stats", handler.GetStreamStats())

		req := httptest.NewRequest("GET", "/admin/stats", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp map[string]interface{}
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Empty(t, resp)
	})
}

func TestResetStats(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("resets statistics successfully", func(t *testing.T) {
		manager := &mockConfigManager{
			resetSuccess: true,
		}

		handler := NewAdminHandlers(manager)
		router := gin.New()
		router.POST("/admin/stats/reset", handler.ResetStats())

		req := httptest.NewRequest("POST", "/admin/stats/reset", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp map[string]interface{}
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, "Statistics reset successfully", resp["message"])
	})

	t.Run("returns 500 on reset failure", func(t *testing.T) {
		manager := &mockConfigManager{
			resetError: errors.New("reset failed"),
		}

		handler := NewAdminHandlers(manager)
		router := gin.New()
		router.POST("/admin/stats/reset", handler.ResetStats())

		req := httptest.NewRequest("POST", "/admin/stats/reset", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusInternalServerError, w.Code)
	})
}

func TestCloseAllStreams(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("closes all streams successfully", func(t *testing.T) {
		manager := &mockConfigManager{
			closedCount: 5,
		}

		handler := NewAdminHandlers(manager)
		router := gin.New()
		router.POST("/admin/streams/close-all", handler.CloseAllStreams())

		req := httptest.NewRequest("POST", "/admin/streams/close-all", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp map[string]interface{}
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, float64(5), resp["closed_count"])
		assert.Equal(t, "All streams closed successfully", resp["message"])
	})

	t.Run("returns success with zero streams closed", func(t *testing.T) {
		manager := &mockConfigManager{
			closedCount: 0,
		}

		handler := NewAdminHandlers(manager)
		router := gin.New()
		router.POST("/admin/streams/close-all", handler.CloseAllStreams())

		req := httptest.NewRequest("POST", "/admin/streams/close-all", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp map[string]interface{}
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, float64(0), resp["closed_count"])
	})

	t.Run("returns 500 on close failure", func(t *testing.T) {
		manager := &mockConfigManager{
			closeAllError: errors.New("failed to close streams"),
		}

		handler := NewAdminHandlers(manager)
		router := gin.New()
		router.POST("/admin/streams/close-all", handler.CloseAllStreams())

		req := httptest.NewRequest("POST", "/admin/streams/close-all", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusInternalServerError, w.Code)
	})
}

// Mock config manager for testing
type mockConfigManager struct {
	config        *models.ConfigResponse
	getError      error
	updatedConfig *models.ConfigResponse
	updateError   error
	stats         map[string]interface{}
	statsError    error
	resetSuccess  bool
	resetError    error
	closedCount   int
	closeAllError error
}

func (m *mockConfigManager) GetConfig() (*models.ConfigResponse, error) {
	if m.getError != nil {
		return nil, m.getError
	}
	return m.config, nil
}

func (m *mockConfigManager) UpdateConfig(req models.ConfigUpdateRequest) (*models.ConfigResponse, error) {
	if m.updateError != nil {
		return nil, m.updateError
	}
	return m.updatedConfig, nil
}

func (m *mockConfigManager) GetStreamStats() (map[string]interface{}, error) {
	if m.statsError != nil {
		return nil, m.statsError
	}
	return m.stats, nil
}

func (m *mockConfigManager) ResetStats() error {
	return m.resetError
}

func (m *mockConfigManager) CloseAllStreams() (int, error) {
	if m.closeAllError != nil {
		return 0, m.closeAllError
	}
	return m.closedCount, nil
}
