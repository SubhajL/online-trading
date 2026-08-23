import type { ValidationArguments, ValidatorConstraintInterface } from 'class-validator';
import { Type } from 'class-transformer';
import {
  Equals,
  IsBoolean,
  IsDefined,
  IsEnum,
  IsISO8601,
  IsNotEmpty,
  IsString,
  Matches,
  Validate,
  ValidatorConstraint,
} from 'class-validator';
import type { OrderUpdateV1 } from '../../contracts/gen';

const decimalStringPattern = /^\d{1,10}(?:\.\d{1,8})?$/;
const nonWhitespacePattern = /\S/;

@ValidatorConstraint({ name: 'nullableDecimalString', async: false })
class NullableDecimalStringConstraint implements ValidatorConstraintInterface {
  validate(value: unknown): boolean {
    return value === null || (typeof value === 'string' && decimalStringPattern.test(value));
  }

  defaultMessage(): string {
    return 'must be null or a non-negative finite decimal string';
  }
}

@ValidatorConstraint({ name: 'nullableString', async: false })
class NullableStringConstraint implements ValidatorConstraintInterface {
  validate(value: unknown): boolean {
    return value === null || typeof value === 'string';
  }

  defaultMessage(): string {
    return 'must be null or a string';
  }
}

@ValidatorConstraint({ name: 'nullableFiniteNonnegativeNumber', async: false })
class NullableFiniteNonnegativeNumberConstraint implements ValidatorConstraintInterface {
  validate(value: unknown): boolean {
    return value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0);
  }

  defaultMessage(): string {
    return 'must be null or a finite non-negative number';
  }
}

@ValidatorConstraint({ name: 'applicableOrderPrices', async: false })
class ApplicableOrderPricesConstraint implements ValidatorConstraintInterface {
  validate(_value: unknown, args: ValidationArguments): boolean {
    const payload = args.object as OrderUpdateV1;
    switch (payload.order_type) {
      case 'market':
        return payload.price === null && payload.stop_price === null;
      case 'limit':
        return payload.price !== null && payload.stop_price === null;
      case 'stop_market':
        return payload.price === null && payload.stop_price !== null;
      case 'stop_limit':
        return payload.price !== null && payload.stop_price !== null;
      default:
        return true;
    }
  }

  defaultMessage(args: ValidationArguments): string {
    return `price and stop_price are incompatible with order_type ${String((args.object as OrderUpdateV1).order_type)}`;
  }
}

export class OrderUpdateDto implements OrderUpdateV1 {
  @IsDefined()
  @Equals('1.0.0')
  @Type(() => Object)
  version!: string;

  @IsDefined()
  @IsEnum(['SPOT', 'USD_M'])
  @Type(() => Object)
  venue!: OrderUpdateV1['venue'];

  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @Matches(nonWhitespacePattern)
  @Type(() => Object)
  symbol!: string;

  @IsDefined()
  @IsString()
  @Type(() => Object)
  order_id!: string;

  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @Matches(nonWhitespacePattern)
  @Type(() => Object)
  client_order_id!: string;

  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @Matches(nonWhitespacePattern)
  @Type(() => Object)
  decision_id!: string;

  @IsDefined()
  @IsISO8601({ strict: true })
  @Type(() => Object)
  update_time!: string;

  @IsDefined()
  @IsEnum(['pending', 'new', 'partially_filled', 'filled', 'cancelled', 'rejected', 'expired'])
  @Type(() => Object)
  status!: OrderUpdateV1['status'];

  @IsDefined()
  @IsEnum(['buy', 'sell'])
  @Type(() => Object)
  side!: OrderUpdateV1['side'];

  @IsDefined()
  @IsEnum(['market', 'limit', 'stop_market', 'stop_limit'])
  @Validate(ApplicableOrderPricesConstraint)
  @Type(() => Object)
  order_type!: OrderUpdateV1['order_type'];

  @Validate(NullableDecimalStringConstraint)
  @Type(() => Object)
  price!: string | null;

  @Validate(NullableDecimalStringConstraint)
  @Type(() => Object)
  stop_price!: string | null;

  @IsDefined()
  @IsString()
  @Matches(decimalStringPattern)
  @Type(() => Object)
  quantity!: string;

  @IsDefined()
  @IsString()
  @Matches(decimalStringPattern)
  @Type(() => Object)
  filled_quantity!: string;

  @Validate(NullableDecimalStringConstraint)
  @Type(() => Object)
  average_fill_price!: string | null;

  @Validate(NullableFiniteNonnegativeNumberConstraint)
  @Type(() => Object)
  commission!: number | null;

  @Validate(NullableStringConstraint)
  @Type(() => Object)
  commission_asset!: string | null;

  @Validate(NullableStringConstraint)
  @Type(() => Object)
  error_message!: string | null;

  @IsDefined()
  @IsBoolean()
  @Type(() => Object)
  is_reduce_only!: boolean;
}
