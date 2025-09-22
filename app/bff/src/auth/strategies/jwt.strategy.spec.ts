import { ConfigService } from '@nestjs/config';
import { UnauthorizedException } from '@nestjs/common';
import { JwtStrategy } from './jwt.strategy';
import type { JwtPayload } from '../interfaces/jwt-payload.interface';

describe('JwtStrategy', () => {
  let strategy: JwtStrategy;
  let configService: ConfigService;

  beforeEach(async () => {
    const mockConfigService = {
      get: jest.fn((key: string) => {
        if (key === 'JWT_SECRET') return 'test-secret-key';
        return undefined;
      }),
    };

    configService = mockConfigService as any;
    strategy = new JwtStrategy(configService as any);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('validate', () => {
    it('should return user object for valid payload', async () => {
      const payload: JwtPayload = {
        sub: 'user-123',
        username: 'testuser',
        roles: ['operator'],
      };

      const result = await strategy.validate(payload);

      expect(result).toEqual({
        id: payload.sub,
        username: payload.username,
        roles: payload.roles,
      });
    });

    it('should throw UnauthorizedException when payload is missing sub', async () => {
      const payload = {
        username: 'testuser',
        roles: ['operator'],
      } as any;

      await expect(strategy.validate(payload)).rejects.toThrow(UnauthorizedException);
    });

    it('should throw UnauthorizedException when payload is missing username', async () => {
      const payload = {
        sub: 'user-123',
        roles: ['operator'],
      } as any;

      await expect(strategy.validate(payload)).rejects.toThrow(UnauthorizedException);
    });
  });
});
