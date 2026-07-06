import { Injectable, Logger } from '@nestjs/common';
import { RouterClientService, type ReconcileSummary } from '../router-client/router-client.service';
import { RouterReconcileSummaryDto, RouterSoakStatusDto } from './dto/soak-status.dto';

@Injectable()
export class SoakService {
  private readonly logger = new Logger(SoakService.name);

  constructor(private readonly routerClient: RouterClientService) {}

  async getStatus(): Promise<RouterSoakStatusDto> {
    const readiness = await this.routerClient.getReadiness();

    let reconcile: RouterSoakStatusDto['reconcile'] = { hasRun: false, unavailable: true };
    try {
      const status = await this.routerClient.getReconcileStatus();
      reconcile = {
        hasRun: status.has_run,
        lastRunAt: status.last_run_at,
        summary: status.summary ? mapSummary(status.summary) : undefined,
      };
    } catch (error) {
      // Readiness alone is still useful; surface reconcile as unavailable
      // rather than failing the whole panel.
      this.logger.warn(`Router reconcile status unavailable: ${error}`);
    }

    return { readiness, reconcile, checkedAt: new Date().toISOString() };
  }
}

function mapSummary(summary: ReconcileSummary): RouterReconcileSummaryDto {
  return {
    bracketsSwept: summary.brackets_swept,
    entriesChecked: summary.entries_checked,
    legsResolved: summary.legs_resolved,
    exitLegsUpdated: summary.exit_legs_updated,
    bracketsClosed: summary.brackets_closed,
    staleReserved: summary.stale_reserved,
    unrepairedLegs: summary.unrepaired_legs,
    errors: summary.errors,
  };
}
