import os
import asyncio
from typing import Dict, Any, Optional
import asyncpg
from asyncpg import Pool


def get_pool_config() -> Dict[str, Any]:
    """Get database pool configuration from environment variables"""
    return {
        "max_size": int(os.getenv("POSTGRES_MAX_CONNECTIONS", "20")),
        "min_size": int(os.getenv("POSTGRES_MIN_CONNECTIONS", "5")),
        "command_timeout": float(os.getenv("POSTGRES_IDLE_TIMEOUT", "30000")) / 1000,  # ms to seconds
        "timeout": float(os.getenv("POSTGRES_CONNECTION_TIMEOUT", "60000")) / 1000,  # ms to seconds
    }


async def create_pool(database_url: str) -> Pool:
    """Create a connection pool with configuration from environment"""
    config = get_pool_config()
    
    pool = await asyncpg.create_pool(
        database_url,
        min_size=config["min_size"],
        max_size=config["max_size"],
        command_timeout=config["command_timeout"],
        timeout=config["timeout"],
    )
    
    return pool


class ConnectionManager:
    """Manages database connections and pools"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[Pool] = None
    
    async def initialize(self) -> None:
        """Initialize the connection pool"""
        if self.pool is None:
            self.pool = await create_pool(self.database_url)
    
    async def close(self) -> None:
        """Close the connection pool"""
        if self.pool:
            await self.pool.close()
            self.pool = None
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query and return the result"""
        if not self.pool:
            await self.initialize()
        
        async with self.pool.acquire() as conn:
            result = await conn.execute(query, *args)
            return result
    
    async def fetch(self, query: str, *args) -> list:
        """Fetch rows from a query"""
        if not self.pool:
            await self.initialize()
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return rows
    
    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch a single row from a query"""
        if not self.pool:
            await self.initialize()
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return row
