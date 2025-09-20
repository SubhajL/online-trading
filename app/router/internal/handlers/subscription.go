package handlers

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"router/internal/models"
)

// SubscriptionManager interface for managing stream subscriptions
type SubscriptionManager interface {
	SubscribeToMarketData(streamID, symbol string, streams []string) (*models.SubscriptionResponse, error)
	SubscribeToUserData(streamID, listenKey string) (*models.SubscriptionResponse, error)
	Unsubscribe(streamID string, req models.UnsubscribeRequest) (*models.SubscriptionResponse, error)
	ListSubscriptions(streamID string) ([]models.SubscriptionResponse, error)
}

// SubscriptionHandlers contains handlers for subscription management
type SubscriptionHandlers struct {
	manager SubscriptionManager
}

// NewSubscriptionHandlers creates new subscription handlers
func NewSubscriptionHandlers(manager SubscriptionManager) *SubscriptionHandlers {
	return &SubscriptionHandlers{
		manager: manager,
	}
}

// SubscribeToMarketData subscribes to market data streams
func (h *SubscriptionHandlers) SubscribeToMarketData() gin.HandlerFunc {
	return func(c *gin.Context) {
		streamID := c.Param("id")

		var req models.SubscribeRequest
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

		// Normalize request
		req.Normalize()

		// Subscribe to market data
		resp, err := h.manager.SubscribeToMarketData(streamID, req.Symbol, req.Streams)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				c.JSON(http.StatusNotFound, models.NewErrorResponse(
					"NOT_FOUND",
					"Stream not found",
					c.GetString("request_id"),
				))
				return
			}

			if strings.Contains(err.Error(), "already subscribed") {
				c.JSON(http.StatusConflict, models.NewErrorResponse(
					"ALREADY_SUBSCRIBED",
					"Already subscribed to these streams",
					c.GetString("request_id"),
				))
				return
			}

			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"SUBSCRIPTION_ERROR",
				"Failed to subscribe to market data",
				c.GetString("request_id"),
			))
			return
		}

		c.JSON(http.StatusOK, resp)
	}
}

// SubscribeToUserData subscribes to user data stream
func (h *SubscriptionHandlers) SubscribeToUserData() gin.HandlerFunc {
	return func(c *gin.Context) {
		streamID := c.Param("id")

		var req models.UserDataRequest
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

		// Subscribe to user data
		resp, err := h.manager.SubscribeToUserData(streamID, req.ListenKey)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				c.JSON(http.StatusNotFound, models.NewErrorResponse(
					"NOT_FOUND",
					"Stream not found",
					c.GetString("request_id"),
				))
				return
			}

			if strings.Contains(err.Error(), "invalid listen key") {
				c.JSON(http.StatusUnauthorized, models.NewErrorResponse(
					"INVALID_LISTEN_KEY",
					"Invalid or expired listen key",
					c.GetString("request_id"),
				))
				return
			}

			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"SUBSCRIPTION_ERROR",
				"Failed to subscribe to user data",
				c.GetString("request_id"),
			))
			return
		}

		c.JSON(http.StatusOK, resp)
	}
}

// Unsubscribe removes subscriptions from a stream
func (h *SubscriptionHandlers) Unsubscribe() gin.HandlerFunc {
	return func(c *gin.Context) {
		streamID := c.Param("id")

		var req models.UnsubscribeRequest
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

		// Unsubscribe
		resp, err := h.manager.Unsubscribe(streamID, req)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				c.JSON(http.StatusNotFound, models.NewErrorResponse(
					"NOT_FOUND",
					"Subscription not found",
					c.GetString("request_id"),
				))
				return
			}

			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"SUBSCRIPTION_ERROR",
				"Failed to unsubscribe",
				c.GetString("request_id"),
			))
			return
		}

		c.JSON(http.StatusOK, resp)
	}
}

// ListSubscriptions returns all active subscriptions for a stream
func (h *SubscriptionHandlers) ListSubscriptions() gin.HandlerFunc {
	return func(c *gin.Context) {
		streamID := c.Param("id")

		subscriptions, err := h.manager.ListSubscriptions(streamID)
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
				"SUBSCRIPTION_ERROR",
				"Failed to list subscriptions",
				c.GetString("request_id"),
			))
			return
		}

		// Return empty array if no subscriptions
		if subscriptions == nil {
			subscriptions = []models.SubscriptionResponse{}
		}

		c.JSON(http.StatusOK, subscriptions)
	}
}
