package metrics

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNewCollector_InitializesCorrectly(t *testing.T) {
	collector := NewCollector()

	require.NotNil(t, collector)
	assert.NotNil(t, collector.requestCounter)
	assert.NotNil(t, collector.requestHistogram)
	assert.NotNil(t, collector.orderLatencyHist)
	assert.NotNil(t, collector.orderStatusCount)
	assert.NotNil(t, collector.wsConnectionCount)
	assert.NotNil(t, collector.wsEventCounter)
	assert.NotNil(t, collector.customHistograms)
	assert.NotNil(t, collector.customCounters)
	assert.Equal(t, DefaultLatencyBuckets, collector.histogramBuckets)
	assert.False(t, collector.startTime.IsZero())
}

func TestNewCollectorWithBuckets_UsesCustomBuckets(t *testing.T) {
	customBuckets := []float64{0.1, 0.5, 1.0, 2.0}
	collector := NewCollectorWithBuckets(customBuckets)

	require.NotNil(t, collector)
	assert.Equal(t, customBuckets, collector.histogramBuckets)
}

func TestRecordHTTPRequest_IncrementsCounter(t *testing.T) {
	collector := NewCollector()

	collector.RecordHTTPRequest("GET", "/api/orders", 200)
	collector.RecordHTTPRequest("GET", "/api/orders", 200)
	collector.RecordHTTPRequest("POST", "/api/orders", 201)

	snapshot := collector.GetSnapshot()

	// Find counters
	var getOrdersCount, postOrdersCount int64
	for _, counter := range snapshot.Counters {
		if counter.Name == "http_requests_total" {
			if counter.Labels["method"] == "GET" && counter.Labels["path"] == "/api/orders" && counter.Labels["status"] == "200" {
				getOrdersCount = counter.Value
			}
			if counter.Labels["method"] == "POST" && counter.Labels["path"] == "/api/orders" && counter.Labels["status"] == "201" {
				postOrdersCount = counter.Value
			}
		}
	}

	assert.Equal(t, int64(2), getOrdersCount)
	assert.Equal(t, int64(1), postOrdersCount)
}

func TestRecordHTTPDuration_AddsToHistogram(t *testing.T) {
	collector := NewCollector()

	collector.RecordHTTPDuration("GET", "/api/orders", 0.150)
	collector.RecordHTTPDuration("GET", "/api/orders", 0.025)
	collector.RecordHTTPDuration("POST", "/api/orders", 0.300)

	snapshot := collector.GetSnapshot()

	// Find histograms
	var getOrdersHist, postOrdersHist []float64
	for _, hist := range snapshot.Histograms {
		if hist.Name == "http_request_duration_seconds" {
			if hist.Labels["method"] == "GET" && hist.Labels["endpoint"] == "/api/orders" {
				getOrdersHist = append(getOrdersHist, hist.Value)
			}
			if hist.Labels["method"] == "POST" && hist.Labels["endpoint"] == "/api/orders" {
				postOrdersHist = append(postOrdersHist, hist.Value)
			}
		}
	}

	assert.Len(t, getOrdersHist, 2)
	assert.Contains(t, getOrdersHist, 0.150)
	assert.Contains(t, getOrdersHist, 0.025)
	assert.Len(t, postOrdersHist, 1)
	assert.Contains(t, postOrdersHist, 0.300)
}

func TestRecordOrderLatency_TracksOrderPerformance(t *testing.T) {
	collector := NewCollector()

	collector.RecordOrderLatency("binance", "spot", 0.250)
	collector.RecordOrderLatency("binance", "futures", 0.180)
	collector.RecordOrderLatency("binance", "spot", 0.320)

	snapshot := collector.GetSnapshot()

	var spotLatencies, futuresLatencies []float64
	for _, hist := range snapshot.Histograms {
		if hist.Name == "order_latency_seconds" {
			if hist.Labels["exchange"] == "binance" && hist.Labels["type"] == "spot" {
				spotLatencies = append(spotLatencies, hist.Value)
			}
			if hist.Labels["exchange"] == "binance" && hist.Labels["type"] == "futures" {
				futuresLatencies = append(futuresLatencies, hist.Value)
			}
		}
	}

	assert.Len(t, spotLatencies, 2)
	assert.Contains(t, spotLatencies, 0.250)
	assert.Contains(t, spotLatencies, 0.320)
	assert.Len(t, futuresLatencies, 1)
	assert.Contains(t, futuresLatencies, 0.180)
}

