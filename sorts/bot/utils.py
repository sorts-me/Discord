import os
import nextcord
from typing import Tuple, Optional
from sqlalchemy.orm import Session

MASCOT_DIR = "Sortling Mascot"

# Standard Brand Color for sorts.me (#000543)
BRAND_COLOR = nextcord.Color(0x000543)

def clean_text(text: Optional[str]) -> str:
    """Sanitizes text by replacing typographic dashes and non-breaking spaces."""
    if not text:
        return ""
    return (
        text.replace("—", "-")
        .replace("–", "-")
        .replace("\ufffd", "")
        .replace("\xa0", " ")
    )

def create_sortling_embed(
    title: str,
    description: str,
    color: nextcord.Color = BRAND_COLOR,
    is_error: bool = False
) -> Tuple[nextcord.Embed, Optional[nextcord.File]]:
    """Creates a standardized nextcord Embed with no mascot thumbnail.

    The thinking.gif / Icon_Neutral.png thumbnails are reserved exclusively
    for the /sort questionnaire flow and are set there directly.

    Returns:
        A tuple of (Embed, None). The None keeps call-site signatures
        compatible — callers can safely pass file=None to Discord.
    """
    embed = nextcord.Embed(
        title=clean_text(title),
        description=clean_text(description),
        color=color
    )
    return embed, None

def get_guild_university(db: Session, guild_id: Optional[int] = None):
    """Resolves Mahindra University directly for all operations in Sortling-MU."""
    from sorts.database import models as db_models
    univ = db.query(db_models.University).filter_by(slug="mahindra").first()
    if not univ:
        univ = db.query(db_models.University).first()
    return univ
