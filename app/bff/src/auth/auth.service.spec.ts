import { Test, TestingModule } from '@nestjs/testing';
import { JwtService } from '@nestjs/jwt';
import { UnauthorizedException } from '@nestjs/common';
import { AuthService } from './auth.service';
import { ConfigService } from '@nestjs/config';

jest.mock('bcrypt');
import * as bcrypt from 'bcrypt';

describe('AuthService', () => {
  let service: AuthService;
  let jwtService: JwtService;

  const mockJwtService = {
    sign: jest.fn(),
    verify: jest.fn(),
  };

  const mockConfigService = {
    get: jest.fn(),
  };

  const mockUser = {
    id: 'user-123',
    username: 'testuser',
    password: '$2b$10$hashedpassword',
    roles: ['operator'],
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        AuthService,
        { provide: JwtService, useValue: mockJwtService },
        { provide: ConfigService, useValue: mockConfigService },
      ],
    }).compile();

    service = module.get<AuthService>(AuthService);
    jwtService = module.get<JwtService>(JwtService);

    mockConfigService.get.mockImplementation((key: string) => {
      const config: Record<string, string> = {
        JWT_EXPIRATION: '24h',
        JWT_REFRESH_EXPIRATION: '7d',
      };
      return config[key];
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('validateUser', () => {
    it('should return user without password when credentials are valid', async () => {
      (bcrypt.compare as jest.Mock).mockResolvedValue(true);

      const result = await service.validateUser('testuser', 'password123');

      expect(result).toEqual({
        id: mockUser.id,
        username: mockUser.username,
        roles: mockUser.roles,
      });
    });

    it('should throw UnauthorizedException when user not found', async () => {
      await expect(service.validateUser('unknown', 'password')).rejects.toThrow(
        UnauthorizedException,
      );
    });

    it('should throw UnauthorizedException when password is invalid', async () => {
      (bcrypt.compare as jest.Mock).mockResolvedValue(false);

      await expect(service.validateUser('testuser', 'wrongpassword')).rejects.toThrow(
        UnauthorizedException,
      );
    });
  });

  describe('login', () => {
    it('should return JWT tokens for valid user', async () => {
      const user = { id: 'user-123', username: 'testuser', roles: ['operator'] };
      const accessToken = 'access.token.here';
      const refreshToken = 'refresh.token.here';

      mockJwtService.sign.mockReturnValueOnce(accessToken).mockReturnValueOnce(refreshToken);

      const result = await service.login(user);

      expect(result).toEqual({ accessToken, refreshToken });
      expect(jwtService.sign).toHaveBeenCalledTimes(2);
      expect(jwtService.sign).toHaveBeenNthCalledWith(
        1,
        { sub: user.id, username: user.username, roles: user.roles },
        { expiresIn: '24h' },
      );
      expect(jwtService.sign).toHaveBeenNthCalledWith(
        2,
        { sub: user.id, username: user.username },
        { expiresIn: '7d' },
      );
    });
  });

  describe('refreshToken', () => {
    it('should return new access token for valid refresh token', async () => {
      const payload = { sub: 'user-123', username: 'testuser' };
      const newAccessToken = 'new.access.token';

      mockJwtService.verify.mockReturnValue(payload);
      mockJwtService.sign.mockReturnValue(newAccessToken);

      const result = await service.refreshToken('valid.refresh.token');

      expect(result).toEqual({ access_token: newAccessToken });
      expect(jwtService.verify).toHaveBeenCalledWith('valid.refresh.token');
    });

    it('should throw UnauthorizedException for invalid refresh token', async () => {
      mockJwtService.verify.mockImplementation(() => {
        throw new Error('Invalid token');
      });

      await expect(service.refreshToken('invalid.token')).rejects.toThrow(UnauthorizedException);
    });
  });

  describe('getProfile', () => {
    it('should return user profile for valid user id', async () => {
      const userId = 'user-123';

      const result = await service.getProfile(userId);

      expect(result).toEqual({
        id: 'user-123',
        username: 'testuser',
        roles: ['operator'],
        preferences: {},
      });
    });

    it('should throw UnauthorizedException for invalid user id', async () => {
      await expect(service.getProfile('invalid-id')).rejects.toThrow(UnauthorizedException);
    });
  });
});
