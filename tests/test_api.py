import pytest
from sorts.database.connection import get_db, init_db
from sorts.database import models as db_models
from sorts.web.api import handle_api_request
from sorts.services.seed_service import seed_global_traits, seed_default_questions


@pytest.fixture
def test_db():
    init_db()
    with get_db() as db:
        univ = db.query(db_models.University).filter_by(slug="mahindra").first()
        if not univ:
            univ = db_models.University(
                slug="mahindra",
                name="Mahindra University",
                website="https://www.mahindrauniversity.edu.in",
                description="Campus guide",
                reddit_subreddit="MahindraUni",
            )
            db.add(univ)
            db.commit()

        seed_global_traits(db)
        seed_default_questions(db, univ.id)

        club = db.query(db_models.Club).filter_by(university_id=univ.id, slug="qubit-club").first()
        if not club:
            club = db_models.Club(
                university_id=univ.id,
                slug="qubit-club",
                name="Qubit Club",
                summary="Quantum computing club",
                description="Exploring quantum algorithms and Qiskit.",
                category="Technical",
                official=True,
            )
            db.add(club)
            db.commit()

        yield db


def test_api_university_endpoint(test_db):
    status, data = handle_api_request("/api/university", "GET", {"subreddit": ["MahindraUni"]}, {})
    assert status == 200
    assert data["name"] == "Mahindra University"
    assert data["slug"] == "mahindra"


def test_api_clubs_endpoint(test_db):
    status, data = handle_api_request("/api/clubs", "GET", {"university_id": ["1"]}, {})
    assert status == 200
    assert "clubs" in data
    assert data["count"] >= 1


def test_api_sort_flow(test_db):
    # 1. Start session
    status, data = handle_api_request("/api/sort/session", "POST", {}, {"university_id": 1, "user_id": "test_devvit_user"})
    assert status == 200
    session_id = data["session_id"]
    question = data["question"]
    assert session_id is not None
    assert question["id"] > 0

    # 2. Answer question
    status_ans, data_ans = handle_api_request(
        "/api/sort/answer",
        "POST",
        {},
        {"session_id": session_id, "question_id": question["id"], "option_id": question["options"][0]["id"]},
    )
    assert status_ans == 200
    assert "completed" in data_ans
