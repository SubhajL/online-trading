import { Test, TestingModule } from '@nestjs/testing';
import { UnauthorizedException } from '@nestjs/common';
import { AuthController } from './auth.controller';
import { AuthService } from './auth.service';
import type { LoginDto } from './dto/login.dto';
import type { RefreshTokenDto } from './dto/refresh-token.dto';

describe('AuthController', () => {
  let controller: AuthController;
  let authService: AuthService;

  const mockAuthService = {
    validateUser: jest.fn(),
    login: jest.fn(),
    getProfile: jest.fn(),
    refreshToken: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [AuthController],
      providers: [
        {
          provide: AuthService,
          useValue: mockAuthService,
        },
      ],
    }).compile();

    controller = module.get<AuthController>(AuthController);
    authService = module.get<AuthService>(AuthService);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('login', () => {
    it('should return JWT token for valid credentials', async () => {
      const loginDto: LoginDto = {
        username: 'testuser',
        password: 'testpass',
      };

      const expectedToken = { access_token: 'jwt-token' };
      mockAuthService.validateUser.mockResolvedValue({
        id: 'user-123',
        username: 'testuser',
        roles: ['operator'],
      });
      mockAuthService.login.mockResolvedValue(expectedToken);

      const result = await controller.login(loginDto);

      expect(result).toEqual(expectedToken);
      expect(authService.validateUser).toHaveBeenCalledWith(loginDto.username, loginDto.password);
      expect(authService.login).toHaveBeenCalledWith({
        id: 'user-123',
        username: 'testuser',
        roles: ['operator'],
      });
    });

    it('should throw UnauthorizedException for invalid credentials', async () => {
      const loginDto: LoginDto = {
        username: 'testuser',
        password: 'wrongpass',
      };

      mockAuthService.validateUser.mockResolvedValue(null);

      await expect(controller.login(loginDto)).rejects.toThrow(UnauthorizedException);
      expect(authService.login).not.toHaveBeenCalled();
    });
  });

  describe('getProfile', () => {
    it('should return user profile', async () => {
      const user = {
        id: 'user-123',
        username: 'testuser',
        roles: ['operator'],
      };

      const expectedProfile = {
        id: 'user-123',
        username: 'testuser',
        roles: ['operator'],
        preferences: {},
      };

      mockAuthService.getProfile.mockResolvedValue(expectedProfile);

      const result = await controller.getProfile({ user });

      expect(result).toEqual(expectedProfile);
      expect(authService.getProfile).toHaveBeenCalledWith(user.id);
    });
  });

  describe('refreshToken', () => {
    it('should return new access token for valid refresh token', async () => {
      const refreshTokenDto: RefreshTokenDto = {
        refresh_token: 'valid-refresh-token',
      };

      const expectedResponse = { access_token: 'new-jwt-token' };
      mockAuthService.refreshToken.mockResolvedValue(expectedResponse);

      const result = await controller.refreshToken(refreshTokenDto);

      expect(result).toEqual(expectedResponse);
      expect(authService.refreshToken).toHaveBeenCalledWith(refreshTokenDto.refresh_token);
    });

    it('should throw UnauthorizedException for invalid refresh token', async () => {
      const refreshTokenDto: RefreshTokenDto = {
        refresh_token: 'invalid-refresh-token',
      };

      mockAuthService.refreshToken.mockRejectedValue(new UnauthorizedException());

      await expect(controller.refreshToken(refreshTokenDto)).rejects.toThrow(UnauthorizedException);
    });
  });

  describe('logout', () => {
    it('should return success message', async () => {
      const result = await controller.logout();

      expect(result).toEqual({ message: 'Logged out successfully' });
    });
  });
});
