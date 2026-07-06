import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { DataSource } from 'typeorm';

const REQUIRED_ALERT_TABLES = ['alerts', 'alert_snapshots'] as const;

@Injectable()
export class DatabaseSchemaVerifierService implements OnModuleInit {
  private readonly logger = new Logger(DatabaseSchemaVerifierService.name);

  constructor(private readonly dataSource: DataSource) {}

  async onModuleInit(): Promise<void> {
    const [row] = (await this.dataSource.query(
      `
        SELECT
          to_regclass('public.alerts') AS alerts,
          to_regclass('public.alert_snapshots') AS alert_snapshots
      `,
    )) as Array<Record<(typeof REQUIRED_ALERT_TABLES)[number], string | null>>;

    const missingTables = REQUIRED_ALERT_TABLES.filter((tableName) => !row?.[tableName]);
    if (missingTables.length > 0) {
      throw new Error(`Missing required BFF database tables: ${missingTables.join(', ')}`);
    }

    this.logger.log(`Verified required BFF database tables: ${REQUIRED_ALERT_TABLES.join(', ')}`);
  }
}
