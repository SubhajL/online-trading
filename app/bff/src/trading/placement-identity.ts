import { BadRequestException } from '@nestjs/common';
import { createHash } from 'node:crypto';

declare const routerIdempotencyKeyBrand: unique symbol;
export type RouterIdempotencyKey = string & {
  readonly [routerIdempotencyKeyBrand]: true;
};

export type RouterPlacementIdentity = {
  idempotencyKey: RouterIdempotencyKey;
  clientOrderIds: {
    main: string;
    takeProfits: string[];
    stopLoss: string;
  };
};

export function createRouterPlacementIdentity(
  principalId: string,
  callerKey: string,
  takeProfitCount: number,
): RouterPlacementIdentity {
  const normalizedPrincipal = principalId.trim();
  const normalizedKey = callerKey.trim();
  if (!normalizedPrincipal || !normalizedKey) {
    throw new BadRequestException('Idempotency identity is required');
  }
  if (!Number.isInteger(takeProfitCount) || takeProfitCount < 1) {
    throw new BadRequestException('Take-profit count must be positive');
  }

  const digest = createHash('sha256')
    .update(normalizedPrincipal)
    .update('\0')
    .update(normalizedKey)
    .digest('hex');
  const token = digest.slice(0, 16);
  return {
    idempotencyKey: `bff_${digest}` as RouterIdempotencyKey,
    clientOrderIds: {
      main: `${token}_entry`,
      takeProfits: Array.from({ length: takeProfitCount }, (_, index) => `${token}_tp${index + 1}`),
      stopLoss: `${token}_sl`,
    },
  };
}
