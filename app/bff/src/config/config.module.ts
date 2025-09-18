import { Module } from '@nestjs/common';
import { ConfigModule as NestConfigModule } from '@nestjs/config';
import { loadConfiguration } from './configuration';

@Module({})
export class ConfigModule {
  static forRoot() {
    return {
      module: ConfigModule,
      imports: [
        NestConfigModule.forRoot({
          isGlobal: true,
          load: [loadConfiguration],
          cache: true,
        }),
      ],
      global: true,
      exports: [NestConfigModule],
    };
  }
}
