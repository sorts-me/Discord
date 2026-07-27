import json
import logging
from http.server import BaseHTTPRequestHandler
from typing import Dict, Any

from sorts.database.connection import get_db
from sorts.database import models as db_models
from sorts.services.club_service import ClubService
from sorts.services.session_service import SessionService

logger = logging.getLogger("sortling.api")


def handle_api_request(path: str, method: str, params: Dict[str, Any], body_data: Dict[str, Any]) -> tuple[int, dict]:
    """Handles REST API requests from Devvit or external clients."""
    with get_db() as db:
        # 1. GET /api/university
        if path == "/api/university" and method == "GET":
            sub = params.get("subreddit", [None])[0]
            slug = params.get("slug", [None])[0]

            univ = None
            if sub:
                clean_sub = sub.strip().lstrip("r/").lower()
                all_univs = db.query(db_models.University).all()
                univ = next(
                    (u for u in all_univs if u.reddit_subreddit and u.reddit_subreddit.strip().lstrip("r/").lower() == clean_sub),
                    None,
                )
            if not univ and slug:
                univ = db.query(db_models.University).filter_by(slug=slug).first()

            if not univ:
                from sorts.config.settings import DEFAULT_UNIVERSITY_SLUG
                univ = db.query(db_models.University).filter_by(slug=DEFAULT_UNIVERSITY_SLUG).first()

            if not univ:
                return 404, {"error": "University not found"}

            return 200, {
                "id": univ.id,
                "slug": univ.slug,
                "name": univ.name,
                "website": univ.website,
                "description": univ.description,
                "reddit_subreddit": univ.reddit_subreddit,
            }

        # 2. GET /api/clubs
        if path == "/api/clubs" and method == "GET":
            univ_id = int(params.get("university_id", [1])[0])
            query = params.get("query", [""])[0]

            service = ClubService()
            if query:
                clubs = service.search_clubs(db, univ_id, query)
            else:
                clubs, _ = service.get_clubs_paginated(db, univ_id, page=1, per_page=50)

            return 200, {
                "count": len(clubs),
                "clubs": [c.to_schema_dict() for c in clubs],
            }

        # 3. GET /api/events
        if path == "/api/events" and method == "GET":
            univ_id = int(params.get("university_id", [1])[0])
            events = (
                db.query(db_models.Event)
                .filter_by(university_id=univ_id)
                .order_by(db_models.Event.id.desc())
                .all()
            )
            return 200, {
                "count": len(events),
                "events": [
                    {
                        "id": e.id,
                        "name": e.name,
                        "slug": e.slug,
                        "organizer": e.organizer,
                        "category": e.category,
                        "summary": e.summary,
                        "description": e.description,
                        "prizes": e.prizes,
                        "registration_deadline": e.registration_deadline,
                        "event_date": e.event_date,
                        "team_rules": e.team_rules,
                        "registration_link": e.registration_link,
                        "email_required": e.email_required,
                    }
                    for e in events
                ],
            }

        # 4. POST /api/sort/session (Start quiz session)
        if path == "/api/sort/session" and method == "POST":
            univ_id = int(body_data.get("university_id", 1))
            user_id = body_data.get("user_id", "reddit_user")

            session_svc = SessionService()
            session = session_svc.create_session(db, univ_id, user_identifier=user_id)
            first_q = session_svc.get_next_question(db, session.id)

            if not first_q:
                return 400, {"error": "No questions available"}

            return 200, {
                "session_id": session.id,
                "question": {
                    "id": first_q.id,
                    "code": first_q.code,
                    "text": first_q.text,
                    "options": [{"id": o.id, "text": o.text} for o in first_q.options],
                },
            }

        # 5. POST /api/sort/answer (Submit answer)
        if path == "/api/sort/answer" and method == "POST":
            session_id = body_data.get("session_id")
            question_id = int(body_data.get("question_id"))
            option_id = int(body_data.get("option_id"))

            session_svc = SessionService()
            session_svc.submit_answer(db, session_id, question_id, option_id)

            next_q = session_svc.get_next_question(db, session_id)
            if next_q:
                return 200, {
                    "completed": False,
                    "session_id": session_id,
                    "question": {
                        "id": next_q.id,
                        "code": next_q.code,
                        "text": next_q.text,
                        "options": [{"id": o.id, "text": o.text} for o in next_q.options],
                    },
                }

            # Convergence reached - generate top 3 recommendations
            recs = session_svc.generate_recommendations(db, session_id, limit=3)
            return 200, {
                "completed": True,
                "recommendations": [
                    {
                        "rank": r.rank,
                        "score": round(r.score, 2),
                        "explanation": r.explanation,
                        "club": r.club.to_schema_dict() if r.club else None,
                    }
                    for r in recs
                ],
            }

        return 404, {"error": "Endpoint not found"}
