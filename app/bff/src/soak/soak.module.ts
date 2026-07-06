import { Module } from '@nestjs/common';
import { RouterClientModule } from '../router-client/router-client.module';
import { SoakController } from './soak.controller';
import { SoakService } from './soak.service';

@Module({
  imports: [RouterClientModule],
  controllers: [SoakController],
  providers: [SoakService],
})
export class SoakModule {}
