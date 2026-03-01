Create and apply a database migration: $ARGUMENTS

## Migration Process

### Step 1: Create Migration File
```bash
cd app/engine
alembic revision --autogenerate -m "$ARGUMENTS"
```

### Step 2: Review Generated Migration
- Open the generated file in `app/engine/migrations/versions/`
- Verify the `upgrade()` function is correct
- Verify the `downgrade()` function properly reverses changes
- Check for data migrations if needed

### Step 3: Test Migration Locally
```bash
# Apply migration
make db-migrate

# Verify schema
PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -c "\dt"
```

### Step 4: Test Downgrade
```bash
cd app/engine
alembic downgrade -1
alembic upgrade head
```

### Step 5: Run Tests
```bash
# Integration tests touch the database
pytest app/engine/tests/integration/ -v -m integration
```

## Safety Checklist

- [ ] Migration is reversible (has proper downgrade)
- [ ] No data loss in existing tables
- [ ] Indexes added for new foreign keys
- [ ] Large tables use batch operations
- [ ] Migration tested locally
- [ ] Downgrade tested locally

## CRITICAL WARNINGS

- **NEVER** run migrations on production without approval
- **ALWAYS** backup database before production migrations
- **NEVER** use `synchronize: true` in TypeORM
- **ALWAYS** review generated SQL before applying

## Environment Variables Needed
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=trading_platform
POSTGRES_USER=trading_user
POSTGRES_PASSWORD=<from .env>
```
