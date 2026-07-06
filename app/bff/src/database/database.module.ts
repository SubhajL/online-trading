import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { DatabaseSchemaVerifierService } from './database-schema-verifier.service';

@Module({
  imports: [
    TypeOrmModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: async (configService: ConfigService) => ({
        type: 'postgres',
        host: configService.get<string>('POSTGRES_HOST', 'localhost'),
        port: configService.get<number>('POSTGRES_PORT', 5432),
        username: configService.get<string>('POSTGRES_USER', 'trading_user'),
        password: configService.get<string>('POSTGRES_PASSWORD', 'your_secure_password_here'),
        database: configService.get<string>('POSTGRES_DB', 'trading_platform'),
        autoLoadEntities: true,
        synchronize: false,
        logging: configService.get<string>('NODE_ENV') === 'development',
      }),
    }),
  ],
  providers: [DatabaseSchemaVerifierService],
})
export class DatabaseModule {}
