package handlers

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"router/internal/models"
)

// ConfigManager interface for managing configuration and admin operations
type ConfigManager interface {
	GetConfig() (*models.ConfigResponse, error)
	UpdateConfig(req models.ConfigUpdateRequest) (*models.ConfigResponse, error)
	GetStreamStats() (map[string]interface{}, error)
	ResetStats() error
	CloseAllStreams() (int, error)
}

// AdminHandlers contains handlers for administrative operations
type AdminHandlers struct {
	manager ConfigManager
}

// NewAdminHandlers creates new admin handlers
func NewAdminHandlers(manager ConfigManager) *AdminHandlers {
	return &AdminHandlers{
		manager: manager,
	}
}

// GetConfig returns the current configuration
func (h *AdminHandlers) GetConfig() gin.HandlerFunc {
	return func(c *gin.Context) {
		config, err := h.manager.GetConfig()
		if err != nil {
			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"CONFIG_ERROR",
				"Failed to retrieve configuration",
				c.GetString("request_id"),
			))
			return
		}

		c.JSON(http.StatusOK, config)
	}
}

// UpdateConfig updates the system configuration
func (h *AdminHandlers) UpdateConfig() gin.HandlerFunc {
	return func(c *gin.Context) {
		var req models.ConfigUpdateRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, models.NewErrorResponse(
				"VALIDATION_ERROR",
				"Invalid request body",
				c.GetString("request_id"),
			))
			return
		}

		// Validate request
		if err := req.Validate(); err != nil {
			c.JSON(http.StatusBadRequest, models.NewErrorResponse(
				"VALIDATION_ERROR",
				err.Error(),
				c.GetString("request_id"),
			))
			return
		}

		// Update configuration
		config, err := h.manager.UpdateConfig(req)
		if err != nil {
			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"CONFIG_ERROR",
				"Failed to update configuration",
				c.GetString("request_id"),
			))
			return
		}

		c.JSON(http.StatusOK, config)
	}
}

// GetStreamStats returns stream statistics
func (h *AdminHandlers) GetStreamStats() gin.HandlerFunc {
	return func(c *gin.Context) {
		stats, err := h.manager.GetStreamStats()
		if err != nil {
			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"STATS_ERROR",
				"Failed to retrieve statistics",
				c.GetString("request_id"),
			))
			return
		}

		// Return empty object if no stats available
		if stats == nil {
			stats = make(map[string]interface{})
		}

		c.JSON(http.StatusOK, stats)
	}
}

// ResetStats resets all statistics
func (h *AdminHandlers) ResetStats() gin.HandlerFunc {
	return func(c *gin.Context) {
		if err := h.manager.ResetStats(); err != nil {
			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"STATS_ERROR",
				"Failed to reset statistics",
				c.GetString("request_id"),
			))
			return
		}

		c.JSON(http.StatusOK, gin.H{
			"message": "Statistics reset successfully",
			"status":  "success",
		})
	}
}

// CloseAllStreams closes all active streams
func (h *AdminHandlers) CloseAllStreams() gin.HandlerFunc {
	return func(c *gin.Context) {
		count, err := h.manager.CloseAllStreams()
		if err != nil {
			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"STREAM_ERROR",
				"Failed to close all streams",
				c.GetString("request_id"),
			))
			return
		}

		c.JSON(http.StatusOK, gin.H{
			"message":      "All streams closed successfully",
			"closed_count": count,
			"status":       "success",
		})
	}
}
