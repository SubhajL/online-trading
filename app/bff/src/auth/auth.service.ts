import { Injectable, UnauthorizedException } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { ConfigService } from '@nestjs/config';
import * as bcrypt from 'bcrypt';
import { JwtPayload, JwtTokens } from './interfaces/jwt-payload.interface';

interface User {
  id: string;
  username: string;
  password: string;
  roles: string[];
}

@Injectable()
export class AuthService {
  private readonly users: User[] = [
    {
      id: 'user-123',
      username: 'testuser',
      password: '$2b$10$hashedpassword',
      roles: ['operator'],
    },
    {
      id: 'user-456',
      username: 'admin',
      password: '$2b$10$KIKhxW5lMQPC1svPLAcrZeP/oLhV5Dw7F8PTVm08r6oNSJzJl8jGe', // password: admin123
      roles: ['admin', 'operator'],
    },
    {
      id: 'user-789',
      username: 'trader@test.com',
      password: '$2b$10$PjNyJWip7IMwgE/rC1ZzjOHuH7uopLRUf3Eb82luMGCECjUVyDk8e', // password: Password123
      roles: ['operator'],
    },
  ];

  constructor(
    private readonly jwtService: JwtService,
    private readonly configService: ConfigService,
  ) {}

  async validateUser(username: string, password: string): Promise<Omit<User, 'password'>> {
    const user = this.users.find((u) => u.username === username);
    if (!user) {
      throw new UnauthorizedException('Invalid credentials');
    }

    const isPasswordValid = await bcrypt.compare(password, user.password);
    if (!isPasswordValid) {
      throw new UnauthorizedException('Invalid credentials');
    }

    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { password: _password, ...result } = user;
    return result;
  }

  async login(user: Omit<User, 'password'>, rememberMe = true): Promise<JwtTokens> {
    const payload: JwtPayload = {
      sub: user.id,
      username: user.username,
      roles: user.roles,
    };

    // Extended expiry for Remember Me: 30 days vs 24 hours
    const accessExpiry = rememberMe
      ? this.configService.get<string>('JWT_REMEMBER_EXPIRATION', '30d')
      : this.configService.get<string>('JWT_EXPIRATION', '24h');

    const refreshExpiry = rememberMe
      ? this.configService.get<string>('JWT_REMEMBER_REFRESH_EXPIRATION', '60d')
      : this.configService.get<string>('JWT_REFRESH_EXPIRATION', '7d');

    const accessToken = this.jwtService.sign(payload, {
      expiresIn: accessExpiry,
    });

    const refreshToken = this.jwtService.sign(
      { sub: user.id, username: user.username },
      {
        expiresIn: refreshExpiry,
      },
    );

    return { accessToken, refreshToken };
  }

  async refreshToken(refreshToken: string): Promise<{ access_token: string }> {
    try {
      const payload = this.jwtService.verify<{ sub: string; username: string }>(refreshToken);

      const user = this.users.find((u) => u.id === payload.sub);
      if (!user) {
        throw new UnauthorizedException('Invalid refresh token');
      }

      const newPayload: JwtPayload = {
        sub: user.id,
        username: user.username,
        roles: user.roles,
      };

      const accessToken = this.jwtService.sign(newPayload, {
        expiresIn: this.configService.get<string>('JWT_EXPIRATION', '24h'),
      });

      return { access_token: accessToken };
    } catch {
      throw new UnauthorizedException('Invalid refresh token');
    }
  }

  async getProfile(
    userId: string,
  ): Promise<{ id: string; username: string; roles: string[]; preferences: any }> {
    const user = this.users.find((u) => u.id === userId);
    if (!user) {
      throw new UnauthorizedException('User not found');
    }

    return {
      id: user.id,
      username: user.username,
      roles: user.roles,
      preferences: {},
    };
  }
}
