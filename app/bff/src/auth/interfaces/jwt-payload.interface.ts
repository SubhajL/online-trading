export interface JwtPayload {
  sub: string; // user ID
  username: string;
  roles: string[];
  iat?: number;
  exp?: number;
}

export interface JwtTokens {
  accessToken: string;
  refreshToken: string;
}
