package api

import (
	"math"
	"testing"
	"time"

	"github.com/shopspring/decimal"
)

func TestSideSignedSlippageBps_BuyHigherActualIsPositive(t *testing.T) {
	expectedPrice := decimal.NewFromFloat(50000)
	actualPrice := decimal.NewFromFloat(50050)

	slippage := SideSignedSlippageBps("BUY", expectedPrice, actualPrice)

	if slippage <= 0 {
		t.Errorf("Expected positive slippage for BUY with higher actual, got %f", slippage)
	}
	expectedBps := 10.0 // 50/50000 * 10000 = 10 bps
	if math.Abs(slippage-expectedBps) > 0.01 {
		t.Errorf("Expected slippage ~%f bps, got %f", expectedBps, slippage)
	}
}

func TestSideSignedSlippageBps_SellLowerActualIsPositive(t *testing.T) {
	expectedPrice := decimal.NewFromFloat(50000)
	actualPrice := decimal.NewFromFloat(49950)

	slippage := SideSignedSlippageBps("SELL", expectedPrice, actualPrice)

	if slippage <= 0 {
		t.Errorf("Expected positive slippage for SELL with lower actual, got %f", slippage)
	}
	expectedBps := 10.0 // 50/50000 * 10000 = 10 bps
	if math.Abs(slippage-expectedBps) > 0.01 {
		t.Errorf("Expected slippage ~%f bps, got %f", expectedBps, slippage)
	}
}

func TestSideSignedSlippageBps_ExactFillIsZero(t *testing.T) {
	expectedPrice := decimal.NewFromFloat(50000)
	actualPrice := decimal.NewFromFloat(50000)

	slippageBuy := SideSignedSlippageBps("BUY", expectedPrice, actualPrice)
	slippageSell := SideSignedSlippageBps("SELL", expectedPrice, actualPrice)

	if slippageBuy != 0 {
		t.Errorf("Expected zero slippage for BUY with exact fill, got %f", slippageBuy)
	}
	if slippageSell != 0 {
		t.Errorf("Expected zero slippage for SELL with exact fill, got %f", slippageSell)
	}
}

func TestSideSignedSlippageBps_ZeroExpectedReturnsZero(t *testing.T) {
	expectedPrice := decimal.Zero
	actualPrice := decimal.NewFromFloat(50000)

	slippage := SideSignedSlippageBps("BUY", expectedPrice, actualPrice)

	if slippage != 0 {
		t.Errorf("Expected zero slippage for zero expected price, got %f", slippage)
	}
}

func TestCalculatePercentile_P50_EvenCount(t *testing.T) {
	values := []float64{10, 20, 30, 40}

	p50 := CalculatePercentile(values, 50)

	expected := 25.0 // Interpolation between 20 and 30
	if math.Abs(p50-expected) > 0.01 {
		t.Errorf("Expected P50 = %f, got %f", expected, p50)
	}
}

func TestCalculatePercentile_P50_OddCount(t *testing.T) {
	values := []float64{10, 20, 30, 40, 50}

	p50 := CalculatePercentile(values, 50)

	expected := 30.0
	if math.Abs(p50-expected) > 0.01 {
		t.Errorf("Expected P50 = %f, got %f", expected, p50)
	}
}

func TestCalculatePercentile_P95_SmallSample(t *testing.T) {
	values := []float64{100, 200, 300, 400, 500}

	p95 := CalculatePercentile(values, 95)

	// For 5 values, P95 should be close to the max
	if p95 < 400 || p95 > 500 {
		t.Errorf("Expected P95 between 400 and 500, got %f", p95)
	}
}

func TestCalculatePercentile_EmptySlice(t *testing.T) {
	values := []float64{}

	p50 := CalculatePercentile(values, 50)

	if p50 != 0 {
		t.Errorf("Expected 0 for empty slice, got %f", p50)
	}
}

