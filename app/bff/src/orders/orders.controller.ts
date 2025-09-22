import { Controller, Get, Query } from '@nestjs/common';
import { OrdersService } from './orders.service';
import { GetOrdersDto } from './dto/get-orders.dto';
import { Order } from './entities/order.entity';
import { Public } from '../auth/decorators/public.decorator';

@Controller('orders')
export class OrdersController {
  constructor(private readonly ordersService: OrdersService) {}

  @Get()
  @Public()
  async getOrders(@Query() query: GetOrdersDto): Promise<{ orders: Order[] }> {
    const orders = await this.ordersService.getOrders(query);
    return { orders };
  }
}
