import 'reflect-metadata';
import { plainToInstance } from 'class-transformer';
import { validateSync } from 'class-validator';
import { SignalPayloadDto } from './signal-payload.dto';

describe(SignalPayloadDto.name, () => {
  const validatePayload = (payload: Record<string, unknown>) =>
    validateSync(
      plainToInstance(SignalPayloadDto, payload, {
        enableImplicitConversion: true,
      }),
      {
        whitelist: true,
        forbidNonWhitelisted: true,
      },
    );

  it('accepts the canonical engine snapshot delivery payload', () => {
    const errors = validatePayload({
      signalId: 'exec_5f927db522784efcae0f99de21f20544',
      symbol: 'BTCUSDT',
      venue: 'USD_M',
      timeframe: '15m',
      side: 'BUY',
      entry: 50000,
      stopLoss: 49500,
      takeProfit: 51000,
      confidence: 0.75,
      signalTime: '2026-08-22T12:00:00+00:00',
      reasons: ['Test decision'],
    });

    expect(errors).toEqual([]);
  });

  it('rejects the old engine payload with null identity and undeclared fields', () => {
    const errors = validatePayload({
      idempotencyKey: 'sig_test123',
      signalId: null,
      symbol: 'BTCUSDT',
      venue: 'SPOT',
      timeframe: null,
      side: 'BUY',
      entry: '50000',
      stopLoss: '49500',
      takeProfit: '51000',
      confidence: '0.75',
      signalTime: '2026-08-22T12:00:00+00:00',
    });

    expect(errors.some((error) => error.property === 'idempotencyKey')).toBe(true);
    expect(errors.some((error) => error.property === 'signalId')).toBe(true);
    expect(errors.some((error) => error.property === 'timeframe')).toBe(true);
  });
});
