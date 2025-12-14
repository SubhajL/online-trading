import { Controller, Get, Query, UseGuards } from '@nestjs/common';
import { OrdersService } from './orders.service';
import { GetOrdersDto } from './dto/get-orders.dto';
import { Order } from './entities/order.entity';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';

@Controller('orders')
@UseGuards(JwtAuthGuard)
export class OrdersController {
  constructor(private readonly ordersService: OrdersService) {}

  @Get()
  async getOrders(@Query() query: GetOrdersDto): Promise<{ orders: Order[] }> {
    const orders = await this.ordersService.getOrders(query);
    return { orders };
  }
}
