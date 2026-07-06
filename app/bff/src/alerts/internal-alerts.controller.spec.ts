import { IS_PUBLIC_KEY } from '../auth/decorators/public.decorator';
import { InternalAlertsController } from './internal-alerts.controller';

describe('InternalAlertsController', () => {
  it('is public so internal token auth can bypass the global JWT guard', () => {
    expect(Reflect.getMetadata(IS_PUBLIC_KEY, InternalAlertsController)).toBe(true);
  });
});
