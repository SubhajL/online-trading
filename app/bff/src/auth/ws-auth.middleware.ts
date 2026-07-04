import { Logger } from '@nestjs/common';
import type { ConfigService } from '@nestjs/config';
import type { JwtService } from '@nestjs/jwt';
import type { Socket } from 'socket.io';
import type { JwtPayload } from './interfaces/jwt-payload.interface';

type WsNextFunction = (err?: Error) => void;

export type WsAuthMiddleware = (socket: Socket, next: WsNextFunction) => Promise<void>;

const logger = new Logger('WsAuthMiddleware');

export function extractHandshakeToken(socket: Socket): string | undefined {
  // handshake.auth is attacker-controlled JSON: token may be any type, and a
  // non-string here must not be able to throw (unhandled middleware rejections
  // kill the process on modern Node).
  const raw: unknown = socket.handshake.auth?.token;
  let token = typeof raw === 'string' ? raw : undefined;

  if (!token) {
    const header = socket.handshake.headers?.authorization;
    if (typeof header === 'string' && header.length > 0) {
      token = header;
    }
  }

  if (token?.startsWith('Bearer ')) {
    token = token.slice(7);
  }

  return token || undefined;
}

/**
 * Socket.io handshake middleware enforcing JWT auth at connection time.
 *
 * NestJS guards run only on message handlers, never on the connection
 * itself, so without this middleware anonymous sockets complete the
 * handshake and receive every room broadcast. Rejected sockets never
 * reach handleConnection; accepted ones carry the payload in
 * socket.data.user.
 */
export function createWsAuthMiddleware(
  jwtService: JwtService,
  configService: ConfigService,
): WsAuthMiddleware {
  return async (socket: Socket, next: WsNextFunction): Promise<void> => {
    // socket.io does not await or catch middleware rejections, so any throw
    // escaping this function becomes an unhandled rejection that can kill the
    // process — everything stays inside this try/catch.
    try {
      const token = extractHandshakeToken(socket);

      if (!token) {
        logger.warn(`Rejecting socket ${socket.id}: no token in handshake`);
        next(new Error('unauthorized'));
        return;
      }

      const secret =
        configService.get<string>('JWT_SECRET') ?? configService.get<string>('jwt.secret');

      if (!secret) {
        logger.error('JWT secret is not configured; rejecting socket connection');
        next(new Error('unauthorized'));
        return;
      }

      const payload = await jwtService.verifyAsync<JwtPayload>(token, { secret });
      socket.data.user = payload;
      next();
    } catch (error) {
      logger.warn(
        `Rejecting socket ${socket.id}: ${error instanceof Error ? error.message : 'invalid token'}`,
      );
      next(new Error('unauthorized'));
    }
  };
}
