"""
YouTube Traffic Generator - Simulates realistic YouTube browsing behavior
"""
import asyncio
import logging
import random
import time
from typing import Dict, Any, List, Optional
import aiohttp
from .base import TrafficGenerator
from .interface_binding import SourceIPBoundConnector

logger = logging.getLogger(__name__)


class YouTubeTrafficGenerator(TrafficGenerator):
    """
    Generates traffic that mimics YouTube browsing behavior.

    Simulates realistic YouTube usage by fetching pages, thumbnails, and content
    without actually downloading video streams. Should trigger "youtube" classification
    in Ruckus One via domain/SSL fingerprinting.

    Config:
        watch_duration_min: Minimum watch time in seconds (default: 300 = 5 min)
        watch_duration_max: Maximum watch time in seconds (default: 1800 = 30 min)
        pause_between_min: Minimum pause between videos (default: 10)
        pause_between_max: Maximum pause between videos (default: 60)
        browse_intensity: "light", "medium", "heavy" (default: "medium")
    """

    # Search terms for realistic browsing
    SEARCH_TERMS = [
        "music", "gaming", "news", "cooking", "travel", "tech reviews",
        "how to", "funny videos", "sports highlights", "movie trailers",
        "vlogs", "tutorials", "product reviews", "documentaries",
    ]

    # Trending categories
    TRENDING_CATEGORIES = [
        "music", "gaming", "news", "movies", "sports", "learning",
    ]

    # Popular channels for browsing
    POPULAR_CHANNELS = [
        "UC-lHJZR3Gqxm24_Vd_AJ5Yw",  # PewDiePie
        "UCX6OQ3DkcsbYNE6H8uQQuVA",  # MrBeast
        "UCbCmjCuTUZos6Inko4u57UQ",  # Cocomelon
        "UCpko_-a4wgz2u_DgDgd9fqA",  # WWE
        "UCq-Fj5jknLsUf-MWSy4_brA",  # T-Series
    ]

    def __init__(self, interface: str, config: Dict[str, Any], mock_mode: bool = False, app_config=None):
        super().__init__(interface, config, mock_mode)

        # Set timeout from app config or use default
        if app_config:
            self.api_timeout = app_config.youtube_timeout
        else:
            self.api_timeout = 30

        self.watch_duration_min = config.get("watch_duration_min", 300)  # 5 min
        self.watch_duration_max = config.get("watch_duration_max", 1800)  # 30 min
        self.pause_between_min = config.get("pause_between_min", 10)
        self.pause_between_max = config.get("pause_between_max", 60)
        self.browse_intensity = config.get("browse_intensity", "medium")
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (X11; Linux armv7l) WiPi/1.0"
        )

        self.stats = {
            "pages_fetched": 0,
            "videos_browsed": 0,
            "watch_time_seconds": 0,
            "bytes_transferred": 0,
            "current_session": None,
        }

    def get_type(self) -> str:
        return "youtube"

    async def _generate_traffic(self) -> None:
        """Main traffic generation loop - simulate YouTube browsing sessions"""
        logger.info(
            f"Starting YouTube browsing on {self.interface} "
            f"(intensity: {self.browse_intensity}, watch: {self.watch_duration_min}-{self.watch_duration_max}s)"
        )

        while self.active:
            try:
                # Simulate browsing YouTube homepage/trending
                await self._browse_homepage()

                # Pick a video and "watch" it (browse video page + interactions)
                await self._browse_video()

                self.stats["videos_browsed"] += 1

                # Pause between videos (user browsing, deciding what to watch next)
                pause_time = random.randint(self.pause_between_min, self.pause_between_max)
                logger.debug(f"Pausing {pause_time}s between videos on {self.interface}")
                await asyncio.sleep(pause_time)

            except Exception as e:
                logger.error(f"Error in YouTube traffic generation on {self.interface}: {e}")
                await asyncio.sleep(60)  # Wait before retry

    async def _browse_homepage(self) -> None:
        """Simulate browsing YouTube homepage, trending, subscriptions"""
        if self.mock_mode:
            logger.debug(f"[MOCK] Would browse YouTube homepage on {self.interface}")
            await asyncio.sleep(random.uniform(2, 5))
            return

        logger.debug(f"Browsing YouTube homepage on {self.interface}")

        try:
            connector = await SourceIPBoundConnector.create_for_interface(self.interface)
            timeout = aiohttp.ClientTimeout(total=self.api_timeout)
            headers = {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
            }

            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                # Browse homepage
                await self._fetch_page(session, "https://www.youtube.com", headers)
                await asyncio.sleep(random.uniform(1, 3))

                # Random activity based on intensity
                if self.browse_intensity in ["medium", "heavy"]:
                    # Browse trending
                    category = random.choice(self.TRENDING_CATEGORIES)
                    await self._fetch_page(
                        session,
                        f"https://www.youtube.com/feed/trending?bp=4gINGgt5dG1hX2NoYXJ0cw%3D%3D",
                        headers
                    )
                    await asyncio.sleep(random.uniform(1, 2))

                if self.browse_intensity == "heavy":
                    # Browse a channel
                    channel = random.choice(self.POPULAR_CHANNELS)
                    await self._fetch_page(
                        session,
                        f"https://www.youtube.com/channel/{channel}",
                        headers
                    )
                    await asyncio.sleep(random.uniform(1, 2))

                    # Perform a search
                    search_term = random.choice(self.SEARCH_TERMS)
                    await self._fetch_page(
                        session,
                        f"https://www.youtube.com/results?search_query={search_term.replace(' ', '+')}",
                        headers
                    )
                    await asyncio.sleep(random.uniform(1, 2))

        except Exception as e:
            logger.debug(f"Error browsing YouTube homepage: {e}")

    async def _fetch_page(self, session: aiohttp.ClientSession, url: str, headers: Dict[str, str]) -> int:
        """Fetch a page and return bytes transferred"""
        try:
            async with session.get(url, headers=headers) as response:
                data = await response.read()
                bytes_transferred = len(data)

                logger.debug(
                    f"Fetched {url}: {response.status} ({bytes_transferred} bytes)"
                )

                self.stats["pages_fetched"] += 1
                self.stats["bytes_transferred"] += bytes_transferred

                return bytes_transferred
        except Exception as e:
            logger.debug(f"Error fetching {url}: {e}")
            return 0

    async def _browse_video(self) -> None:
        """Simulate browsing/watching a YouTube video page"""
        # Random watch duration
        watch_duration = random.randint(self.watch_duration_min, self.watch_duration_max)

        if self.mock_mode:
            logger.info(
                f"[MOCK] Would browse YouTube video on {self.interface} ({watch_duration}s)"
            )
            await asyncio.sleep(watch_duration)
            self.stats["watch_time_seconds"] += watch_duration
            return

        # Generate a random video ID (11 chars, YouTube format)
        video_id = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-', k=11))

        logger.info(
            f"Browsing YouTube video on {self.interface}: {watch_duration}s session"
        )

        self.stats["current_session"] = {
            "video_id": video_id,
            "duration": watch_duration,
            "started_at": time.time(),
        }

        try:
            start_time = time.time()
            end_time = start_time + watch_duration

            connector = await SourceIPBoundConnector.create_for_interface(self.interface)
            timeout = aiohttp.ClientTimeout(total=self.api_timeout)
            headers = {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Referer": "https://www.youtube.com",
            }

            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                # Fetch video page
                await self._fetch_page(
                    session,
                    f"https://www.youtube.com/watch?v={video_id}",
                    headers
                )
                await asyncio.sleep(random.uniform(2, 5))

                # Simulate periodic interactions during "watch" time
                interaction_count = 0
                while self.active and time.time() < end_time:
                    # Wait for a portion of watch time
                    wait_time = min(
                        random.randint(30, 120),
                        int(end_time - time.time())
                    )
                    if wait_time <= 0:
                        break

                    await asyncio.sleep(wait_time)

                    if time.time() >= end_time:
                        break

                    # Periodic interaction based on intensity
                    interaction_count += 1

                    if self.browse_intensity == "heavy" or (self.browse_intensity == "medium" and interaction_count % 2 == 0):
                        # Fetch related content
                        interaction = random.choice([
                            "comments",
                            "channel",
                            "related",
                        ])

                        if interaction == "comments":
                            # Fetch comments (would normally be async JS request)
                            logger.debug(f"Fetching comments for {video_id}")
                            await asyncio.sleep(random.uniform(0.5, 1.5))

                        elif interaction == "channel":
                            # Visit channel page
                            channel_id = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-', k=24))
                            await self._fetch_page(
                                session,
                                f"https://www.youtube.com/channel/{channel_id}",
                                headers
                            )
                            await asyncio.sleep(random.uniform(1, 3))

                        elif interaction == "related":
                            # Click on related video (fetch another video page)
                            related_id = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-', k=11))
                            await self._fetch_page(
                                session,
                                f"https://www.youtube.com/watch?v={related_id}",
                                headers
                            )
                            await asyncio.sleep(random.uniform(2, 5))

            elapsed = time.time() - start_time

            logger.info(
                f"Finished browsing video on {self.interface}: {int(elapsed)}s session"
            )

            self.stats["watch_time_seconds"] += int(elapsed)
            self.stats["current_session"] = None

        except Exception as e:
            logger.error(f"Error in _browse_video for {self.interface}: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get current traffic statistics"""
        base_stats = super().get_stats()
        return {
            **base_stats,
            "browse_intensity": self.browse_intensity,
            "pages_fetched": self.stats["pages_fetched"],
            "videos_browsed": self.stats["videos_browsed"],
        }
