export class Balance {
  asset: string;
  free: number;
  locked: number;
  total: number;
  venue: 'SPOT' | 'USD_M';
  usdValue: number | null;
}
