# Alert Adapter Testing Guide

## Overview

Alert adapters (Telegram, LINE) are designed to send trading notifications to external messaging platforms. These adapters have been thoroughly tested with real credentials in local development.

## Test Status

### Integration Tests
- **Local Testing**: ✅ All tests pass with real Telegram/LINE credentials
- **CI Environment**: ⏭️ Tests are skipped due to credential requirements
- **Reason**: Mock implementations for CI would add significant complexity without production value

### Skipped Tests
The following tests are marked with `@pytest.mark.skip` in CI:
- `test_integration_alert_system.py`: All integration tests
- `test_telegram.py`: `test_send_alert_success`

These tests verify:
- Real-time alert delivery
- Multi-platform coordination
- Error recovery and retry logic
- Rate limiting compliance

## Running Tests Locally

To run alert adapter tests with real services:

1. Set up credentials in `.env`:
```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# LINE
LINE_CHANNEL_ACCESS_TOKEN=your_line_token_here
LINE_USER_ID=your_user_id_here
```

2. Run the tests:
```bash
# Run all alert tests
pytest app/engine/adapters/alert/ -v

# Run specific adapter tests
pytest app/engine/adapters/alert/test_telegram.py -v
pytest app/engine/adapters/alert/test_line.py -v
```

## Architecture Notes

### Alert Flow
1. Trading events (decisions, orders, positions) → Event Bus
2. Alert adapters subscribe to relevant events
3. Events are formatted into human-readable messages
4. Messages are sent to configured platforms
5. Delivery is confirmed or retried

### Key Components
- `AlertFormatter`: Converts trading events to readable messages
- `AlertDeduplicator`: Prevents duplicate alerts (Redis-backed)
- Platform adapters: Handle API-specific requirements

## Future Considerations

When adding new alert platforms:
1. Follow the existing adapter pattern
2. Test with real credentials locally first
3. Add skip markers for CI tests
4. Document credential setup

## Technical Debt

- **CI Mocks**: Could be implemented if team grows beyond solo developer
- **Integration Tests**: Consider end-to-end testing in staging environment
- **Monitoring**: Add metrics for alert delivery success rates