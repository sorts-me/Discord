import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

# Use persistent disk /var/data if mounted (Render cloud deployment)
default_db_url = "sqlite:////var/data/sorts.db" if os.path.exists("/var/data") else "sqlite:///sorts.db"
DATABASE_URL = os.getenv("DATABASE_URL", default_db_url)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Exempted guilds resolve to the default university instead of looking up by guild_id.
# Comma-separated Discord guild IDs. Typically used for the primary/test server.
EXEMPTED_GUILDS_STR = os.getenv("EXEMPTED_GUILDS", "1475575129726517349,1361752080297230376")
EXEMPTED_GUILDS = {int(x.strip()) for x in EXEMPTED_GUILDS_STR.split(",") if x.strip()}

# Slug of the university used as the default for exempted guilds and bootstrap seeding.
DEFAULT_UNIVERSITY_SLUG = os.getenv("DEFAULT_UNIVERSITY_SLUG", "mahindra")

# Reddit Bot Credentials (PRAW)
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "SortlingBot/1.0 (Campus Guide)")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME", "")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD", "")

# Configure logging
numeric_level = getattr(logging, LOG_LEVEL, logging.INFO)
logging.basicConfig(
    level=numeric_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("sortling")
from urllib.parse import urlparse
_parsed = urlparse(DATABASE_URL)
_safe_url = f"{_parsed.scheme}://***@{_parsed.hostname}{_parsed.path}"
logger.info(f"Configuration loaded. Database: {_safe_url}")
