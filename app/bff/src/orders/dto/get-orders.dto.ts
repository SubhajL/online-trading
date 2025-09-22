import { IsOptional, IsIn, IsString, IsNumber } from 'class-validator';
import { Transform } from 'class-transformer';
import { OrderStatus, Venue } from '../entities/order.entity';

export class GetOrdersDto {
  @IsOptional()
  @IsIn(['SPOT', 'USD_M'])
  venue?: Venue;

  @IsOptional()
  @IsIn(['NEW', 'FILLED', 'PARTIALLY_FILLED', 'CANCELED', 'REJECTED', 'EXPIRED'])
  status?: OrderStatus;

  @IsOptional()
  @IsString()
  symbol?: string;

  @IsOptional()
  @IsNumber()
  @Transform(({ value }) => parseInt(value, 10))
  limit?: number;

  @IsOptional()
  @IsNumber()
  @Transform(({ value }) => parseInt(value, 10))
  offset?: number;
}
