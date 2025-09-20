package metrics

import (
	"fmt"
	"strconv"
	"strings"
	"time"
)

// NewCollector creates a new metrics collector with default latency buckets
func NewCollector() *Collector {
	return &Collector{
		requestCounter:    make(map[string]int64),
		requestHistogram:  make(map[string][]float64),
		orderLatencyHist:  make(map[string][]float64),
		orderStatusCount:  make(map[string]int64),
		wsConnectionCount: make(map[string]int64),
		wsEventCounter:    make(map[string]int64),
		customHistograms:  make(map[string][]float64),
		customCounters:    make(map[string]int64),
		histogramBuckets:  DefaultLatencyBuckets,
		startTime:         time.Now(),
	}
}

// NewCollectorWithBuckets creates a new metrics collector with custom histogram buckets
func NewCollectorWithBuckets(buckets []float64) *Collector {
	return &Collector{
		requestCounter:    make(map[string]int64),
		requestHistogram:  make(map[string][]float64),
		orderLatencyHist:  make(map[string][]float64),
		orderStatusCount:  make(map[string]int64),
		wsConnectionCount: make(map[string]int64),
		wsEventCounter:    make(map[string]int64),
		customHistograms:  make(map[string][]float64),
		customCounters:    make(map[string]int64),
		histogramBuckets:  buckets,
		startTime:         time.Now(),
	}
}

// RecordHTTPRequest increments the HTTP request counter
func (c *Collector) RecordHTTPRequest(method, path string, status int) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	key := c.buildKey(method, path, status)
	c.requestCounter[key]++
}

// RecordHTTPDuration records HTTP request duration
func (c *Collector) RecordHTTPDuration(method, endpoint string, duration float64) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	key := c.buildKey(method, endpoint)
	c.requestHistogram[key] = append(c.requestHistogram[key], duration)
}

// RecordOrderLatency records order latency by exchange and type
func (c *Collector) RecordOrderLatency(exchange, orderType string, latency float64) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	key := c.buildKey(exchange, orderType)
	c.orderLatencyHist[key] = append(c.orderLatencyHist[key], latency)
}

// RecordOrderStatus increments order status counter
func (c *Collector) RecordOrderStatus(exchange, status string) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	key := c.buildKey(exchange, status)
	c.orderStatusCount[key]++
}

// RecordWebSocketConnection records WebSocket connection events
func (c *Collector) RecordWebSocketConnection(status string) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	c.wsConnectionCount[status]++
}

// RecordWebSocketEvent records WebSocket event counts
func (c *Collector) RecordWebSocketEvent(eventType string) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	c.wsEventCounter[eventType]++
}

// RecordCustomHistogram records a custom histogram value
func (c *Collector) RecordCustomHistogram(name string, value float64) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	c.customHistograms[name] = append(c.customHistograms[name], value)
}

// RecordCustomCounter increments a custom counter
func (c *Collector) RecordCustomCounter(name string) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	c.customCounters[name]++
}