func TestCalculatePercentile_SingleValue(t *testing.T) {
	values := []float64{42}

	p50 := CalculatePercentile(values, 50)
	p95 := CalculatePercentile(values, 95)

	if p50 != 42 {
		t.Errorf("Expected P50 = 42, got %f", p50)
	}
	if p95 != 42 {
		t.Errorf("Expected P95 = 42, got %f", p95)
	}
}

func TestComputeExecutionQuality_CalculatesLatencyPercentiles(t *testing.T) {
	baseTime := time.Date(2025, 1, 1, 12, 0, 0, 0, time.UTC)
	decisionTs := baseTime
	routerReceivedTs := baseTime.Add(50 * time.Millisecond)
	routerSentTs := baseTime.Add(60 * time.Millisecond)
	exchangeAckTs := baseTime.Add(100 * time.Millisecond)
	firstFillTs := baseTime.Add(150 * time.Millisecond)

	orders := []OrderExecutionRow{
		{
			Side:             "BUY",
			ExpectedPrice:    decimal.NewFromFloat(50000),
			AverageFillPrice: decimal.NewFromFloat(50010),
			Status:           "FILLED",
			DecisionTs:       &decisionTs,
			RouterReceivedTs: &routerReceivedTs,
			RouterSentTs:     &routerSentTs,
			ExchangeAckTs:    &exchangeAckTs,
			FirstFillTs:      &firstFillTs,
		},
	}

	result := ComputeExecutionQuality(orders)

	// Engine to router: 50ms
	if math.Abs(result.EngineToRouterP50-50) > 1 {
		t.Errorf("Expected EngineToRouterP50 ~50ms, got %f", result.EngineToRouterP50)
	}

	// Router to exchange: 40ms (100 - 60)
	if math.Abs(result.RouterToExchangeP50-40) > 1 {
		t.Errorf("Expected RouterToExchangeP50 ~40ms, got %f", result.RouterToExchangeP50)
	}

	// Time to first fill: 90ms (150 - 60)
	if math.Abs(result.TimeToFirstFillP50-90) > 1 {
		t.Errorf("Expected TimeToFirstFillP50 ~90ms, got %f", result.TimeToFirstFillP50)
	}
}

func TestComputeExecutionQuality_CalculatesSlippageStats(t *testing.T) {
	baseTime := time.Date(2025, 1, 1, 12, 0, 0, 0, time.UTC)
	orders := []OrderExecutionRow{
		{
			Side:             "BUY",
			ExpectedPrice:    decimal.NewFromFloat(50000),
			AverageFillPrice: decimal.NewFromFloat(50010), // 2 bps slippage
			Status:           "FILLED",
			DecisionTs:       &baseTime,
		},
		{
			Side:             "BUY",
			ExpectedPrice:    decimal.NewFromFloat(50000),
			AverageFillPrice: decimal.NewFromFloat(50020), // 4 bps slippage
			Status:           "FILLED",
			DecisionTs:       &baseTime,
		},
		{
			Side:             "BUY",
			ExpectedPrice:    decimal.NewFromFloat(50000),
			AverageFillPrice: decimal.NewFromFloat(50030), // 6 bps slippage
			Status:           "FILLED",
			DecisionTs:       &baseTime,
		},
	}

	result := ComputeExecutionQuality(orders)

	// Average slippage should be (2 + 4 + 6) / 3 = 4 bps
	if math.Abs(result.AvgSlippageBps-4) > 0.1 {
		t.Errorf("Expected AvgSlippageBps ~4, got %f", result.AvgSlippageBps)
	}

	// Max slippage (by absolute value) should be 6 bps
	if math.Abs(result.MaxSlippageBps-6) > 0.1 {
		t.Errorf("Expected MaxSlippageBps ~6, got %f", result.MaxSlippageBps)
	}

	// StdDev should be around 1.63 (std of [2,4,6])
	if result.SlippageStdDev < 1 || result.SlippageStdDev > 2.5 {
		t.Errorf("Expected SlippageStdDev ~1.63, got %f", result.SlippageStdDev)
	}
}

