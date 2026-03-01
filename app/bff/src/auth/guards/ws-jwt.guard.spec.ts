import { Test, TestingModule } from '@nestjs/testing';
import { ExecutionContext } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { ConfigService } from '@nestjs/config';
import { WsJwtGuard } from './ws-jwt.guard';
import { Socket } from 'socket.io';
import type { JwtPayload } from '../interfaces/jwt-payload.interface';

describe('WsJwtGuard', () => {
  let guard: WsJwtGuard;
  let jwtService: JwtService;
  let configService: ConfigService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        WsJwtGuard,
        {
          provide: JwtService,
          useValue: {
            verifyAsync: jest.fn(),
          },
        },
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn(),
          },
        },
      ],
    }).compile();

    guard = module.get<WsJwtGuard>(WsJwtGuard);
    jwtService = module.get<JwtService>(JwtService);
    configService = module.get<ConfigService>(ConfigService);
  });

  const createMockExecutionContext = (token?: string): ExecutionContext => {
    const mockSocket = {
      handshake: {
        auth: token ? { token } : {},
        query: token ? {} : {},
      },
      data: {},
    } as unknown as Socket;

    return {
      switchToWs: jest.fn().mockReturnValue({
        getClient: jest.fn().mockReturnValue(mockSocket),
      }),
    } as unknown as ExecutionContext;
  };

  describe('canActivate', () => {
    it('should return true when valid JWT token is provided in handshake auth', async () => {
      const mockPayload: JwtPayload = {
        sub: 'user-123',
        username: 'testuser',
        roles: ['operator'],
      };
      const mockToken = 'valid-jwt-token';
      const mockSecret = 'test-secret';

      jest.spyOn(configService, 'get').mockImplementation((key: string) => {
        if (key === 'JWT_SECRET') return mockSecret;
        return undefined;
      });
      jest.spyOn(jwtService, 'verifyAsync').mockResolvedValue(mockPayload);

      const context = createMockExecutionContext(mockToken);
      const result = await guard.canActivate(context);

      expect(result).toBe(true);
      expect(configService.get).toHaveBeenCalledWith('JWT_SECRET');
      expect(jwtService.verifyAsync).toHaveBeenCalledWith(mockToken, { secret: mockSecret });

      const client = context.switchToWs().getClient<Socket>();
      expect(client.data.user).toEqual(mockPayload);
    });

    it('should check query params when no token in handshake auth', async () => {
      const mockPayload: JwtPayload = {
        sub: 'user-123',
        username: 'testuser',
        roles: ['operator'],
      };
      const mockToken = 'valid-jwt-token';
      const mockSecret = 'test-secret';

      const mockSocket = {
        handshake: {
          auth: {},
          query: { token: mockToken },
        },
        data: {},
      } as unknown as Socket;

      const context = {
        switchToWs: jest.fn().mockReturnValue({
          getClient: jest.fn().mockReturnValue(mockSocket),
        }),
      } as unknown as ExecutionContext;

      jest.spyOn(configService, 'get').mockImplementation((key: string) => {
        if (key === 'JWT_SECRET') return mockSecret;
        return undefined;
      });
      jest.spyOn(jwtService, 'verifyAsync').mockResolvedValue(mockPayload);

      const result = await guard.canActivate(context);

      expect(result).toBe(true);
      expect(configService.get).toHaveBeenCalledWith('JWT_SECRET');
      expect(jwtService.verifyAsync).toHaveBeenCalledWith(mockToken, { secret: mockSecret });
      expect(mockSocket.data.user).toEqual(mockPayload);
    });

    it('should return false when no token is provided', async () => {
      const mockSocket = {
        handshake: {
          auth: {},
          query: {},
        },
        data: {},
      } as unknown as Socket;

      const context = {
        switchToWs: jest.fn().mockReturnValue({
          getClient: jest.fn().mockReturnValue(mockSocket),
        }),
      } as unknown as ExecutionContext;

      const result = await guard.canActivate(context);

      expect(result).toBe(false);
      expect(jwtService.verifyAsync).not.toHaveBeenCalled();
    });

    it('should return false when token verification fails', async () => {
      const mockToken = 'invalid-jwt-token';
      const mockSecret = 'test-secret';

      jest.spyOn(configService, 'get').mockImplementation((key: string) => {
        if (key === 'JWT_SECRET') return mockSecret;
        return undefined;
      });
      jest.spyOn(jwtService, 'verifyAsync').mockRejectedValue(new Error('Invalid token'));

      const context = createMockExecutionContext(mockToken);
      const result = await guard.canActivate(context);

      expect(result).toBe(false);
      expect(configService.get).toHaveBeenCalledWith('JWT_SECRET');
      expect(jwtService.verifyAsync).toHaveBeenCalledWith(mockToken, { secret: mockSecret });
    });

    it('should return false when token has expired', async () => {
      const mockToken = 'expired-jwt-token';
      const mockSecret = 'test-secret';

      jest.spyOn(configService, 'get').mockImplementation((key: string) => {
        if (key === 'JWT_SECRET') return mockSecret;
        return undefined;
      });
      jest
        .spyOn(jwtService, 'verifyAsync')
        .mockRejectedValue(new Error('TokenExpiredError: jwt expired'));

      const context = createMockExecutionContext(mockToken);
      const result = await guard.canActivate(context);

      expect(result).toBe(false);
    });

    it('should handle Bearer token format', async () => {
      const mockPayload: JwtPayload = {
        sub: 'user-123',
        username: 'testuser',
        roles: ['operator'],
      };
      const mockToken = 'Bearer valid-jwt-token';
      const mockSecret = 'test-secret';

      jest.spyOn(configService, 'get').mockImplementation((key: string) => {
        if (key === 'JWT_SECRET') return mockSecret;
        return undefined;
      });
      jest.spyOn(jwtService, 'verifyAsync').mockResolvedValue(mockPayload);

      const context = createMockExecutionContext(mockToken);
      const result = await guard.canActivate(context);

      expect(result).toBe(true);
      expect(configService.get).toHaveBeenCalledWith('JWT_SECRET');
      expect(jwtService.verifyAsync).toHaveBeenCalledWith('valid-jwt-token', {
        secret: mockSecret,
      });
    });

    it('should fall back to legacy jwt.secret when JWT_SECRET is missing', async () => {
      const mockPayload: JwtPayload = {
        sub: 'user-123',
        username: 'testuser',
        roles: ['operator'],
      };
      const mockToken = 'valid-jwt-token';
      const mockSecret = 'legacy-test-secret';

      jest.spyOn(configService, 'get').mockImplementation((key: string) => {
        if (key === 'JWT_SECRET') return undefined;
        if (key === 'jwt.secret') return mockSecret;
        return undefined;
      });
      jest.spyOn(jwtService, 'verifyAsync').mockResolvedValue(mockPayload);

      const context = createMockExecutionContext(mockToken);
      const result = await guard.canActivate(context);

      expect(result).toBe(true);
      expect(configService.get).toHaveBeenCalledWith('JWT_SECRET');
      expect(configService.get).toHaveBeenCalledWith('jwt.secret');
      expect(jwtService.verifyAsync).toHaveBeenCalledWith(mockToken, { secret: mockSecret });
    });
  });
});
