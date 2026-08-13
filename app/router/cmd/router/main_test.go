package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

func TestActiveExecutionRequiresDurableOrderUpdateDependencies(t *testing.T) {
	tests := []struct {
		name        string
		database    string
		updateURL   string
		engineToken string
		want        string
	}{
		{name: "database", updateURL: "http://engine", engineToken: "token", want: "DATABASE_URL"},
		{name: "dispatcher URL", database: "postgres://db", engineToken: "token", want: "ORDER_UPDATE_URL"},
		{name: "engine token", database: "postgres://db", updateURL: "http://engine", want: "ENGINE_INTERNAL_API_TOKEN"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateActiveExecutionDependencies(true, tt.database, tt.updateURL, tt.engineToken)
			if err == nil || !strings.Contains(err.Error(), tt.want) {
				t.Fatalf("expected %s dependency error, got %v", tt.want, err)
			}
		})
	}
	if err := validateActiveExecutionDependencies(false, "", "", ""); err != nil {
		t.Fatalf("inactive execution should not require delivery dependencies: %v", err)
	}
}

func TestLoggingMiddlewareEscapesRequestData(t *testing.T) {
	oldStdout := os.Stdout
	reader, writer, err := os.Pipe()
	if err != nil {
		t.Fatalf("pipe: %v", err)
	}
	os.Stdout = writer
	defer func() {
		os.Stdout = oldStdout
	}()

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.URL.Path = "/<script>alert(1)</script>"
	req.RemoteAddr = "<svg>"
	recorder := httptest.NewRecorder()

	handler := loggingMiddleware(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))

	handler.ServeHTTP(recorder, req)
	_ = writer.Close()

	output, err := io.ReadAll(reader)
	if err != nil {
		t.Fatalf("read log output: %v", err)
	}

	text := string(output)
	if strings.Contains(text, "<script>") || strings.Contains(text, "<svg>") {
		t.Fatalf("expected escaped request data, got %q", text)
	}
	if !strings.Contains(text, "&lt;script&gt;") || !strings.Contains(text, "&lt;svg&gt;") {
		t.Fatalf("expected HTML-escaped request data, got %q", text)
	}
}

func TestAuthMiddlewareRejectsMissingBearerToken(t *testing.T) {
	handler := authMiddleware(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		}),
		"secret-token",
	)

	req := httptest.NewRequest(http.MethodPost, "/place_bracket", nil)
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, req)

	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", recorder.Code)
	}
}

func TestAuthMiddlewareAllowsHealthRoutesWithoutToken(t *testing.T) {
	handler := authMiddleware(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		}),
		"secret-token",
	)

	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, req)

	if recorder.Code != http.StatusNoContent {
		t.Fatalf("expected 204, got %d", recorder.Code)
	}
}