// GetSnapshot returns a point-in-time view of all metrics
func (c *Collector) GetSnapshot() MetricSnapshot {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	var counters []CounterEntry
	var histograms []HistogramEntry

	// HTTP request counters
	for key, count := range c.requestCounter {
		parts := c.parseKey(key, 3)
		if len(parts) >= 3 {
			counters = append(counters, CounterEntry{
				Name:  "http_requests_total",
				Value: count,
				Labels: map[string]string{
					"method": parts[0],
					"path":   parts[1],
					"status": parts[2],
				},
			})
		}
	}

	// HTTP request duration histograms
	for key, durations := range c.requestHistogram {
		parts := c.parseKey(key, 2)
		if len(parts) >= 2 {
			for _, duration := range durations {
				histograms = append(histograms, HistogramEntry{
					Name:  "http_request_duration_seconds",
					Value: duration,
					Labels: map[string]string{
						"method":   parts[0],
						"endpoint": parts[1],
					},
				})
			}
		}
	}

	// Order latency histograms
	for key, latencies := range c.orderLatencyHist {
		parts := c.parseKey(key, 2)
		if len(parts) >= 2 {
			for _, latency := range latencies {
				histograms = append(histograms, HistogramEntry{
					Name:  "order_latency_seconds",
					Value: latency,
					Labels: map[string]string{
						"exchange": parts[0],
						"type":     parts[1],
					},
				})
			}
		}
	}

	// Order status counters
	for key, count := range c.orderStatusCount {
		parts := c.parseKey(key, 2)
		if len(parts) >= 2 {
			counters = append(counters, CounterEntry{
				Name:  "order_status_total",
				Value: count,
				Labels: map[string]string{
					"exchange": parts[0],
					"status":   parts[1],
				},
			})
		}
	}

	// WebSocket connection counters
	for status, count := range c.wsConnectionCount {
		counters = append(counters, CounterEntry{
			Name:  "websocket_connections_total",
			Value: count,
			Labels: map[string]string{
				"status": status,
			},
		})
	}

	// WebSocket event counters
	for eventType, count := range c.wsEventCounter {
		counters = append(counters, CounterEntry{
			Name:  "websocket_events_total",
			Value: count,
			Labels: map[string]string{
				"event_type": eventType,
			},
		})
	}

	// Custom histograms
	for name, values := range c.customHistograms {
		for _, value := range values {
			histograms = append(histograms, HistogramEntry{
				Name:   name,
				Value:  value,
				Labels: make(map[string]string),
			})
		}
	}

	// Custom counters
	for name, count := range c.customCounters {
		counters = append(counters, CounterEntry{
			Name:   name,
			Value:  count,
			Labels: make(map[string]string),
		})
	}

	return MetricSnapshot{
		Counters:   counters,
		Histograms: histograms,
		Timestamp:  time.Now(),
	}
}

// Reset clears all metrics
func (c *Collector) Reset() {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	c.requestCounter = make(map[string]int64)
	c.requestHistogram = make(map[string][]float64)
	c.orderLatencyHist = make(map[string][]float64)
	c.orderStatusCount = make(map[string]int64)
	c.wsConnectionCount = make(map[string]int64)
	c.wsEventCounter = make(map[string]int64)
	c.customHistograms = make(map[string][]float64)
	c.customCounters = make(map[string]int64)
	c.startTime = time.Now()
}

// Collect returns Prometheus-formatted metrics
func (c *Collector) Collect() (string, error) {
	snapshot := c.GetSnapshot()
	var lines []string

	// Add uptime metric
	uptime := time.Since(c.startTime).Seconds()
	lines = append(lines, "# HELP router_uptime_seconds Time since the server started")
	lines = append(lines, "# TYPE router_uptime_seconds counter")
	lines = append(lines, fmt.Sprintf("router_uptime_seconds %f %d", uptime, snapshot.Timestamp.Unix()))
	lines = append(lines, "")

	// Process counters
	counterGroups := make(map[string][]CounterEntry)
	for _, counter := range snapshot.Counters {
		counterGroups[counter.Name] = append(counterGroups[counter.Name], counter)
	}

	for metricName, counters := range counterGroups {
		// Add help and type comments
		lines = append(lines, fmt.Sprintf("# HELP %s %s", metricName, getCounterHelp(metricName)))
		lines = append(lines, fmt.Sprintf("# TYPE %s counter", metricName))

		// Add counter values
		for _, counter := range counters {
			labels := formatLabels(counter.Labels)
			lines = append(lines, fmt.Sprintf("%s%s %d %d", metricName, labels, counter.Value, snapshot.Timestamp.Unix()))
		}
		lines = append(lines, "")
	}

	// Process histograms
	histogramGroups := make(map[string][]HistogramEntry)
	for _, histogram := range snapshot.Histograms {
		histogramGroups[histogram.Name] = append(histogramGroups[histogram.Name], histogram)
	}

	for metricName, histograms := range histogramGroups {
		// Add help and type comments
		lines = append(lines, fmt.Sprintf("# HELP %s %s", metricName, getHistogramHelp(metricName)))
		lines = append(lines, fmt.Sprintf("# TYPE %s histogram", metricName))

		// Group histograms by labels to create buckets
		labelGroups := make(map[string][]float64)
		for _, hist := range histograms {
			labelKey := formatLabels(hist.Labels)
			labelGroups[labelKey] = append(labelGroups[labelKey], hist.Value)
		}

		// Generate histogram buckets for each label group
		for labelKey, values := range labelGroups {
			bucketCounts := c.calculateBucketCounts(values)

			// Generate bucket metrics
			for i, bucketLimit := range c.histogramBuckets {
				bucketLabels := addBucketLabel(labelKey, bucketLimit)
				lines = append(lines, fmt.Sprintf("%s_bucket%s %d %d",
					metricName, bucketLabels, bucketCounts[i], snapshot.Timestamp.Unix()))
			}

			// Add +Inf bucket
			infBucketLabels := addBucketLabel(labelKey, "+Inf")
			lines = append(lines, fmt.Sprintf("%s_bucket%s %d %d",
				metricName, infBucketLabels, len(values), snapshot.Timestamp.Unix()))

			// Add sum and count
			sum := 0.0
			for _, value := range values {
				sum += value
			}
			lines = append(lines, fmt.Sprintf("%s_sum%s %f %d",
				metricName, labelKey, sum, snapshot.Timestamp.Unix()))
			lines = append(lines, fmt.Sprintf("%s_count%s %d %d",
				metricName, labelKey, len(values), snapshot.Timestamp.Unix()))
		}
		lines = append(lines, "")
	}

	return strings.Join(lines, "\n"), nil
}

