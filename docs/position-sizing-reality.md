# Position Sizing Reality Check

## The Key Insight

**We cannot always achieve the target 0.5% risk per trade due to the 2% maximum position size limit.**

This is not a bug - it's a critical safety feature.

## Why This Happens

### Bitcoin Example ($50,000 price)

With a $10,000 account:
- To risk 0.5% ($50) with a 2% stop loss ($1,000 move)
- We'd need: $50 ÷ $1,000 = 0.05 BTC
- Position value: 0.05 BTC × $50,000 = $2,500
- That's 25% of the account! ❌

The 2% position limit caps us at:
- Max position: $10,000 × 2% = $200
- Max BTC: $200 ÷ $50,000 = 0.004 BTC
- Actual risk: 0.004 × $1,000 = $40 (0.4% risk) ✅

## Position Sizing Rules

1. **Target**: Risk 0.5% of account per trade
2. **Constraint**: Never exceed 2% position size
3. **Reality**: With expensive assets, we often achieve less than 0.5% risk

## Account Size Requirements

To achieve full 0.5% risk on Bitcoin with 2% stop:

| BTC Price | Account Needed | Explanation |
|-----------|----------------|-------------|
| $20,000   | $50,000       | 2.5× BTC price |
| $50,000   | $125,000      | 2.5× BTC price |
| $100,000  | $250,000      | 2.5× BTC price |

Formula: `Account Size = BTC Price × Stop% ÷ (Risk% × 2)`

## Practical Implications

### Small Accounts ($10k-50k)
- Trading BTC: Expect 0.04-0.2% risk per trade
- Better suited for: ETH, altcoins, or futures with leverage
- Consider: Micro BTC futures or fractional shares

### Medium Accounts ($50k-500k)
- Can achieve closer to 0.5% risk on most assets
- Still limited on very expensive assets with tight stops
- Good range for diverse portfolio

### Large Accounts ($500k+)
- Can achieve full 0.5% risk on most scenarios
- Position limit becomes binding only with very tight stops
- Focus shifts to liquidity and slippage concerns

## Code Implementation

```python
# Our position sizing logic (simplified)
risk_based_position = (account * 0.005) / stop_distance
max_allowed_position = (account * 0.02) / entry_price

# Safety: Use the smaller of the two
actual_position = min(risk_based_position, max_allowed_position)
```

## Safety First

This design ensures:
1. **Never risk more than 0.5%** - Protects from large losses
2. **Never exceed 2% position** - Prevents overconcentration
3. **Graceful degradation** - System still works with constraints

## Recommendations

1. **Accept reduced risk** when position limits apply
2. **Size accounts appropriately** for assets you trade
3. **Use leverage carefully** in futures to achieve target risk
4. **Monitor actual risk** vs target risk in reporting

Remember: It's better to take smaller, safer positions than to violate risk management rules.