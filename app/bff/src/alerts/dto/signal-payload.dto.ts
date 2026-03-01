import {
  IsString,
  IsNumber,
  IsEnum,
  IsISO8601,
  IsArray,
  IsOptional,
  ValidateNested,
  IsPositive,
} from 'class-validator';
import { Type } from 'class-transformer';

export enum SignalSide {
  BUY = 'BUY',
  SELL = 'SELL',
}

class SignalContext {
  @IsOptional()
  @IsNumber()
  @IsPositive()
  preCandles?: number;

  @IsOptional()
  @IsNumber()
  @IsPositive()
  postCandles?: number;
}

export class SignalPayloadDto {
  @IsString()
  signalId: string;

  @IsString()
  symbol: string;

  @IsString()
  venue: string;

  @IsString()
  timeframe: string;

  @IsEnum(SignalSide)
  side: SignalSide;

  @IsNumber()
  @IsPositive()
  entry: number;

  @IsNumber()
  @IsPositive()
  stopLoss: number;

  @IsNumber()
  @IsPositive()
  takeProfit: number;

  @IsNumber()
  confidence: number;

  @IsISO8601()
  signalTime: string;

  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  reasons?: string[];

  @IsOptional()
  @ValidateNested()
  @Type(() => SignalContext)
  context?: SignalContext;
}
