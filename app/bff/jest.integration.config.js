module.exports = {
  moduleFileExtensions: ['js', 'json', 'ts'],
  rootDir: '.',
  testMatch: ['**/test/integration/**/*.spec.ts'],
  transform: {
    '^.+\\.(t|j)s$': 'ts-jest',
  },
  collectCoverageFrom: [
    'src/**/*.(t|j)s',
    '!src/**/*.spec.ts',
  ],
  coverageDirectory: './coverage/integration',
  testEnvironment: 'node',
  testTimeout: 30000, // 30 seconds for integration tests
  moduleNameMapper: {
    '^src/(.*)$': '<rootDir>/src/$1',
  },
};