import { IsOptional, IsEnum } from 'class-validator';

export enum Venue {
  SPOT = 'SPOT',
  USD_M = 'USD_M',
}

export class GetBalancesDto {
  @IsOptional()
  @IsEnum(Venue)
  venue?: Venue;
}