func TestRecordOrderStatus_CountsByStatus(t *testing.T) {
	collector := NewCollector()

	collector.RecordOrderStatus("binance", "filled")
	collector.RecordOrderStatus("binance", "filled")
	collector.RecordOrderStatus("binance", "cancelled")
	collector.RecordOrderStatus("binance", "rejected")

	snapshot := collector.GetSnapshot()

	var filledCount, cancelledCount, rejectedCount int64
	for _, counter := range snapshot.Counters {
		if counter.Name == "order_status_total" && counter.Labels["exchange"] == "binance" {
			switch counter.Labels["status"] {
			case "filled":
				filledCount = counter.Value
			case "cancelled":
				cancelledCount = counter.Value
			case "rejected":
				rejectedCount = counter.Value
			}
		}
	}

	assert.Equal(t, int64(2), filledCount)
	assert.Equal(t, int64(1), cancelledCount)
	assert.Equal(t, int64(1), rejectedCount)
}

func TestRecordWebSocketConnection_TracksConnections(t *testing.T) {
	collector := NewCollector()

	collector.RecordWebSocketConnection("connected")
	collector.RecordWebSocketConnection("connected")
	collector.RecordWebSocketConnection("disconnected")

	snapshot := collector.GetSnapshot()

	var connectedCount, disconnectedCount int64
	for _, counter := range snapshot.Counters {
		if counter.Name == "websocket_connections_total" {
			switch counter.Labels["status"] {
			case "connected":
				connectedCount = counter.Value
			case "disconnected":
				disconnectedCount = counter.Value
			}
		}
	}

	assert.Equal(t, int64(2), connectedCount)
	assert.Equal(t, int64(1), disconnectedCount)
}

func TestRecordWebSocketEvent_CountsEvents(t *testing.T) {
	collector := NewCollector()

	collector.RecordWebSocketEvent("depth_update")
	collector.RecordWebSocketEvent("depth_update")
	collector.RecordWebSocketEvent("trade")
	collector.RecordWebSocketEvent("ticker")

	snapshot := collector.GetSnapshot()

	var depthCount, tradeCount, tickerCount int64
	for _, counter := range snapshot.Counters {
		if counter.Name == "websocket_events_total" {
			switch counter.Labels["event_type"] {
			case "depth_update":
				depthCount = counter.Value
			case "trade":
				tradeCount = counter.Value
			case "ticker":
				tickerCount = counter.Value
			}
		}
	}

	assert.Equal(t, int64(2), depthCount)
	assert.Equal(t, int64(1), tradeCount)
	assert.Equal(t, int64(1), tickerCount)
}

func TestRecordCustomHistogram_AddsCustomMetric(t *testing.T) {
	collector := NewCollector()

	collector.RecordCustomHistogram("trade_volume", 1000.50)
	collector.RecordCustomHistogram("trade_volume", 2500.75)
	collector.RecordCustomHistogram("profit_loss", -150.25)

	snapshot := collector.GetSnapshot()

	var volumeValues, plValues []float64
	for _, hist := range snapshot.Histograms {
		switch hist.Name {
		case "trade_volume":
			volumeValues = append(volumeValues, hist.Value)
		case "profit_loss":
			plValues = append(plValues, hist.Value)
		}
	}

	assert.Len(t, volumeValues, 2)
	assert.Contains(t, volumeValues, 1000.50)
	assert.Contains(t, volumeValues, 2500.75)
	assert.Len(t, plValues, 1)
	assert.Contains(t, plValues, -150.25)
}

