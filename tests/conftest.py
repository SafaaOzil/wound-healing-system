import pytest

from app import app
from models import db, User

from werkzeug.security import generate_password_hash


@pytest.fixture
def test_app():

    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SECRET_KEY="test-secret-key"
    )

    with app.app_context():

        db.drop_all()
        db.create_all()

        admin = User(
            full_name="Test Admin",
            username="admin_test",
            password=generate_password_hash(
                "Test123!"
            ),
            role="ADMIN",
            is_active=True
        )

        doctor = User(
            full_name="Test Doctor",
            username="doctor_test",
            password=generate_password_hash(
                "Test123!"
            ),
            role="DOCTOR",
            is_active=True
        )

        nurse = User(
            full_name="Test Nurse",
            username="nurse_test",
            password=generate_password_hash(
                "Test123!"
            ),
            role="NURSE",
            is_active=True
        )

        db.session.add_all([
            admin,
            doctor,
            nurse
        ])

        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):

    return test_app.test_client()


@pytest.fixture
def admin_login(client):

    client.post(
        "/login",
        data={
            "username": "admin_test",
            "password": "Test123!"
        },
        follow_redirects=True
    )

    return client


@pytest.fixture
def doctor_login(client):

    client.post(
        "/login",
        data={
            "username": "doctor_test",
            "password": "Test123!"
        },
        follow_redirects=True
    )

    return client


@pytest.fixture
def nurse_login(client):

    client.post(
        "/login",
        data={
            "username": "nurse_test",
            "password": "Test123!"
        },
        follow_redirects=True
    )

    return client