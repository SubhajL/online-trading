export class AlertSnapshotDto {
  id: string;
  signalId: string;
  symbol: string;
  timeframe: string;
  imagePath: string;
  imageUrl?: string;
  meta: Record<string, unknown>;
  createdAt: Date;
}
