// No mocking - following the NO MOCK DATA principle
// Tests will use real database connections
// Database is already set up and running

// Set test environment
process.env.NODE_ENV = 'test';
process.env.POSTGRES_HOST = 'localhost';
process.env.POSTGRES_PORT = '5432';
process.env.POSTGRES_USER = 'trading_user';
process.env.POSTGRES_PASSWORD = 'your_secure_password_here';
process.env.POSTGRES_DB = 'trading_platform';
process.env.DATABASE_URL = 'postgresql://trading_user:your_secure_password_here@localhost:5432/trading_platform';

// Set Redis configuration
process.env.REDIS_HOST = 'localhost';
process.env.REDIS_PORT = '6379';
process.env.REDIS_URL = 'redis://localhost:6379/0';

// Set JWT secret for auth tests
process.env.JWT_SECRET = 'test_jwt_secret_key_minimum_32_characters';
process.env.JWT_EXPIRES_IN = '24h';
