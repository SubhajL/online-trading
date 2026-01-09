package api

import (
	"math"
	"sort"
	"strings"
	"time"

	"github.com/shopspring/decimal"
)

// OrderExecutionRow represents a single order's execution data for quality calculation
type OrderExecutionRow struct {
	Side             string
	ExpectedPrice    decimal.Decimal
	AverageFillPrice decimal.Decimal
	Status           string
	DecisionTs       *time.Time
	RouterReceivedTs *time.Time
	RouterSentTs     *time.Time
	ExchangeAckTs    *time.Time
	FirstFillTs      *time.Time
	FilledTs         *time.Time
}

// SideSignedSlippageBps calculates slippage in basis points with sign convention.
// For BUY, higher actual price is worse (positive slippage).
// For SELL, lower actual price is worse (positive slippage).
// Unknown sides are treated as BUY for safety (conservative estimate).
func SideSignedSlippageBps(side string, expectedPrice, actualPrice decimal.Decimal) float64 {
	if expectedPrice.IsZero() {
		return 0
	}

	diff := actualPrice.Sub(expectedPrice)
	relDiff := diff.Div(expectedPrice).Mul(decimal.NewFromInt(10000))

	slippage, _ := relDiff.Float64()

	normalizedSide := strings.ToUpper(side)
	if normalizedSide == "BUY" {
		return slippage
	}
	if normalizedSide == "SELL" {
		return -slippage
	}
	// Unknown side: treat as BUY (conservative)
	return slippage
}

// CalculatePercentile calculates the p-th percentile from a sorted slice of values.
// Percentile should be between 0 and 100. Values outside this range are clamped.
func CalculatePercentile(values []float64, percentile float64) float64 {
	if len(values) == 0 {
		return 0
	}

	// Clamp percentile to valid range
	if percentile < 0 {
		percentile = 0
	}
	if percentile > 100 {
		percentile = 100
	}

	sorted := make([]float64, len(values))
	copy(sorted, values)
	sort.Float64s(sorted)

	n := float64(len(sorted))
	rank := (percentile / 100) * (n - 1)

	lower := int(math.Floor(rank))
	upper := int(math.Ceil(rank))

	if lower == upper || upper >= len(sorted) {
		return sorted[lower]
	}

	weight := rank - float64(lower)
	return sorted[lower]*(1-weight) + sorted[upper]*weight
}

// ComputeExecutionQuality aggregates execution quality metrics from order rows.
func ComputeExecutionQuality(orders []OrderExecutionRow) ExecutionQuality {
	if len(orders) == 0 {
		return ExecutionQuality{}
	}

	totalOrders := len(orders)
	filledOrders := 0

	var engineToRouterLatencies []float64
	var routerToExchangeLatencies []float64
	var timeToFirstFillLatencies []float64
	var slippages []float64

	for _, order := range orders {
		if order.Status == "FILLED" {
			filledOrders++
		}

		// Engine to Router latency
		if order.DecisionTs != nil && order.RouterReceivedTs != nil {
			latencyMs := float64(order.RouterReceivedTs.Sub(*order.DecisionTs).Milliseconds())
			if latencyMs >= 0 {
				engineToRouterLatencies = append(engineToRouterLatencies, latencyMs)
			}
		}

		// Router to Exchange latency
		if order.RouterSentTs != nil && order.ExchangeAckTs != nil {
			latencyMs := float64(order.ExchangeAckTs.Sub(*order.RouterSentTs).Milliseconds())
			if latencyMs >= 0 {
				routerToExchangeLatencies = append(routerToExchangeLatencies, latencyMs)
			}
		}

		// Time to first fill
		if order.RouterSentTs != nil && order.FirstFillTs != nil {
			latencyMs := float64(order.FirstFillTs.Sub(*order.RouterSentTs).Milliseconds())
			if latencyMs >= 0 {
				timeToFirstFillLatencies = append(timeToFirstFillLatencies, latencyMs)
			}
		}

		// Slippage (only for filled orders with prices)
		if order.Status == "FILLED" && !order.ExpectedPrice.IsZero() && !order.AverageFillPrice.IsZero() {
			slippage := SideSignedSlippageBps(order.Side, order.ExpectedPrice, order.AverageFillPrice)
			slippages = append(slippages, slippage)
		}
	}

	result := ExecutionQuality{
		TotalOrders:  totalOrders,
		FilledOrders: filledOrders,
	}

	if totalOrders > 0 {
		result.FillRate = float64(filledOrders) / float64(totalOrders)
	}

	if len(engineToRouterLatencies) > 0 {
		result.EngineToRouterP50 = CalculatePercentile(engineToRouterLatencies, 50)
		result.EngineToRouterP95 = CalculatePercentile(engineToRouterLatencies, 95)
	}

	if len(routerToExchangeLatencies) > 0 {
		result.RouterToExchangeP50 = CalculatePercentile(routerToExchangeLatencies, 50)
		result.RouterToExchangeP95 = CalculatePercentile(routerToExchangeLatencies, 95)
	}

	if len(timeToFirstFillLatencies) > 0 {
		result.TimeToFirstFillP50 = CalculatePercentile(timeToFirstFillLatencies, 50)
		result.TimeToFirstFillP95 = CalculatePercentile(timeToFirstFillLatencies, 95)
	}

	if len(slippages) > 0 {
		// Calculate average
		var sum float64
		for _, s := range slippages {
			sum += s
		}
		result.AvgSlippageBps = sum / float64(len(slippages))

		// Calculate max (worst slippage by absolute value)
		maxAbsSlippage := math.Abs(slippages[0])
		for _, s := range slippages {
			absS := math.Abs(s)
			if absS > maxAbsSlippage {
				maxAbsSlippage = absS
			}
		}
		result.MaxSlippageBps = maxAbsSlippage

		// Calculate standard deviation
		if len(slippages) > 1 {
			var sumSqDiff float64
			for _, s := range slippages {
				diff := s - result.AvgSlippageBps
				sumSqDiff += diff * diff
			}
			result.SlippageStdDev = math.Sqrt(sumSqDiff / float64(len(slippages)))
		}
	}

	return result
}
