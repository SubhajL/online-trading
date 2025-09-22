import { ExecutionContext } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { AuthGuard } from '@nestjs/passport';
import { JwtAuthGuard } from './jwt-auth.guard';

describe('JwtAuthGuard', () => {
  let guard: JwtAuthGuard;
  let reflector: Reflector;

  beforeEach(() => {
    reflector = new Reflector();
    guard = new JwtAuthGuard(reflector);
  });

  describe('canActivate', () => {
    it('should allow access when IS_PUBLIC_KEY is true', async () => {
      const mockContext = {
        getHandler: jest.fn(),
        getClass: jest.fn(),
      } as unknown as ExecutionContext;

      jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(true);

      const result = await guard.canActivate(mockContext);

      expect(result).toBe(true);
      expect(reflector.getAllAndOverride).toHaveBeenCalledWith('isPublic', [
        mockContext.getHandler(),
        mockContext.getClass(),
      ]);
    });

    it('should call parent canActivate when IS_PUBLIC_KEY is false', async () => {
      const mockContext = {
        getHandler: jest.fn(),
        getClass: jest.fn(),
      } as unknown as ExecutionContext;

      jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(false);
      const parentCanActivate = jest
        .spyOn(AuthGuard('jwt').prototype, 'canActivate')
        .mockReturnValue(true);

      const result = await guard.canActivate(mockContext);

      expect(result).toBe(true);
      expect(parentCanActivate).toHaveBeenCalledWith(mockContext);
    });

    it('should call parent canActivate when IS_PUBLIC_KEY is undefined', async () => {
      const mockContext = {
        getHandler: jest.fn(),
        getClass: jest.fn(),
      } as unknown as ExecutionContext;

      jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(undefined);
      const parentCanActivate = jest
        .spyOn(AuthGuard('jwt').prototype, 'canActivate')
        .mockReturnValue(false);

      const result = await guard.canActivate(mockContext);

      expect(result).toBe(false);
      expect(parentCanActivate).toHaveBeenCalledWith(mockContext);
    });
  });
});
