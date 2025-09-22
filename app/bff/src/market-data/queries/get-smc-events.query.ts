export class GetSmcEventsQuery {
  constructor(
    public readonly symbol: string,
    public readonly tf: string,
    public readonly eventTypes?: string[],
    public readonly startTime?: Date,
    public readonly endTime?: Date,
    public readonly limit?: number,
  ) {}
}