func TestRecordCustomCounter_IncrementsCustomCounter(t *testing.T) {
	collector := NewCollector()

	collector.RecordCustomCounter("api_calls")
	collector.RecordCustomCounter("api_calls")
	collector.RecordCustomCounter("errors")

	snapshot := collector.GetSnapshot()

	var apiCallsCount, errorsCount int64
	for _, counter := range snapshot.Counters {
		switch counter.Name {
		case "api_calls":
			apiCallsCount = counter.Value
		case "errors":
			errorsCount = counter.Value
		}
	}

	assert.Equal(t, int64(2), apiCallsCount)
	assert.Equal(t, int64(1), errorsCount)
}

func TestGetSnapshot_ThreadSafe(t *testing.T) {
	collector := NewCollector()

	// Run concurrent operations
	done := make(chan bool, 10)
	for i := 0; i < 10; i++ {
		go func(id int) {
			collector.RecordHTTPRequest("GET", "/test", 200)
			collector.RecordOrderLatency("test", "spot", float64(id)*0.1)
			_ = collector.GetSnapshot()
			done <- true
		}(i)
	}

	// Wait for all to complete
	for i := 0; i < 10; i++ {
		<-done
	}

	snapshot := collector.GetSnapshot()
	assert.NotNil(t, snapshot)
	assert.False(t, snapshot.Timestamp.IsZero())
}

func TestGetSnapshot_ReturnsImmutableCopy(t *testing.T) {
	collector := NewCollector()

	collector.RecordHTTPRequest("GET", "/test", 200)

	snapshot1 := collector.GetSnapshot()
	snapshot2 := collector.GetSnapshot()

	// Should be different instances
	assert.NotSame(t, &snapshot1, &snapshot2)

	// But same content at this point
	assert.Equal(t, len(snapshot1.Counters), len(snapshot2.Counters))

	// Adding new metric should not affect previous snapshot
	collector.RecordHTTPRequest("POST", "/test", 201)
	snapshot3 := collector.GetSnapshot()

	assert.NotEqual(t, len(snapshot1.Counters), len(snapshot3.Counters))
}

func TestReset_ClearsAllMetrics(t *testing.T) {
	collector := NewCollector()

	collector.RecordHTTPRequest("GET", "/test", 200)
	collector.RecordOrderLatency("binance", "spot", 0.150)
	collector.RecordOrderStatus("binance", "filled")

	// Should have metrics
	snapshot1 := collector.GetSnapshot()
	assert.True(t, len(snapshot1.Counters) > 0)
	assert.True(t, len(snapshot1.Histograms) > 0)

	// Reset
	collector.Reset()

	// Should be empty
	snapshot2 := collector.GetSnapshot()
	assert.Equal(t, 0, len(snapshot2.Counters))
	assert.Equal(t, 0, len(snapshot2.Histograms))
}

func TestCollect_PrometheusFormat(t *testing.T) {
	collector := NewCollector()

	// Add some test data
	collector.RecordHTTPRequest("GET", "/api/test", 200)
	collector.RecordHTTPDuration("GET", "/api/test", 0.150)
	collector.RecordOrderLatency("binance", "spot", 0.250)

	// Collect metrics
	output, err := collector.Collect()
	require.NoError(t, err)
	assert.NotEmpty(t, output)

	// Check that it contains Prometheus format elements
	assert.Contains(t, output, "# HELP")
	assert.Contains(t, output, "# TYPE")
	assert.Contains(t, output, "router_uptime_seconds")
	assert.Contains(t, output, "http_requests_total")
	assert.Contains(t, output, "http_request_duration_seconds")
	assert.Contains(t, output, "order_latency_seconds")
}

func TestCollect_EmptyCollector(t *testing.T) {
	collector := NewCollector()

	output, err := collector.Collect()
	require.NoError(t, err)
	assert.NotEmpty(t, output)

	// Should at least contain uptime metric
	assert.Contains(t, output, "router_uptime_seconds")
}
