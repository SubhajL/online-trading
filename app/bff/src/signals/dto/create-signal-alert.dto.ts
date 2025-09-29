import { IsString, IsNumber, IsEnum, IsArray, IsOptional, IsISO8601 } from 'class-validator';
import { Venue } from '../../balances/dto/get-balances.dto';

export class CreateSignalAlertDto {
  @IsString()
  signalId: string;

  @IsString()
  symbol: string;

  @IsEnum(Venue)
  venue: Venue;

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
