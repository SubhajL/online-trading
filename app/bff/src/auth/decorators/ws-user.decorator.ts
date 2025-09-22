import { createParamDecorator, ExecutionContext } from '@nestjs/common';
import { Socket } from 'socket.io';
import type { JwtPayload } from '../interfaces/jwt-payload.interface';

export const WsUser = createParamDecorator(
  (data: keyof JwtPayload | undefined, ctx: ExecutionContext): JwtPayload | any => {
    const client = ctx.switchToWs().getClient<Socket>();
    const user = client.data.user as JwtPayload;

    return data ? user?.[data] : user;
  },
);