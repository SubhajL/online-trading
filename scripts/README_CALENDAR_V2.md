# Economic Calendar Scripts V2 - Free Data Sources

## Overview

Version 2 of the calendar updater pulls from **FREE data sources** instead of relying on manual dates:

### Free Sources Implemented

1. **FRED API** (Federal Reserve Economic Data)
   - Official US government data
   - Free with registration at https://fred.stlouisfed.org/docs/api/api_key.html
   - Most reliable for US data (CPI, NFP)

2. **ForexFactory** (Web Scraping)
   - Popular trader calendar
   - High-quality event data
   - No API key needed

3. **FXStreet RSS Feed**
   - Real-time RSS feed
   - No registration required
   - Good for upcoming events

4. **Trading Economics** (Limited Free Tier)
   - Guest access available
   - Multiple countries covered
   - Rate limited but useful

## Quick Start

### 1. Install Dependencies
```bash
pip install -r scripts/requirements_calendar.txt
```

### 2. Get FRED API Key (Recommended)
1. Visit https://fred.stlouisfed.org/docs/api/api_key.html
2. Register for free account
3. Add to `.env`:
   ```bash
   FRED_API_KEY=your_key_here
   ```

### 3. Run the Updater
```bash
# Use all available sources
python3 scripts/update_economic_calendar_v2.py

# Use specific sources only
python3 scripts/update_economic_calendar_v2.py --source fred --source forexfactory

# Dry run to preview
python3 scripts/update_economic_calendar_v2.py --dry-run
```

## Comparison: V1 vs V2

| Feature | V1 (Manual) | V2 (Free Sources) |
|---------|-------------|-------------------|
| Data freshness | Manual updates | Automatic from APIs |
| Reliability | High (if maintained) | Medium (depends on sources) |
| Maintenance | High effort | Low effort |
| Coverage | Limited events | Comprehensive |
| Dependencies | None | requests, beautifulsoup4 |

## Source Reliability Ranking

1. **FRED** ⭐⭐⭐⭐⭐
   - Official government source
   - Never goes down
   - Exact release times

2. **Trading Economics** ⭐⭐⭐⭐
   - Professional data
   - Rate limited on free tier
   - Good coverage

3. **ForexFactory** ⭐⭐⭐
   - Community maintained
   - Can change HTML structure
   - Respectful scraping required

4. **FXStreet** ⭐⭐⭐
   - RSS can be delayed
   - Limited detail
   - Good as backup

## Best Practices

### 1. Use Multiple Sources
```bash
# Good - uses redundancy
python3 scripts/update_economic_calendar_v2.py

# Less reliable - single source
python3 scripts/update_economic_calendar_v2.py --source fxstreet
```

### 2. Schedule Updates Carefully
```bash
# Cron for every 6 hours with random delay
0 */6 * * * sleep $((RANDOM % 300)) && /path/to/update_economic_calendar_v2.py
```

### 3. Monitor Source Health
```python
# Add to your monitoring
def check_calendar_sources():
    sources = ['fred', 'forexfactory', 'fxstreet', 'tradingeconomics']
    working = []

    for source in sources:
        result = subprocess.run([
            'python3', 'scripts/update_economic_calendar_v2.py',
            '--source', source, '--dry-run'
        ], capture_output=True)

        if result.returncode == 0:
            working.append(source)

    if len(working) < 2:
        alert("Less than 2 calendar sources working!")
```

## Handling Source Failures

The script is resilient to individual source failures:

1. **Automatic fallback** - If one source fails, others continue
2. **Manual dates included** - Known central bank dates as safety net
3. **Deduplication** - Same event from multiple sources merged
4. **Validation** - Suspicious data filtered out

## Web Scraping Ethics

When using ForexFactory scraping:

1. **Respect robots.txt**
2. **Add delays between requests** (already implemented)
3. **Use descriptive User-Agent**
4. **Don't hammer the servers**
5. **Consider donating if you rely on their data**

## Troubleshooting

### "No module named 'beautifulsoup4'"
```bash
pip install beautifulsoup4 lxml
```

### "FRED API key not found"
Either:
- Get free key from FRED website
- Or use other sources: `--source forexfactory --source fxstreet`

### "No events found"
Check:
1. Internet connection
2. Source websites aren't down
3. HTML structure hasn't changed (for scrapers)

### Rate Limiting
If you see 429 errors:
- Add delays between updates
- Use fewer sources per run
- Rotate between sources

## Future Enhancements

1. **Add more free sources**:
   - DailyFX RSS
   - Myfxbook calendar API
   -央行 websites direct

2. **Caching layer**:
   ```python
   # Redis cache to avoid duplicate fetches
   cache_key = f"calendar:{source}:{date}"
   if redis.get(cache_key):
       return cached_data
   ```

3. **Smart scheduling**:
   - Fetch more frequently near known event times
   - Less frequently on weekends

4. **Event verification**:
   - Cross-check between sources
   - Flag discrepancies

## Migration from V1

To migrate from manual V1 to automated V2:

1. Install dependencies: `pip install -r scripts/requirements_calendar.txt`
2. Get FRED API key (optional but recommended)
3. Test V2: `python3 scripts/update_economic_calendar_v2.py --dry-run`
4. Update cron to use V2 script
5. Keep V1 as emergency fallback

## Summary

V2 provides **automated, free, multi-source** calendar updates. While not as reliable as paid services, using multiple free sources provides good coverage for most trading needs. The script handles failures gracefully and includes manual dates as a safety net.

Remember: **Some data is better than no data**, but always verify critical events (FOMC, ECB, BOE) against official sources!