import type { OrderRequest } from '../../router-client/router-client.service';

export class PlaceOrderCommand {
  constructor(
    public readonly userId: string,
    public readonly orderRequest: OrderRequest,
    public readonly idempotencyKey: string,
  ) {}
}
