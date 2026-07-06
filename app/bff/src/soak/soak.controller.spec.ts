import { GUARDS_METADATA } from '@nestjs/common/constants';
import { SoakController } from './soak.controller';
import { SoakService } from './soak.service';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import type { RouterSoakStatusDto } from './dto/soak-status.dto';

describe('SoakController', () => {
  it('is protected by JwtAuthGuard', () => {
    const guards = Reflect.getMetadata(GUARDS_METADATA, SoakController) as unknown[];
    expect(guards).toEqual(expect.arrayContaining([JwtAuthGuard]));
  });

  it('returns the router soak status from SoakService', async () => {
    const status: RouterSoakStatusDto = {
      readiness: { ready: true, status: 'ready' },
      reconcile: { hasRun: true },
      checkedAt: '2026-07-06T00:00:00.000Z',
    };
    const soakService = { getStatus: jest.fn().mockResolvedValue(status) };
    const controller = new SoakController(soakService as unknown as SoakService);

    await expect(controller.getStatus()).resolves.toBe(status);
    expect(soakService.getStatus).toHaveBeenCalledTimes(1);
  });
});
