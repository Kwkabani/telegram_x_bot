import asyncio
import random
import logging

logger = logging.getLogger(__name__)


async def human_type(page, text: str, min_delay: float = 0.05, max_delay: float = 0.15):
    for char in text:
        await page.keyboard.type(char, delay=int(random.uniform(min_delay, max_delay) * 1000))
        if random.random() < 0.05:
            await asyncio.sleep(random.uniform(0.2, 0.5))


async def random_delay(min_sec: float = 0.5, max_sec: float = 2.0):
    await asyncio.sleep(random.uniform(min_sec, max_sec))
