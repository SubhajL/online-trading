import { IsEnum, IsOptional, IsBoolean, IsString, IsDateString } from 'class-validator';

export type AlertType = 'order' | 'position' | 'decision' | 'smc' | 'error' | 'info';
export type AlertPriority = 'low' | 'medium' | 'high' | 'critical';

export class Alert {
  id: string;
  type: AlertType;
  priority: AlertPriority;
  title: string;
  message: string;
  data?: Record<string, unknown>;
  read: boolean;
  createdAt: string;
  updatedAt?: string;
}

export class AlertFilters {
  @IsOptional()
  @IsEnum(['order', 'position', 'decision', 'smc', 'error', 'info'])
  type?: AlertType;

  @IsOptional()
  @IsEnum(['low', 'medium', 'high', 'critical'])
  priority?: AlertPriority;

  @IsOptional()
  @IsBoolean()
  read?: boolean;

  @IsOptional()
  @IsDateString()
  fromDate?: string;

  @IsOptional()
  @IsDateString()
  toDate?: string;

  @IsOptional()
  @IsString()
  search?: string;
}

export class AlertStats {
  total: number;
  unread: number;
  byType: Record<AlertType, number>;
  byPriority: Record<AlertPriority, number>;
}

export class PaginatedAlertsDto {
  data: Alert[];
  total: number;
  page: number;
  limit: number;
}

export class SearchAlertsDto {
  data: Alert[];
  total: number;
}

export class UpdateCountDto {
  updated: number;
}

export class UnreadCountDto {
  count: number;
}
