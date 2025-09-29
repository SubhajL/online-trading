import { IsString, IsNumber, IsEnum, IsArray, IsOptional, IsISO8601 } from 'class-validator';

export class CreateSignalAlertDto {
  @IsString()
  signalId: string;

  @IsString()
  symbol: string;

  @IsEnum(['SPOT', 'USD_M'])
  venue: 'SPOT' | 'USD_M';

  @IsEnum(['BUY', 'SELL'])
  side: 'BUY' | 'SELL';

  @IsNumber()
  entry: number;

  @IsNumber()
  stopLoss: number;

  @IsNumber()
  takeProfit: number;

  @IsNumber()
  confidence: number;

  @IsArray()
  @IsString({ each: true })
  reasons: string[];

  @IsString()
  timeframe: string;

  @IsISO8601()
  signalTime: string;

  @IsOptional()
  @IsNumber()
  price?: number;
}