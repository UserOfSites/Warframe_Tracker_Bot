import asyncio
import logging

from titania.bot import TitaniaBot
from titania.config import Config
from titania.data.factory import build_data_source
from titania.storage.db import Database


def main() -> None:
    config = Config()  # type: ignore[call-arg]
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_run(config))


async def _run(config: Config) -> None:
    db = Database(config.db_path)
    await db.connect()
    try:
        async with build_data_source(config) as data_source:
            bot = TitaniaBot(config=config, data_source=data_source, db=db)
            await bot.start(config.discord_token)
    finally:
        await db.close()


if __name__ == "__main__":
    main()
