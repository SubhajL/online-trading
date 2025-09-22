import { ExecutionContext } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { RolesGuard } from './roles.guard';
import type { Role } from '../types/role.type';

describe('RolesGuard', () => {
  let guard: RolesGuard;
  let reflector: Reflector;

  beforeEach(() => {
    reflector = new Reflector();
    guard = new RolesGuard(reflector);
  });

  describe('canActivate', () => {
    it('should return true when no required roles are set', () => {
      const mockContext = createMockContext();
      jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(undefined);

      const result = guard.canActivate(mockContext);

      expect(result).toBe(true);
    });

    it('should return true when user has required role', () => {
      const requiredRoles: Role[] = ['admin'];
      const mockContext = createMockContext({
        id: 'user-123',
        username: 'testuser',
        roles: ['admin', 'operator'],
      });

      jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(requiredRoles);

      const result = guard.canActivate(mockContext);

      expect(result).toBe(true);
    });

    it('should return true when user has at least one of the required roles', () => {
      const requiredRoles: Role[] = ['admin', 'operator'];
      const mockContext = createMockContext({
        id: 'user-123',
        username: 'testuser',
        roles: ['operator'],
      });

      jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(requiredRoles);

      const result = guard.canActivate(mockContext);

      expect(result).toBe(true);
    });

    it('should return false when user does not have any required roles', () => {
      const requiredRoles: Role[] = ['admin'];
      const mockContext = createMockContext({
        id: 'user-123',
        username: 'testuser',
        roles: ['viewer'],
      });

      jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(requiredRoles);

      const result = guard.canActivate(mockContext);

      expect(result).toBe(false);
    });

    it('should return false when user has no roles', () => {
      const requiredRoles: Role[] = ['admin'];
      const mockContext = createMockContext({
        id: 'user-123',
        username: 'testuser',
        roles: [],
      });

      jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(requiredRoles);

      const result = guard.canActivate(mockContext);

      expect(result).toBe(false);
    });

    it('should return false when there is no user in request', () => {
      const requiredRoles: Role[] = ['admin'];
      const mockContext = createMockContext(null);

      jest.spyOn(reflector, 'getAllAndOverride').mockReturnValue(requiredRoles);

      const result = guard.canActivate(mockContext);

      expect(result).toBe(false);
    });
  });
});

function createMockContext(user?: any): ExecutionContext {
  return {
    switchToHttp: () => ({
      getRequest: () => ({ user }),
    }),
    getHandler: jest.fn(),
    getClass: jest.fn(),
  } as unknown as ExecutionContext;
}
