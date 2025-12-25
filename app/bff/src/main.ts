import { NestFactory } from '@nestjs/core';
import { ConfigService } from '@nestjs/config';
import { ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  const configService = app.get(ConfigService);

  // Global validation pipe
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      transform: true,
      forbidNonWhitelisted: true,
      transformOptions: {
        enableImplicitConversion: true,
      },
    }),
  );

  // Enable CORS - use WS_CORS_ORIGIN env var or default to localhost:3000
  const corsOrigin = configService.get<string>('WS_CORS_ORIGIN') || 'http://localhost:3000';
  app.enableCors({
    origin: corsOrigin,
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With', 'X-Idempotency-Key'],
  });

  // Global prefix
  app.setGlobalPrefix('api');

  // Use PORT for internal container port (3001), fall back to BFF_PORT for external reference
  const port = configService.get<number>('PORT') || 3001;
  await app.listen(port);

  console.log(`🚀 BFF service is running on: http://localhost:${port}/api`);
  console.log(`📢 CORS enabled for origin: ${corsOrigin}`);
}

bootstrap();
