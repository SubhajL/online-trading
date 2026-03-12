package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

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
