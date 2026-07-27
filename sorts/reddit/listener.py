import os
import re
import logging
import threading
import time
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from sorts.config import settings
from sorts.database.connection import get_db
from sorts.database import models as db_models
from sorts.services.club_service import ClubService
from sorts.services.session_service import SessionService
from sorts.services.seed_service import seed_default_questions

logger = logging.getLogger("sortling.reddit")

_HEADER_DIVIDER = "\n\n---\n\n"


def clean_text(val: Optional[str]) -> str:
    """Removes em-dashes and strips whitespace for compliance with AGENTS.md rules."""
    if not val:
        return ""
    return str(val).replace("—", "-").replace("–", "-").strip()


class RedditListener:
    """Background listener for Reddit mentions and private message commands."""

    def __init__(self):
        self.club_service = ClubService()
        self.session_service = SessionService()

    def is_configured(self) -> bool:
        """Returns True if Reddit credentials are provided in settings."""
        return bool(
            settings.REDDIT_CLIENT_ID
            and settings.REDDIT_CLIENT_SECRET
            and settings.REDDIT_USERNAME
            and settings.REDDIT_PASSWORD
        )

    def _get_university_for_subreddit(self, db: Session, subreddit_name: Optional[str]) -> Optional[db_models.University]:
        """Resolves university by subreddit name or falls back to DEFAULT_UNIVERSITY_SLUG / first university in DB."""
        if subreddit_name:
            clean_sub = subreddit_name.strip().lstrip("r/").lower()
            all_univs = db.query(db_models.University).all()
            for u in all_univs:
                if u.reddit_subreddit and u.reddit_subreddit.strip().lstrip("r/").lower() == clean_sub:
                    return u

        # Fallback to default university or first available university in DB
        univ = (
            db.query(db_models.University)
            .filter_by(slug=settings.DEFAULT_UNIVERSITY_SLUG)
            .first()
        )
        if not univ:
            univ = db.query(db_models.University).first()
        return univ

    def format_about(self) -> str:
        """Formats the !about response for Reddit."""
        lines = [
            "## Sortling - Campus Club & Event Guide",
            "",
            "> **Your campus, sorted.**",
            "",
            _HEADER_DIVIDER,
            "## About",
            "Sortling is a multi-university club and event discovery guide. It helps students find active campus organizations, browse verified club registries, and discover upcoming hackathons.",
            "",
            "## Available Commands",
            "• `!clubs` - Browse active university clubs.",
            "• `!club <name>` - Search details for a specific club.",
            "• `!events` - View upcoming campus hackathons and workshops.",
            "• `!event <name>` - View details for a specific event.",
            "• `!sort` - Start an interactive club matching questionnaire.",
            "• `!about` - Display this guide.",
            "",
            "---",
            "*Sortling Campus Guide*",
        ]
        return "\n".join(lines)

    def handle_clubs_command(self, db: Session, univ: db_models.University) -> str:
        """Formats response for !clubs."""
        clubs, _ = self.club_service.get_clubs_paginated(db, univ.id, page=1, per_page=50)
        if not clubs:
            return f"## Club Directory - {univ.name}\n\nNo active clubs found in the registry for {univ.name}. Subreddit admins can run `!setup` or add clubs."

        lines = [
            f"## Club Directory - {univ.name}",
            "",
            f"> **Explore {len(clubs)} verified campus clubs and student organizations.**",
            _HEADER_DIVIDER,
            "## Active Clubs",
        ]

        for club in clubs[:15]:
            cat = clean_text(club.category or "General")
            lines.append(f"• **{clean_text(club.name)}** (`{cat}`): {clean_text(club.summary)}")

        if len(clubs) > 15:
            lines.append(f"\n*Showing 15 of {len(clubs)} clubs. Use `!club <name>` to view a specific club.*")

        lines.extend(["", "---", "*Sortling Campus Guide*"])
        return "\n".join(lines)

    def handle_club_command(self, db: Session, univ: db_models.University, query: str) -> str:
        """Formats response for !club <name>."""
        if not query.strip():
            return "Please provide a club name or keyword. Example: `!club qubit`"

        matches = self.club_service.search_clubs(db, univ.id, query.strip())
        if not matches:
            return f"No clubs found matching `{query}` for {univ.name}."

        club = matches[0]
        socials = club.get_socials()
        soc_bullets = [f"• **{k.capitalize()}**: {v}" for k, v in socials.items()]

        lines = [
            f"## {clean_text(club.name)}",
            "",
            f"> **{clean_text(club.summary)}**",
            _HEADER_DIVIDER,
            "## About",
            clean_text(club.description),
            _HEADER_DIVIDER,
            "## Club Overview",
            f"• **Category**: {clean_text(club.category or 'General')}",
            f"• **Club Type**: {'Official Club' if club.official else 'Student Initiative'}",
            _HEADER_DIVIDER,
            "## Details & Schedule",
            f"• **Meeting Schedule**: {clean_text(club.meeting_frequency or 'Bi-weekly sessions')}",
            f"• **Commitment Level**: {clean_text(club.commitment or 'Medium commitment')}",
        ]

        if soc_bullets:
            lines.extend([_HEADER_DIVIDER, "## Official Links"] + soc_bullets)

        lines.extend(["", "---", "*Sortling Campus Guide*"])
        return "\n".join(lines)

    def handle_events_command(self, db: Session, univ: db_models.University) -> str:
        """Formats response for !events."""
        events = (
            db.query(db_models.Event)
            .filter_by(university_id=univ.id)
            .order_by(db_models.Event.id.desc())
            .all()
        )
        if not events:
            return f"## Events Registry - {univ.name}\n\nNo upcoming events found for {univ.name}."

        lines = [
            f"## Upcoming Events & Opportunities - {univ.name}",
            "",
            f"> **Explore {len(events)} upcoming campus hackathons and technical workshops.**",
            _HEADER_DIVIDER,
            "## Active Events",
        ]

        for ev in events:
            lines.append(
                f"• **{clean_text(ev.name)}** (`{clean_text(ev.category)}`): {clean_text(ev.summary)}\n"
                f"  • Date: {clean_text(ev.event_date or 'TBA')} | Deadline: {clean_text(ev.registration_deadline or 'TBA')}"
            )

        lines.extend(["", "---", "*Sortling Campus Guide*"])
        return "\n".join(lines)

    def handle_event_command(self, db: Session, univ: db_models.University, query: str) -> str:
        """Formats response for !event <name>."""
        if not query.strip():
            return "Please provide an event name or keyword. Example: `!event hackathon`"

        clean_q = query.strip().lower()

        all_evs = db.query(db_models.Event).filter_by(university_id=univ.id).all()

        def matches_event(e: db_models.Event) -> bool:
            if clean_q in e.slug.lower() or clean_q in e.name.lower() or clean_q in (e.summary or "").lower():
                return True
            # Match initials / acronym (e.g. 'sih' -> 'Smart India Hackathon')
            words = re.findall(r"[a-zA-Z]+", e.name)
            initials = "".join(w[0] for w in words).lower()
            if clean_q in initials:
                return True
            return False

        ev = next((e for e in all_evs if matches_event(e)), None)

        if not ev:
            return f"No events found matching `{query}` for {univ.name}."

        lines = [
            f"## {clean_text(ev.name)}",
            "",
            f"> **{clean_text(ev.summary)}**",
            _HEADER_DIVIDER,
            "## About",
            clean_text(ev.description),
            _HEADER_DIVIDER,
            "## Event Overview",
            f"• **Organized By**: {clean_text(ev.organizer)}",
            f"• **Category**: `{clean_text(ev.category)}`",
            _HEADER_DIVIDER,
            "## Important Dates",
            f"• **Registration Deadline**: {clean_text(ev.registration_deadline or 'TBA')}",
            f"• **Event Date**: {clean_text(ev.event_date or 'TBA')}",
        ]

        if ev.prizes:
            lines.extend([_HEADER_DIVIDER, "## Cash Prizes & Rewards", clean_text(ev.prizes)])

        if ev.team_rules:
            lines.extend([_HEADER_DIVIDER, "## Team Formation Rules", clean_text(ev.team_rules)])

        lines.extend([
            _HEADER_DIVIDER,
            "## Registration Requirement",
            "• **Student Email Required**: Yes" if ev.email_required else "• **Open Registration**: Yes",
            f"• **Register**: {ev.registration_link}",
            "",
            "---",
            "*Sortling Campus Guide*",
        ])
        return "\n".join(lines)

    def handle_setup_command(self, db: Session, subreddit_name: str, args_text: str) -> str:
        """Links a subreddit to a university workspace."""
        if not args_text.strip():
            return "Usage: `!setup <University Name> [| <Website URL>]`"

        parts = [p.strip() for p in args_text.split("|")]
        univ_name = parts[0]
        website = parts[1] if len(parts) > 1 else ""

        slug = re.sub(r"[^a-z0-9]", "-", univ_name.lower()).strip("-")
        univ = db.query(db_models.University).filter_by(slug=slug).first()

        if not univ:
            univ = db_models.University(
                slug=slug,
                name=univ_name,
                website=website or "https://example.edu",
                description=f"Campus guide for {univ_name}.",
                reddit_subreddit=subreddit_name,
            )
            db.add(univ)
            db.commit()
            db.refresh(univ)
            seed_default_questions(db, univ.id)
            msg = f"**{univ_name}** has been registered and linked to `r/{subreddit_name}`."
        else:
            univ.reddit_subreddit = subreddit_name
            if website:
                univ.website = website
            db.commit()
            msg = f"Linked `r/{subreddit_name}` to **{univ.name}**."

        return f"## Setup Complete\n\n{msg}\n\nUse `!clubs` or `!sort` in `r/{subreddit_name}` to explore."

    def _format_question_markdown(self, question: db_models.Question, univ_name: str) -> str:
        """Formats a questionnaire question into clean Reddit Markdown."""
        lines = [
            f"## Interactive Club Recommendation Quiz - {univ_name}",
            "",
            f"> **{clean_text(question.text)}**",
            _HEADER_DIVIDER,
            "Select the option that fits you best by replying with its number:",
            "",
        ]
        for idx, opt in enumerate(question.options, start=1):
            lines.append(f"`{idx}` {clean_text(opt.text)}")

        lines.extend([
            "",
            "---",
            "*Reply with the number of your choice (e.g. `1` or `!sort 1`)*",
        ])
        return "\n".join(lines)

    def _format_recommendations_markdown(self, recs: List[db_models.Recommendation], univ_name: str) -> str:
        """Formats club recommendation results into clean Reddit Markdown."""
        rank_badges = {1: "`1`", 2: "`2`", 3: "`3`"}
        lines = [
            f"## Your Club Matches - {univ_name}",
            "",
            f"> **Top recommendation matches based on your answers.**",
            _HEADER_DIVIDER,
        ]

        for r in recs[:3]:
            club = r.club
            badge = rank_badges.get(r.rank, f"`{r.rank}`")
            lines.extend([
                f"### {badge} {clean_text(club.name)}",
                f"> **{clean_text(club.summary)}**",
                "",
                f"• **Why you fit**: {clean_text(r.explanation)}",
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━",
                "",
            ])

        lines.extend([
            "*Sortling Campus Guide*",
        ])
        return "\n".join(lines)

    def handle_sort_pm(self, db: Session, univ: db_models.University, author_name: str, clean_text_input: str) -> str:
        """Handles interactive stateful quiz sessions for Reddit Direct Messages (PMs)."""
        user_identifier = f"reddit_pm_{author_name.lower()}"

        # Find existing active session
        session = (
            db.query(db_models.RecommendationSession)
            .filter_by(university_id=univ.id, user_identifier=user_identifier, status="active")
            .order_by(db_models.RecommendationSession.id.desc())
            .first()
        )

        # Handle explicit restart or starting fresh
        if not session or clean_text_input == "!sort" or clean_text_input == "!sort start" or clean_text_input == "!sort reset":
            session = self.session_service.create_session(db, univ.id, user_identifier=user_identifier)
            first_q = self.session_service.get_next_question(db, session.id)
            if not first_q:
                return f"No questions available for {univ.name}."
            return self._format_question_markdown(first_q, univ.name)

        # Check if user input is an option choice selection (e.g., "1", "2", "3", "4" or "!sort 1")
        option_idx = None
        choice_match = re.match(r"^(?:!sort\s+)?([1-9])$", clean_text_input, re.IGNORECASE)
        if choice_match:
            option_idx = int(choice_match.group(1)) - 1

        if option_idx is not None:
            curr_q = self.session_service.get_next_question(db, session.id)
            if curr_q and 0 <= option_idx < len(curr_q.options):
                opt = curr_q.options[option_idx]
                self.session_service.submit_answer(db, session.id, curr_q.id, opt.id)
                next_q = self.session_service.get_next_question(db, session.id)
                if next_q:
                    return self._format_question_markdown(next_q, univ.name)
                else:
                    recs = self.session_service.generate_recommendations(db, session.id, limit=3)
                    if not recs:
                        return f"No club matches found for your profile at {univ.name}. Use `!clubs` to browse all clubs."
                    return self._format_recommendations_markdown(recs, univ.name)

        # If user is in an active session but text didn't match an option, re-prompt current question
        curr_q = self.session_service.get_next_question(db, session.id)
        if curr_q:
            return (
                f"I didn't understand that choice. Please reply with a valid option number (1-{len(curr_q.options)}):\n\n"
                + self._format_question_markdown(curr_q, univ.name)
            )

        return self._format_question_markdown(curr_q, univ.name) if curr_q else "Use `!sort` to start the quiz."

    def process_command(
        self,
        db: Session,
        text: str,
        subreddit_name: Optional[str],
        author_name: Optional[str] = None,
        is_pm: bool = False
    ) -> Optional[str]:
        """Parses command string and returns formatted markdown output."""
        clean = text.strip()

        # Strip bot tag if present
        clean = re.sub(r"^/?u/(?:Sortling|SortlingBot)\s*", "", clean, flags=re.IGNORECASE).strip()

        if clean.startswith("!about"):
            return self.format_about()

        univ = self._get_university_for_subreddit(db, subreddit_name)

        if clean.startswith("!clubs"):
            if not univ:
                return "No university configured for this subreddit yet. Use `!setup <University Name>` to register."
            return self.handle_clubs_command(db, univ)

        if clean.startswith("!club"):
            if not univ:
                return "No university configured for this subreddit yet."
            query = clean[5:].strip()
            return self.handle_club_command(db, univ, query)

        if clean.startswith("!events"):
            if not univ:
                return "No university configured for this subreddit yet."
            return self.handle_events_command(db, univ)

        if clean.startswith("!event"):
            if not univ:
                return "No university configured for this subreddit yet."
            query = clean[6:].strip()
            return self.handle_event_command(db, univ, query)

        if clean.startswith("!setup"):
            args = clean[6:].strip()
            return self.handle_setup_command(db, subreddit_name or "general", args)

        # Stateful PM quiz flow vs public subreddit prompt
        if is_pm or (author_name and not subreddit_name):
            if univ and author_name:
                return self.handle_sort_pm(db, univ, author_name, clean)

        if clean.startswith("!sort"):
            if not univ:
                return "No university configured for this subreddit yet."
            return (
                f"## Interactive Recommendation Quiz - {univ.name}\n\n"
                f"To take the interactive club matching quiz for **{univ.name}**, send a Direct Message (PM) to `u/Sortling` containing `!sort`."
            )

        return None

    def start_polling(self):
        """Starts the PRAW inbox listener loop in a daemon thread."""
        if not self.is_configured():
            logger.info("Reddit credentials not configured. Reddit listener idle.")
            return

        thread = threading.Thread(target=self._run_praw_loop, daemon=True)
        thread.start()
        logger.info(f"Reddit listener thread started for username: {settings.REDDIT_USERNAME}")

    def _run_praw_loop(self):
        """Internal loop reading PRAW mentions and messages."""
        try:
            import praw
        except ImportError:
            logger.error("praw library not installed. Reddit listener stopping.")
            return

        while True:
            try:
                reddit = praw.Reddit(
                    client_id=settings.REDDIT_CLIENT_ID,
                    client_secret=settings.REDDIT_CLIENT_SECRET,
                    user_agent=settings.REDDIT_USER_AGENT,
                    username=settings.REDDIT_USERNAME,
                    password=settings.REDDIT_PASSWORD,
                )
                logger.info("Connected to Reddit API successfully via PRAW.")

                for item in reddit.inbox.stream(skip_existing=True):
                    try:
                        text = item.body
                        sub_name = item.subreddit.display_name if hasattr(item, "subreddit") and item.subreddit else None
                        author_name = str(item.author) if hasattr(item, "author") and item.author else None
                        is_pm = getattr(item, "was_comment", False) is False and sub_name is None

                        with get_db() as db:
                            response_text = self.process_command(
                                db, text, sub_name, author_name=author_name, is_pm=is_pm
                            )

                        if response_text:
                            item.reply(response_text)
                            logger.info(f"Replied to Reddit item {item.id} from u/{item.author}")

                        item.mark_read()
                    except Exception as item_err:
                        logger.error(f"Error processing Reddit inbox item {item.id}: {item_err}")
            except Exception as e:
                logger.error(f"Reddit listener connection error: {e}. Reconnecting in 30s...")
                time.sleep(30)


_instance: Optional[RedditListener] = None


def get_reddit_listener() -> RedditListener:
    global _instance
    if _instance is None:
        _instance = RedditListener()
    return _instance
