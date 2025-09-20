package handlers

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"router/internal/models"
)

// StreamManager interface for managing WebSocket streams
type StreamManager interface {
	CreateStream(streamType string, subscriptions []string) (*models.StreamResponse, error)
	GetStream(id string) (*models.StreamResponse, error)
	ListStreams(filterType string, page, limit int) ([]models.StreamResponse, int, error)
	CloseStream(id string) error
	ReconnectStream(id string) (*models.StreamResponse, error)
}

// StreamHandlers contains handlers for stream management
type StreamHandlers struct {
	manager StreamManager
}

// NewStreamHandlers creates new stream handlers
func NewStreamHandlers(manager StreamManager) *StreamHandlers {
	return &StreamHandlers{
		manager: manager,
	}
}

// CreateStream creates a new WebSocket stream connection
func (h *StreamHandlers) CreateStream() gin.HandlerFunc {
	return func(c *gin.Context) {
		var req models.CreateStreamRequest
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

		// Extract subscriptions based on type
		var subscriptions []string
		if req.Type == "public" && len(req.Subscriptions) > 0 {
			subscriptions = req.Subscriptions
		}

		// Create stream
		stream, err := h.manager.CreateStream(req.Type, subscriptions)
		if err != nil {
			if strings.Contains(err.Error(), "connection failed") {
				c.JSON(http.StatusServiceUnavailable, models.NewErrorResponse(
					"CONNECTION_ERROR",
					"Failed to establish stream connection",
					c.GetString("request_id"),
				))
				return
			}

			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"STREAM_ERROR",
				"Failed to create stream",
				c.GetString("request_id"),
			))
			return
		}

		c.JSON(http.StatusCreated, stream)
	}
}

// GetStream retrieves details of a specific stream
func (h *StreamHandlers) GetStream() gin.HandlerFunc {
	return func(c *gin.Context) {
		streamID := c.Param("id")

		stream, err := h.manager.GetStream(streamID)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				c.JSON(http.StatusNotFound, models.NewErrorResponse(
					"NOT_FOUND",
					"Stream not found",
					c.GetString("request_id"),
				))
				return
			}

			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"STREAM_ERROR",
				"Failed to retrieve stream",
				c.GetString("request_id"),
			))
			return
		}

		c.JSON(http.StatusOK, stream)
	}
}

// ListStreams returns a list of active streams
func (h *StreamHandlers) ListStreams() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Parse query parameters
		page := 1
		limit := 10
		filterType := c.Query("type")

		if pageStr := c.Query("page"); pageStr != "" {
			if p, err := strconv.Atoi(pageStr); err == nil && p > 0 {
				page = p
			}
		}

		if limitStr := c.Query("limit"); limitStr != "" {
			if l, err := strconv.Atoi(limitStr); err == nil && l > 0 && l <= 100 {
				limit = l
			}
		}

		// Get streams
		streams, total, err := h.manager.ListStreams(filterType, page, limit)
		if err != nil {
			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"STREAM_ERROR",
				"Failed to list streams",
				c.GetString("request_id"),
			))
			return
		}

		response := models.NewListResponse(streams, len(streams), total, page, limit)
		c.JSON(http.StatusOK, response)
	}
}

// CloseStream closes an active stream connection
func (h *StreamHandlers) CloseStream() gin.HandlerFunc {
	return func(c *gin.Context) {
		streamID := c.Param("id")

		err := h.manager.CloseStream(streamID)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				c.JSON(http.StatusNotFound, models.NewErrorResponse(
					"NOT_FOUND",
					"Stream not found",
					c.GetString("request_id"),
				))
				return
			}

			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"STREAM_ERROR",
				"Failed to close stream",
				c.GetString("request_id"),
			))
			return
		}

		c.Status(http.StatusNoContent)
	}
}

// ReconnectStream attempts to reconnect a disconnected stream
func (h *StreamHandlers) ReconnectStream() gin.HandlerFunc {
	return func(c *gin.Context) {
		streamID := c.Param("id")

		stream, err := h.manager.ReconnectStream(streamID)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				c.JSON(http.StatusNotFound, models.NewErrorResponse(
					"NOT_FOUND",
					"Stream not found",
					c.GetString("request_id"),
				))
				return
			}

			if strings.Contains(err.Error(), "connection failed") {
				c.JSON(http.StatusServiceUnavailable, models.NewErrorResponse(
					"CONNECTION_ERROR",
					"Failed to reconnect stream",
					c.GetString("request_id"),
				))
				return
			}

			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"STREAM_ERROR",
				"Failed to reconnect stream",
				c.GetString("request_id"),
			))
			return
		}

		c.JSON(http.StatusOK, stream)
	}
}
