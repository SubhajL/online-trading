import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { OrdersController } from './orders.controller';
import { OrdersService } from './orders.service';
import { OrderEntity } from './entities/order-entity';
import { OrderRepository } from './repositories/order.repository';

@Module({
  imports: [TypeOrmModule.forFeature([OrderEntity])],
  controllers: [OrdersController],
  providers: [OrdersService, OrderRepository],
  exports: [OrdersService],
})
export class OrdersModule {}
