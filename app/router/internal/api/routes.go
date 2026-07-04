package api

import "net/http"

func RegisterHealthRoutes(mux *http.ServeMux, handlers *Handlers) {
	mux.HandleFunc("/health", handlers.HealthzHandler)
	mux.HandleFunc("/healthz", handlers.HealthzHandler)
	mux.HandleFunc("/ready", handlers.ReadyzHandler)
	mux.HandleFunc("/readyz", handlers.ReadyzHandler)
}
