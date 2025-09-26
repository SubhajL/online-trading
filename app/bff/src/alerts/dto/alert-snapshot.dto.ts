export class AlertSnapshotDto {
  id: string;
  signalId: string;
  symbol: string;
  timeframe: string;
  imagePath: string;
  imageUrl?: string;
  meta: {
    entry: number;
    stopLoss: number;
    takeProfit: number;
    signalTime: string;
    reasons?: string[];
    side: 'BUY' | 'SELL';
  };
  createdAt: Date;
}
