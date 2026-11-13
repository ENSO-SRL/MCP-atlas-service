import asyncio
from src.shared.database.session import get_db_session
from sqlalchemy import text

async def main():
    with open('docs/seed_padel_house_service.sql', 'r', encoding='utf-8') as f:
        content = f.read()

    # Split on comments and clean
    # The file has BEGIN; then ALTER TABLE statements, then DO $$ ... END $$;, then ALTER TABLE ENABLE, then COMMIT;
    # Let's execute using the raw connection so PL/pgSQL DO block runs as a whole
    async with get_db_session() as session:
        conn = await session.connection()
        raw_conn = await conn.get_raw_connection()
        # raw_conn is an asyncpg connection wrapper
        # Let's execute the full SQL script directly on the underlying asyncpg connection
        asyncpg_conn = raw_conn.driver_connection
        await asyncpg_conn.execute(content)
        print("Seed executed cleanly via asyncpg!")

if __name__ == "__main__":
    asyncio.run(main())