// buildKey creates a composite key from multiple parts
func (c *Collector) buildKey(parts ...interface{}) string {
	var key string
	for i, part := range parts {
		if i > 0 {
			key += ":"
		}
		switch v := part.(type) {
		case string:
			key += v
		case int:
			key += strconv.Itoa(v)
		}
	}
	return key
}

// parseKey splits a composite key into parts
func (c *Collector) parseKey(key string, expectedParts int) []string {
	parts := make([]string, 0, expectedParts)
	current := ""

	for _, char := range key {
		if char == ':' {
			parts = append(parts, current)
			current = ""
		} else {
			current += string(char)
		}
	}

	if current != "" {
		parts = append(parts, current)
	}

	return parts
}

// Helper functions for Prometheus formatting

func getCounterHelp(metricName string) string {
	switch metricName {
	case "http_requests_total":
		return "Total number of HTTP requests"
	case "order_status_total":
		return "Total number of orders by status"
	case "websocket_connections_total":
		return "Total number of WebSocket connection events"
	case "websocket_events_total":
		return "Total number of WebSocket events"
	default:
		return "Custom counter metric"
	}
}

func getHistogramHelp(metricName string) string {
	switch metricName {
	case "http_request_duration_seconds":
		return "HTTP request duration in seconds"
	case "order_latency_seconds":
		return "Order processing latency in seconds"
	default:
		return "Custom histogram metric"
	}
}

func formatLabels(labels map[string]string) string {
	if len(labels) == 0 {
		return ""
	}

	var pairs []string
	for key, value := range labels {
		pairs = append(pairs, fmt.Sprintf(`%s="%s"`, key, value))
	}

	return "{" + strings.Join(pairs, ",") + "}"
}

func addBucketLabel(existingLabels string, bucketLimit interface{}) string {
	bucketLimitStr := fmt.Sprintf("%v", bucketLimit)

	if existingLabels == "" || existingLabels == "{}" {
		return fmt.Sprintf(`{le="%s"}`, bucketLimitStr)
	}

	// Remove closing brace and add bucket label
	trimmed := strings.TrimSuffix(existingLabels, "}")
	return fmt.Sprintf(`%s,le="%s"}`, trimmed, bucketLimitStr)
}

func (c *Collector) calculateBucketCounts(values []float64) []int {
	bucketCounts := make([]int, len(c.histogramBuckets))

	for _, value := range values {
		for i, bucketLimit := range c.histogramBuckets {
			if value <= bucketLimit {
				bucketCounts[i]++
			}
		}
	}

	// Make buckets cumulative
	for i := 1; i < len(bucketCounts); i++ {
		bucketCounts[i] += bucketCounts[i-1]
	}

	return bucketCounts
}