func TestSideSignedSlippageBps_LowercaseSideNormalized(t *testing.T) {
	expectedPrice := decimal.NewFromFloat(50000)
	actualPrice := decimal.NewFromFloat(50050)

	// lowercase "buy" should work like "BUY"
	slippage := SideSignedSlippageBps("buy", expectedPrice, actualPrice)
	expectedBps := 10.0
	if math.Abs(slippage-expectedBps) > 0.01 {
		t.Errorf("Expected slippage ~%f bps for lowercase 'buy', got %f", expectedBps, slippage)
	}

	// lowercase "sell" should work like "SELL"
	slippageSell := SideSignedSlippageBps("sell", expectedPrice, actualPrice)
	if slippageSell >= 0 {
		t.Errorf("Expected negative slippage for lowercase 'sell' with higher actual, got %f", slippageSell)
	}
}

func TestComputeExecutionQuality_HandlesSingleOrder(t *testing.T) {
	baseTime := time.Date(2025, 1, 1, 12, 0, 0, 0, time.UTC)
	orders := []OrderExecutionRow{
		{
			Side:             "BUY",
			ExpectedPrice:    decimal.NewFromFloat(50000),
			AverageFillPrice: decimal.NewFromFloat(50010),
			Status:           "FILLED",
			DecisionTs:       &baseTime,
		},
	}

	result := ComputeExecutionQuality(orders)

	if result.TotalOrders != 1 {
		t.Errorf("Expected TotalOrders = 1, got %d", result.TotalOrders)
	}
	if result.FilledOrders != 1 {
		t.Errorf("Expected FilledOrders = 1, got %d", result.FilledOrders)
	}
	if result.FillRate != 1.0 {
		t.Errorf("Expected FillRate = 1.0, got %f", result.FillRate)
	}
	// Single order means avg = value, max = value, stddev = 0
	if result.SlippageStdDev != 0 {
		t.Errorf("Expected SlippageStdDev = 0 for single order, got %f", result.SlippageStdDev)
	}
}

func TestComputeExecutionQuality_HandlesEmptyOrders(t *testing.T) {
	orders := []OrderExecutionRow{}

	result := ComputeExecutionQuality(orders)

	if result.TotalOrders != 0 {
		t.Errorf("Expected TotalOrders = 0, got %d", result.TotalOrders)
	}
	if result.FilledOrders != 0 {
		t.Errorf("Expected FilledOrders = 0, got %d", result.FilledOrders)
	}
	if result.FillRate != 0 {
		t.Errorf("Expected FillRate = 0, got %f", result.FillRate)
	}
}

func TestComputeExecutionQuality_CalculatesFillRate(t *testing.T) {
	baseTime := time.Date(2025, 1, 1, 12, 0, 0, 0, time.UTC)
	orders := []OrderExecutionRow{
		{Status: "FILLED", DecisionTs: &baseTime, ExpectedPrice: decimal.NewFromFloat(100), AverageFillPrice: decimal.NewFromFloat(100)},
		{Status: "FILLED", DecisionTs: &baseTime, ExpectedPrice: decimal.NewFromFloat(100), AverageFillPrice: decimal.NewFromFloat(100)},
		{Status: "NEW", DecisionTs: &baseTime},
		{Status: "CANCELED", DecisionTs: &baseTime},
	}

	result := ComputeExecutionQuality(orders)

	if result.TotalOrders != 4 {
		t.Errorf("Expected TotalOrders = 4, got %d", result.TotalOrders)
	}
	if result.FilledOrders != 2 {
		t.Errorf("Expected FilledOrders = 2, got %d", result.FilledOrders)
	}
	if result.FillRate != 0.5 {
		t.Errorf("Expected FillRate = 0.5, got %f", result.FillRate)
	}
}
