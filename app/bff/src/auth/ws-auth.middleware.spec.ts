import { JwtService } from '@nestjs/jwt';
import { ConfigService } from '@nestjs/config';
import type { Socket } from 'socket.io';
import { createWsAuthMiddleware, extractHandshakeToken } from './ws-auth.middleware';

const JWT_SECRET = 'test-secret';
const VALID_PAYLOAD = { sub: 'user-1', username: 'trader', roles: ['operator'] };

function makeSocket(handshake: Partial<Socket['handshake']>): Socket {
  return {
    id: 'socket-1',
    handshake: { auth: {}, headers: {}, query: {}, ...handshake },
    data: {},
  } as unknown as Socket;
}

function makeConfigService(secret: string | null = JWT_SECRET): ConfigService {
  return {
    get: jest.fn((key: string) => (key === 'JWT_SECRET' && secret !== null ? secret : undefined)),
  } as unknown as ConfigService;
}

describe('extractHandshakeToken', () => {
  it('reads token from handshake.auth', () => {
    const socket = makeSocket({ auth: { token: 'abc' } });
    expect(extractHandshakeToken(socket)).toBe('abc');
  });

  it('falls back to Authorization header and strips Bearer prefix', () => {
    const socket = makeSocket({ headers: { authorization: 'Bearer xyz' } });
    expect(extractHandshakeToken(socket)).toBe('xyz');
  });

  it('does not read tokens from the query string', () => {
    const socket = makeSocket({ query: { token: 'leaky' } });
    expect(extractHandshakeToken(socket)).toBeUndefined();
  });

  it.each([[{}], [123], [['a']], [true]])(
    'treats non-string auth token %p as absent instead of throwing',
    (badToken) => {
      const socket = makeSocket({ auth: { token: badToken as never } });
      expect(extractHandshakeToken(socket)).toBeUndefined();
    },
  );

  it('treats a bare Bearer prefix as absent', () => {
    const socket = makeSocket({ headers: { authorization: 'Bearer ' } });
    expect(extractHandshakeToken(socket)).toBeUndefined();
  });
});

describe('createWsAuthMiddleware', () => {
  let jwtService: JwtService;

  beforeEach(() => {
    jwtService = new JwtService({ secret: JWT_SECRET });
  });

  it('sets socket.data.user and calls next() for a valid token', async () => {
    const token = jwtService.sign(VALID_PAYLOAD, { secret: JWT_SECRET });
    const middleware = createWsAuthMiddleware(jwtService, makeConfigService());
    const socket = makeSocket({ auth: { token } });
    const next = jest.fn();

    await middleware(socket, next);

    expect(next).toHaveBeenCalledWith();
    expect(socket.data.user).toMatchObject(VALID_PAYLOAD);
  });

  it('rejects a missing token with an unauthorized error', async () => {
    const middleware = createWsAuthMiddleware(jwtService, makeConfigService());
    const socket = makeSocket({});
    const next = jest.fn();

    await middleware(socket, next);

    expect(next).toHaveBeenCalledWith(expect.any(Error));
    expect(socket.data.user).toBeUndefined();
  });

  it('rejects an invalid token with an unauthorized error', async () => {
    const middleware = createWsAuthMiddleware(jwtService, makeConfigService());
    const socket = makeSocket({ auth: { token: 'not-a-jwt' } });
    const next = jest.fn();

    await middleware(socket, next);

    expect(next).toHaveBeenCalledWith(expect.any(Error));
    expect(socket.data.user).toBeUndefined();
  });

  it('rejects when the JWT secret is not configured', async () => {
    const token = jwtService.sign(VALID_PAYLOAD, { secret: JWT_SECRET });
    const middleware = createWsAuthMiddleware(jwtService, makeConfigService(null));
    const socket = makeSocket({ auth: { token } });
    const next = jest.fn();

    await middleware(socket, next);

    expect(next).toHaveBeenCalledWith(expect.any(Error));
  });

  it('rejects a non-string token with an unauthorized error instead of crashing', async () => {
    const middleware = createWsAuthMiddleware(jwtService, makeConfigService());
    const socket = makeSocket({ auth: { token: { $evil: true } as never } });
    const next = jest.fn();

    await expect(middleware(socket, next)).resolves.toBeUndefined();

    expect(next).toHaveBeenCalledTimes(1);
    expect(next).toHaveBeenCalledWith(expect.any(Error));
    expect(socket.data.user).toBeUndefined();
  });

  it('rejects an expired token', async () => {
    const token = jwtService.sign(VALID_PAYLOAD, { secret: JWT_SECRET, expiresIn: '-1s' });
    const middleware = createWsAuthMiddleware(jwtService, makeConfigService());
    const socket = makeSocket({ auth: { token } });
    const next = jest.fn();

    await middleware(socket, next);

    expect(next).toHaveBeenCalledWith(expect.any(Error));
    expect(socket.data.user).toBeUndefined();
  });
});
