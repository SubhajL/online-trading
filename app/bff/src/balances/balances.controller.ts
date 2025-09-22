import { Controller, Get, Query } from '@nestjs/common';
import { BalancesService } from './balances.service';
import { GetBalancesDto } from './dto/get-balances.dto';
import { Balance } from './entities/balance.entity';
import { Public } from '../auth/decorators/public.decorator';

@Controller('balances')
export class BalancesController {
  constructor(private readonly balancesService: BalancesService) {}

  @Get()
  @Public()
  async getBalances(@Query() query: GetBalancesDto): Promise<Balance[]> {
    return this.balancesService.getBalances(query.venue);
  }
}
