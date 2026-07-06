import { SoakService } from './soak.service';
import type {
  ReconcileStatus,
  RouterClientService,
  RouterReadiness,
} from '../router-client/router-client.service';

function buildService(overrides: {
  readiness: RouterReadiness;
  reconcile?: () => Promise<ReconcileStatus>;
}) {
  const routerClient = {
    getReadiness: jest.fn().mockResolvedValue(overrides.readiness),
    getReconcileStatus: jest
      .fn()
      .mockImplementation(overrides.reconcile ?? (() => Promise.resolve({ has_run: false }))),
  };
  const service = new SoakService(routerClient as unknown as RouterClientService);
  return { service, routerClient };
}

describe('SoakService', () => {
  it('aggregates readiness and maps the reconcile summary to camelCase', async () => {
    const { service } = buildService({
      readiness: { ready: true, status: 'ready' },
      reconcile: () =>
        Promise.resolve({
          has_run: true,
          last_run_at: '2026-07-06T00:00:00Z',
          summary: {
            brackets_swept: 4,
            entries_checked: 2,
            legs_resolved: 1,
            exit_legs_updated: 3,
            brackets_closed: 1,
            stale_reserved: 0,
            unrepaired_legs: 2,
            errors: 0,
          },
        }),
    });

    const status = await service.getStatus();

    expect(status.readiness).toEqual({ ready: true, status: 'ready' });
    expect(status.reconcile).toEqual({
      hasRun: true,
      lastRunAt: '2026-07-06T00:00:00Z',
      summary: {
        bracketsSwept: 4,
        entriesChecked: 2,
        legsResolved: 1,
        exitLegsUpdated: 3,
        bracketsClosed: 1,
        staleReserved: 0,
        unrepairedLegs: 2,
        errors: 0,
      },
    });
    expect(typeof status.checkedAt).toBe('string');
  });

  it('marks reconcile unavailable but still returns readiness when the reconcile query fails', async () => {
    const { service } = buildService({
      readiness: { ready: false, status: 'reconciling' },
      reconcile: () => Promise.reject(new Error('router 500')),
    });

    const status = await service.getStatus();

    expect(status.readiness).toEqual({ ready: false, status: 'reconciling' });
    expect(status.reconcile).toEqual({ hasRun: false, unavailable: true });
  });
});
