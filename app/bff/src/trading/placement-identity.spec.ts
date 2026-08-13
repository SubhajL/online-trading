import { BadRequestException } from '@nestjs/common';
import { createRouterPlacementIdentity } from './placement-identity';

describe(createRouterPlacementIdentity.name, () => {
  it('derives the same router identity for the same user and caller key', () => {
    const first = createRouterPlacementIdentity('user-123', 'click-456', 2);
    const replay = createRouterPlacementIdentity('user-123', 'click-456', 2);

    expect(replay).toEqual(first);
    expect(
      new Set([
        first.clientOrderIds.main,
        ...first.clientOrderIds.takeProfits,
        first.clientOrderIds.stopLoss,
      ]).size,
    ).toBe(4);
    expect(
      [
        first.clientOrderIds.main,
        ...first.clientOrderIds.takeProfits,
        first.clientOrderIds.stopLoss,
      ].every((value) => value.length <= 36),
    ).toBe(true);
  });

  it('scopes a caller key to the authenticated user', () => {
    const first = createRouterPlacementIdentity('user-123', 'click-456', 1);
    const second = createRouterPlacementIdentity('user-789', 'click-456', 1);

    expect(second.idempotencyKey).not.toBe(first.idempotencyKey);
    expect(second.clientOrderIds).not.toEqual(first.clientOrderIds);
  });

  it('rejects a blank caller key', () => {
    expect(() => createRouterPlacementIdentity('user-123', '  ', 1)).toThrow(BadRequestException);
  });
});
