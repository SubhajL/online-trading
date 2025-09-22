import { IsString, IsNumber, IsEnum, IsOptional, IsPositive } from 'class-validator';
import type { OrderSide, OrderType } from '../../database/entities/orders.entity';

export class PlaceOrderDto {
  @IsString()
  symbol!: string;

  @IsEnum(['buy', 'sell'])
  side!: OrderSide;

  @IsEnum(['market', 'limit', 'stop_market'])
  type!: OrderType;

  @IsNumber()
  @IsPositive()
  quantity!: number;

  @IsOptional()
  @IsNumber()
  @IsPositive()
  price?: number;

  @IsOptional()
  @IsNumber()
  @IsPositive()
  stopPrice?: number;

  @IsOptional()
  @IsNumber()
  @IsPositive()
  stopLoss?: number;

  @IsOptional()
  @IsNumber()
  @IsPositive()
  takeProfit?: number;
}
