package storage

import (
	"strings"
	"testing"
)

func TestUpsertOrderIntentSQL_UsesNumericNullIfForFractionalPrices(t *testing.T) {
	if !strings.Contains(upsertOrderIntentSQL, "NULLIF($12::numeric,0::numeric)") {
		t.Fatalf("requested_price NULLIF must cast to numeric: %s", upsertOrderIntentSQL)
	}
	if !strings.Contains(upsertOrderIntentSQL, "NULLIF($17::numeric,0::numeric)") {
		t.Fatalf("expected_price NULLIF must cast to numeric: %s", upsertOrderIntentSQL)
	}
}
