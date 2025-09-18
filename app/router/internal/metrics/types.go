package metrics

import (
	"sync"
	"time"
)

// Collector handles Prometheus metrics collection
type Collector struct {
	// HTTP request metrics
	requestCounter    map[string]int64 // [method:path:status]
	requestHistogram  map[string][]float64 // [method:endpoint] -> durations

	// Order metrics
	orderLatencyHist  map[string][]float64 // [exchange:type] -> durations
	orderStatusCount  map[string]int64     // [exchange:status] -> count

	// WebSocket metrics
	wsConnectionCount map[string]int64     // [status] -> count
	wsEventCounter    map[string]int64     // [event_type] -> count

	// Custom metrics
	customHistograms map[string][]float64 // [name] -> values
	customCounters   map[string]int64     // [name] -> count

	// Thread safety
	mutex sync.RWMutex

	// Configuration
	histogramBuckets []float64
	startTime        time.Time
}

// HistogramEntry represents a histogram data point
type HistogramEntry struct {
	Name   string
	Value  float64
	Labels map[string]string
}

// CounterEntry represents a counter data point
type CounterEntry struct {
	Name   string
	Value  int64
	Labels map[string]string
}

// MetricSnapshot represents a point-in-time view of all metrics
type MetricSnapshot struct {
	Counters   []CounterEntry
	Histograms []HistogramEntry
	Timestamp  time.Time
}

// Default histogram buckets for latency measurements (in seconds)
var DefaultLatencyBuckets = []float64{
	0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
}

// Default histogram buckets for duration measurements (in milliseconds)
var DefaultDurationBuckets = []float64{
	1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000,
}