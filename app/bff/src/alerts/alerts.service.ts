import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, FindManyOptions, ILike, Between } from 'typeorm';
import { Alert } from './entities/alert.entity';
import {
  AlertFilters,
  AlertStats,
  AlertType,
  AlertPriority,
  PaginatedAlertsDto,
  SearchAlertsDto,
  UpdateCountDto,
  UnreadCountDto,
  Alert as AlertDto,
} from './dto/alert.dto';

@Injectable()
export class AlertsService {
  constructor(
    @InjectRepository(Alert)
    private readonly alertRepository: Repository<Alert>,
  ) {}

  private toDto(entity: Alert): AlertDto {
    return {
      id: entity.id,
      type: entity.type,
      priority: entity.priority,
      title: entity.title,
      message: entity.message,
      data: entity.data,
      read: entity.read,
      createdAt: entity.createdAt.toISOString(),
      updatedAt: entity.updatedAt?.toISOString(),
    };
  }

  async findAll(page: number, limit: number, filters: AlertFilters): Promise<PaginatedAlertsDto> {
    const skip = (page - 1) * limit;
    const where: any = {};

    if (filters.type) where.type = filters.type;
    if (filters.priority) where.priority = filters.priority;
    if (filters.read !== undefined) where.read = filters.read;

    if (filters.fromDate && filters.toDate) {
      where.createdAt = Between(new Date(filters.fromDate), new Date(filters.toDate));
    }

    const [data, total] = await this.alertRepository.findAndCount({
      where,
      take: limit,
      skip,
      order: { createdAt: 'DESC' },
    });

    return { data: data.map((alert) => this.toDto(alert)), total, page, limit };
  }

  async findOne(id: string): Promise<AlertDto> {
    const alert = await this.alertRepository.findOne({ where: { id } });
    if (!alert) {
      throw new NotFoundException(`Alert with ID ${id} not found`);
    }
    return this.toDto(alert);
  }

  async markAsRead(id: string): Promise<AlertDto> {
    const alert = await this.alertRepository.findOne({ where: { id } });
    if (!alert) {
      throw new NotFoundException(`Alert with ID ${id} not found`);
    }
    alert.read = true;
    const updated = await this.alertRepository.save(alert);
    return this.toDto(updated);
  }

  async markAllAsRead(): Promise<UpdateCountDto> {
    const result = await this.alertRepository.update({ read: false }, { read: true });
    return { updated: result.affected || 0 };
  }

  async delete(id: string): Promise<void> {
    const alert = await this.findOne(id);
    await this.alertRepository.delete(id);
  }

  async getStats(): Promise<AlertStats> {
    // Get total and unread counts
    const [total, unread] = await Promise.all([
      this.alertRepository.count(),
      this.alertRepository.count({ where: { read: false } }),
    ]);

    // Get counts by type
    const typeStats = await this.alertRepository
      .createQueryBuilder('alert')
      .select('alert.type', 'type')
      .addSelect('COUNT(*)', 'count')
      .groupBy('alert.type')
      .getRawMany();

    const byType = typeStats.reduce(
      (acc, { type, count }) => {
        acc[type as AlertType] = parseInt(count);
        return acc;
      },
      {} as Record<AlertType, number>,
    );

    // Get counts by priority
    const priorityStats = await this.alertRepository
      .createQueryBuilder('alert')
      .select('alert.priority', 'priority')
      .addSelect('COUNT(*)', 'count')
      .groupBy('alert.priority')
      .getRawMany();

    const byPriority = priorityStats.reduce(
      (acc, { priority, count }) => {
        acc[priority as AlertPriority] = parseInt(count);
        return acc;
      },
      {} as Record<AlertPriority, number>,
    );

    // Ensure all types and priorities are included
    const allTypes: AlertType[] = ['order', 'position', 'decision', 'smc', 'error', 'info'];
    const allPriorities: AlertPriority[] = ['low', 'medium', 'high', 'critical'];

    allTypes.forEach((type) => {
      if (!byType[type]) byType[type] = 0;
    });

    allPriorities.forEach((priority) => {
      if (!byPriority[priority]) byPriority[priority] = 0;
    });

    return { total, unread, byType, byPriority };
  }

  async getUnreadCount(): Promise<UnreadCountDto> {
    const count = await this.alertRepository.count({ where: { read: false } });
    return { count };
  }

  async search(query: string, limit: number): Promise<SearchAlertsDto> {
    const [data, total] = await this.alertRepository
      .createQueryBuilder('alert')
      .where('alert.title ILIKE :query', { query: `%${query}%` })
      .orWhere('alert.message ILIKE :query', { query: `%${query}%` })
      .orderBy('alert.createdAt', 'DESC')
      .limit(limit)
      .getManyAndCount();

    return { data: data.map((alert) => this.toDto(alert)), total };
  }

  async export(format: 'csv' | 'json', filters: AlertFilters): Promise<Buffer> {
    const { data } = await this.findAll(1, 10000, filters); // Get all alerts with filters

    if (format === 'csv') {
      return this.exportToCsv(data);
    } else {
      return this.exportToJson(data);
    }
  }

  async create(
    createAlertDto: Omit<AlertDto, 'id' | 'createdAt' | 'updatedAt' | 'read'>,
  ): Promise<AlertDto> {
    const alert = this.alertRepository.create({
      ...createAlertDto,
      read: false,
    });
    const saved = await this.alertRepository.save(alert);
    return this.toDto(saved);
  }

  private exportToCsv(alerts: AlertDto[]): Buffer {
    const headers = 'id,type,priority,title,message,read,createdAt\n';
    const rows = alerts
      .map(
        (alert) =>
          `"${alert.id}","${alert.type}","${alert.priority}","${alert.title}","${alert.message}",${alert.read},"${alert.createdAt}"`,
      )
      .join('\n');

    return Buffer.from(headers + rows);
  }

  private exportToJson(alerts: AlertDto[]): Buffer {
    return Buffer.from(JSON.stringify({ alerts, exportDate: new Date().toISOString() }, null, 2));
  }
}
