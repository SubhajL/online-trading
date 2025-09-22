import { Test, TestingModule } from '@nestjs/testing';
import { BalancesService } from './balances.service';
import { BalanceRepository } from './repositories/balance.repository';
import { BalanceEntity } from './entities/balance-entity';
import { Venue } from './dto/get-balances.dto';

describe('BalancesService', () => {
  let service: BalancesService;
  let balanceRepository: BalanceRepository;

  const mockBalanceEntities: BalanceEntity[] = [
    {
      asset: 'BTC',
      venue: 'SPOT',
      free: 1.5,
      locked: 0.5,
      total: 2.0,
      usdValue: 90000,
      updatedAt: new Date(),
    } as BalanceEntity,
    {
      asset: 'USDT',
      venue: 'SPOT',
      free: 10000,
      locked: 5000,
      total: 15000,
      usdValue: 15000,
      updatedAt: new Date(),
    } as BalanceEntity,
    {
      asset: 'BTC',
      venue: 'USD_M',
      free: 0.5,
      locked: 0.1,
      total: 0.6,
      usdValue: 27000,
      updatedAt: new Date(),
    } as BalanceEntity,
    {
      asset: 'USDT',
      venue: 'USD_M',
      free: 20000,
      locked: 3000,
      total: 23000,
      usdValue: 23000,
      updatedAt: new Date(),
    } as BalanceEntity,
  ];

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        BalancesService,
        {
          provide: BalanceRepository,
          useValue: {
            findAll: jest.fn(),
          },
        },
      ],
    }).compile();

    service = module.get<BalancesService>(BalancesService);
    balanceRepository = module.get<BalanceRepository>(BalanceRepository);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('getBalances', () => {
    it('fetches all balances from repository', async () => {
      jest.spyOn(balanceRepository, 'findAll').mockResolvedValueOnce(mockBalanceEntities);

      const result = await service.getBalances();

      expect(balanceRepository.findAll).toHaveBeenCalledWith(undefined);
      expect(result).toHaveLength(4);
      expect(result[0]).toMatchObject({
        asset: 'BTC',
        venue: 'SPOT',
        free: 1.5,
        locked: 0.5,
        total: 2.0,
        usdValue: 90000,
      });
    });

    it('filters by venue when specified', async () => {
      const spotEntities = mockBalanceEntities.filter((e) => e.venue === 'SPOT');
      jest.spyOn(balanceRepository, 'findAll').mockResolvedValueOnce(spotEntities);

      const spotResult = await service.getBalances(Venue.SPOT);

      expect(balanceRepository.findAll).toHaveBeenCalledWith(Venue.SPOT);
      expect(spotResult).toHaveLength(2);
      expect(spotResult.every((b) => b.venue === 'SPOT')).toBe(true);
    });

    it('returns balances from both venues', async () => {
      jest.spyOn(balanceRepository, 'findAll').mockResolvedValueOnce(mockBalanceEntities);

      const result = await service.getBalances();

      const btcBalances = result.filter((b) => b.asset === 'BTC');
      expect(btcBalances).toHaveLength(2);
      expect(btcBalances.find((b) => b.venue === 'SPOT')).toBeDefined();
      expect(btcBalances.find((b) => b.venue === 'USD_M')).toBeDefined();
    });

    it('returns empty array when no balances exist', async () => {
      jest.spyOn(balanceRepository, 'findAll').mockResolvedValueOnce([]);

      const result = await service.getBalances();

      expect(result).toHaveLength(0);
    });

    it('handles null USD values correctly', async () => {
      const entitiesWithNullUsd = [
        {
          ...mockBalanceEntities[0],
          usdValue: null,
        } as BalanceEntity,
      ];

      jest.spyOn(balanceRepository, 'findAll').mockResolvedValueOnce(entitiesWithNullUsd);

      const result = await service.getBalances();

      expect(result[0].usdValue).toBeNull();
    });
  });
});
