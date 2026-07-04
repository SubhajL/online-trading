package orders

import (
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestSplitTakeProfitQuantities(t *testing.T) {
	tests := []struct {
		name     string
		total    string
		n        int
		step     string
		expected []string
	}{
		{"remainder goes to last slice", "0.01", 3, "0.001", []string{"0.003", "0.003", "0.004"}},
		{"even split stays even", "0.009", 3, "0.001", []string{"0.003", "0.003", "0.003"}},
		{"two way split", "1", 2, "0.1", []string{"0.5", "0.5"}},
		{"single slice gets everything", "0.0123", 1, "0.001", []string{"0.0123"}},
		{"zero step splits evenly unrounded", "1", 3, "0", []string{
			"0.3333333333333333",
			"0.3333333333333333",
			"0.3333333333333333",
		}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			total := decimal.RequireFromString(tt.total)
			quantities := splitTakeProfitQuantities(total, tt.n, decimal.RequireFromString(tt.step))

			require.Len(t, quantities, tt.n)
			sum := decimal.Zero
			for i, q := range quantities {
				assert.True(t, q.Equal(decimal.RequireFromString(tt.expected[i])),
					"slice %d: got %s want %s", i, q, tt.expected[i])
				sum = sum.Add(q)
			}
			if decimal.RequireFromString(tt.step).IsPositive() {
				assert.True(t, sum.Equal(total), "sum %s != total %s", sum, total)
			}
		})
	}
}

func TestSplitTakeProfitQuantitiesZeroSlices(t *testing.T) {
	assert.Nil(t, splitTakeProfitQuantities(decimal.NewFromInt(1), 0, decimal.Zero))
}
