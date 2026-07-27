import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sorts.database.connection import Base
from sorts.database import models as db_models
from sorts.services.seed_service import seed_database
from sorts.services.session_service import SessionService
from sorts.services.import_service import ImportService
from sorts.services.club_service import ClubService

# Setup an in-memory SQLite database for testing services
@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def test_database_seeding_and_session_flow(db_session):
    univ = db_models.University(
        slug="mahindra",
        name="Mahindra University",
        website="https://www.mahindrauniversity.edu.in",
        description="Campus guide",
    )
    db_session.add(univ)
    db_session.commit()
    db_session.refresh(univ)
    
    # 1. Run Seeder
    from sorts.services.seed_service import seed_global_traits, seed_default_questions
    seed_global_traits(db_session)
    seed_default_questions(db_session, univ.id)
    
    # Verify university seeded
    assert univ is not None
    assert univ.name == "Mahindra University"
    
    # Verify traits and questions seeded
    traits_count = db_session.query(db_models.Trait).count()
    assert traits_count > 0
    questions_count = db_session.query(db_models.Question).count()
    assert questions_count > 0

    # Populate a test club
    club = db_models.Club(
        university_id=univ.id,
        slug="test-club",
        name="Test Coding Club",
        summary="A test club for software developers",
        description="Detailed description of test coding club.",
        category="Technical",
        official=True
    )
    db_session.add(club)
    db_session.commit()

    # 2. Run Recommendation Session Flow via SessionService
    session_svc = SessionService()
    session = session_svc.create_session(db_session, univ.id, user_identifier="test_user_123")
    assert session.id is not None
    assert session.status == "active"

    # Answer all questions in sequence
    loop_limit = 20
    answered_count = 0
    while answered_count < loop_limit:
        next_q = session_svc.get_next_question(db_session, session.id)
        if not next_q:
            break
            
        # Select first option
        option = next_q.options[0]
        session_svc.submit_answer(db_session, session.id, next_q.id, option.id)
        answered_count += 1
        
    assert answered_count > 0
    
    # Generate recommendations
    recs = session_svc.generate_recommendations(db_session, session.id, limit=3)
    assert len(recs) > 0
    assert recs[0].rank == 1
    assert recs[0].score >= 0.0
    assert len(recs[0].explanation) > 0

    # Verify session marked completed
    db_session.refresh(session)
    assert session.status == "completed"
    assert session.completed_at is not None


def test_crawler_import_and_publish_flow(db_session):
    univ = db_models.University(
        slug="mahindra",
        name="Mahindra University",
        website="https://www.mahindrauniversity.edu.in",
        description="Campus guide",
    )
    db_session.add(univ)
    db_session.commit()
    db_session.refresh(univ)

    source = db_models.ImportSource(
        university_id=univ.id,
        name="Default Source",
        source_type="file",
        url="sorts/assets/data/global_defaults.json",
    )
    db_session.add(source)
    db_session.commit()

    import_svc = ImportService()
    
    raw_clubs = [{
        "name": "Enigma",
        "summary": "Coding and CS Club",
        "description": "Enigma is the coding club",
        "category": "Technical",
        "official": True,
        "meeting_frequency": "Weekly",
        "commitment": "High commitment"
    }]
    
    job_id = import_svc.import_from_clubs_list(db_session, univ.id, source.id, raw_clubs)
    assert job_id > 0
    
    job = import_svc.get_job(db_session, job_id)
    assert job.status == "completed"

    drafts = db_session.query(db_models.DraftClub).filter_by(import_job_id=job_id).all()
    assert len(drafts) > 0
    assert drafts[0].name == "Enigma"

    import_svc.publish_job(db_session, job_id)
    db_session.refresh(job)
    assert job.status == "approved"

    clubs = db_session.query(db_models.Club).filter_by(university_id=univ.id).all()
    assert len(clubs) > 0
    assert clubs[0].name == "Enigma"
