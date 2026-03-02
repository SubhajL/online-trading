import { CanActivate, ExecutionContext, Injectable, Logger } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { ConfigService } from '@nestjs/config';
import { Socket } from 'socket.io';
import type { JwtPayload } from '../interfaces/jwt-payload.interface';

@Injectable()
export class WsJwtGuard implements CanActivate {
  private readonly logger = new Logger(WsJwtGuard.name);

  constructor(
    private readonly jwtService: JwtService,
    private readonly configService: ConfigService,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const client = context.switchToWs().getClient<Socket>();
    const token = this.extractToken(client);

    if (!token) {
      this.logger.warn('No JWT token found in WebSocket connection');
      return false;
    }

    try {
      const secret =
        this.configService.get<string>('JWT_SECRET') ??
        this.configService.get<string>('jwt.secret');

      if (!secret) {
        this.logger.error('JWT secret is not configured');
        return false;
      }

      const payload = await this.jwtService.verifyAsync<JwtPayload>(token, {
        secret,
      });

      client.data.user = payload;
      return true;
    } catch (error) {
      this.logger.error(
        `JWT verification failed: ${error instanceof Error ? error.message : 'Unknown error'}`,
      );
      return false;
    }
  }

  private extractToken(client: Socket): string | undefined {
    let token = client.handshake.auth?.token || (client.handshake.query?.token as string);

    if (token?.startsWith('Bearer ')) {
      token = token.slice(7);
    }

    return token;
  }
}
