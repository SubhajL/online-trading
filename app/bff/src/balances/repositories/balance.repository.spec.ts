import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { BalanceRepository } from './balance.repository';
import { BalanceEntity } from '../entities/balance-entity';
import { Repository } from 'typeorm';
import { Venue } from '../dto/get-balances.dto';

describe('BalanceRepository', () => {
  let balanceRepository: BalanceRepository;
  let mockRepository: Repository<BalanceEntity>;

  const mockQueryBuilder = {
    where: jest.fn().mockReturnThis(),
    andWhere: jest.fn().mockReturnThis(),
    orderBy: jest.fn().mockReturnThis(),
    addOrderBy: jest.fn().mockReturnThis(),
    getMany: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        BalanceRepository,
        {
          provide: getRepositoryToken(BalanceEntity),
          useValue: {
            createQueryBuilder: jest.fn(() => mockQueryBuilder),
          },
        },
      ],
    }).compile();

    balanceRepository = module.get<BalanceRepository>(BalanceRepository);
    mockRepository = module.get<Repository<BalanceEntity>>(getRepositoryToken(BalanceEntity));
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('findAll', () => {
    it('should find all non-zero balances', async () => {
      const mockBalances: BalanceEntity[] = [
        {
          asset: 'BTC',
          venue: 'SPOT',
          free: 1.5,
          locked: 0.5,
          total: 2.0,
          usdValue: 80000,
          updatedAt: new Date(),
        },
        {
          asset: 'USDT',
          venue: 'SPOT',
          free: 10000,
          locked: 0,
          total: 10000,
          usdValue: 10000,
          updatedAt: new Date(),
        },
      ];

      mockQueryBuilder.getMany.mockResolvedValue(mockBalances);

      const result = await balanceRepository.findAll();

      expect(mockRepository.createQueryBuilder).toHaveBeenCalledWith('balance');
      expect(mockQueryBuilder.where).toHaveBeenCalledWith('balance.total > :zero', { zero: 0 });
      expect(mockQueryBuilder.orderBy).toHaveBeenCalledWith('balance.venue', 'ASC');
      expect(mockQueryBuilder.addOrderBy).toHaveBeenCalledWith('balance.asset', 'ASC');
      expect(result).toEqual(mockBalances);
    });

    it('should filter by venue when provided', async () => {
      const mockBalances: BalanceEntity[] = [
        {
          asset: 'BTC',
          venue: 'USD_M',
          free: 0.1,
          locked: 0,
          total: 0.1,
          usdValue: 4000,
          updatedAt: new Date(),
        },
      ];

      mockQueryBuilder.getMany.mockResolvedValue(mockBalances);

      const result = await balanceRepository.findAll(Venue.USD_M);

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('balance.venue = :venue', {
        venue: 'USD_M',
      });
      expect(result).toEqual(mockBalances);
    });
  });
});
