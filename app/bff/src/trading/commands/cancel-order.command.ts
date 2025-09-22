export class CancelOrderCommand {
  constructor(
    public readonly userId: string,
    public readonly orderId: string,
    public readonly symbol: string,
    public readonly venue: 'SPOT' | 'USD_M',
  ) {}
}