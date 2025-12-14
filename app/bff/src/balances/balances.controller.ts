import { Controller, Get, Query, UseGuards } from '@nestjs/common';
import { BalancesService } from './balances.service';
import { GetBalancesDto } from './dto/get-balances.dto';
import { Balance } from './entities/balance.entity';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';

@Controller('balances')
@UseGuards(JwtAuthGuard)
export class BalancesController {
  constructor(private readonly balancesService: BalancesService) {}

  @Get()
  async getBalances(@Query() query: GetBalancesDto): Promise<Balance[]> {
    return this.balancesService.getBalances(query.venue);
  }
}
