export class SetAutoTradingCommand {
  constructor(
    public readonly userId: string,
    public readonly enabled: boolean,
  ) {}
}
