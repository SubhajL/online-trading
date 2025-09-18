import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { ConfigModule } from '@nestjs/config';
import { RouterClientService } from './router-client.service';

@Module({
  imports: [ConfigModule, HttpModule],
  providers: [RouterClientService],
  exports: [RouterClientService],
})
export class RouterClientModule {}
