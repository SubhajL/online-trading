import { Injectable, CanActivate, ExecutionContext, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

@Injectable()
export class InternalApiGuard implements CanActivate {
  private readonly internalToken: string;

  constructor(private readonly configService: ConfigService) {
    this.internalToken = this.configService.get<string>('INTERNAL_ALERTS_TOKEN', '');
    if (!this.internalToken) {
      console.warn(
        'WARNING: INTERNAL_ALERTS_TOKEN not set, internal API endpoints are unprotected!',
      );
    }
  }

  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest();
    const authHeader = request.headers.authorization;

    if (!authHeader) {
      throw new UnauthorizedException('Missing Authorization header');
    }

    const [type, token] = authHeader.split(' ');

    if (type !== 'Bearer' || !token) {
      throw new UnauthorizedException('Invalid Authorization header format');
    }

    if (token !== this.internalToken) {
      throw new UnauthorizedException('Invalid internal API token');
    }

    return true;
  }
}
