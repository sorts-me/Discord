import pytest
from sorts.database.connection import get_db, init_db
from sorts.database import models as db_models
from sorts.reddit.listener import RedditListener, get_reddit_listener


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
        else:
            univ.reddit_subreddit = "MahindraUni"
            db.commit()

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

        event = db.query(db_models.Event).filter_by(university_id=univ.id, slug="smart-india-hackathon-2026").first()
        if not event:
            event = db_models.Event(
                university_id=univ.id,
                slug="smart-india-hackathon-2026",
                name="Smart India Hackathon 2026 (Internal Hackathon)",
                organizer="Mahindra University & SIH 2026",
                category="Hackathon",
                summary="BUILD. INNOVATE. REPRESENT MAHINDRA UNIVERSITY.",
                description="Solve real-world problems.",
                registration_link="https://qrco.de/bgvXHe",
                official=True,
            )
            db.add(event)
            db.commit()

        yield db


def test_reddit_about_command(test_db):
    listener = get_reddit_listener()
    resp = listener.process_command(test_db, "!about", "MahindraUni")
    assert resp is not None
    assert "Sortling - Campus Club & Event Guide" in resp
    assert "Your campus, sorted." in resp


def test_reddit_clubs_command(test_db):
    listener = get_reddit_listener()
    resp = listener.process_command(test_db, "!clubs", "MahindraUni")
    assert resp is not None
    assert "Club Directory - Mahindra University" in resp
    assert "Active Clubs" in resp


def test_reddit_club_search_command(test_db):
    listener = get_reddit_listener()
    resp = listener.process_command(test_db, "!club qubit", "MahindraUni")
    assert resp is not None
    assert "Qubit Club" in resp
    assert "quantum computing" in resp.lower()
    assert "Category" in resp


def test_reddit_events_command(test_db):
    listener = get_reddit_listener()
    resp = listener.process_command(test_db, "!events", "MahindraUni")
    assert resp is not None
    assert "Upcoming Events & Opportunities" in resp
    assert "Smart India Hackathon 2026" in resp


def test_reddit_event_search_command(test_db):
    listener = get_reddit_listener()
    resp = listener.process_command(test_db, "!event sih", "MahindraUni")
    assert resp is not None
    assert "Smart India Hackathon 2026" in resp
    assert "https://qrco.de/bgvXHe" in resp


def test_reddit_setup_command(test_db):
    listener = get_reddit_listener()
    resp = listener.process_command(test_db, "!setup Brentford University | https://brentford.edu", "brentforduni")
    assert resp is not None
    assert "Setup Complete" in resp
    assert "brentforduni" in resp


def test_reddit_sort_pm_quiz_flow(test_db):
    from sorts.services.seed_service import seed_global_traits, seed_default_questions
    seed_global_traits(test_db)
    univ = test_db.query(db_models.University).filter_by(slug="mahindra").first()
    seed_default_questions(test_db, univ.id)

    listener = get_reddit_listener()
    # 1. Start PM Quiz
    resp1 = listener.process_command(test_db, "!sort", subreddit_name=None, author_name="freshman_student", is_pm=True)
    assert resp1 is not None
    assert "Interactive Club Recommendation Quiz" in resp1
    assert "Select the option that fits you best" in resp1

    # 2. Answer question 1 by replying with choice '1'
    resp2 = listener.process_command(test_db, "1", subreddit_name=None, author_name="freshman_student", is_pm=True)
    assert resp2 is not None
    assert "Interactive Club Recommendation Quiz" in resp2 or "Your Club Matches" in resp2

