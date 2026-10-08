import os
import time
import psutil

from werkzeug.security import generate_password_hash

from app import app
from models import db, User, Patient, Wound, Visit


# ---------------------------------------
# TEST CONFIGURATION
# ---------------------------------------

app.config.update(
    TESTING=True,
    SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
    SECRET_KEY="performance-test-key"
)


process = psutil.Process(os.getpid())


def memory_mb():
    return process.memory_info().rss / (1024 * 1024)


def measure_request(name, request_function, runs=20):

    times = []
    memory_values = []
    cpu_values = []

    # warm-up
    request_function()

    for _ in range(runs):

        cpu_start = process.cpu_times()
        memory_before = memory_mb()

        start = time.perf_counter()

        response = request_function()

        end = time.perf_counter()

        memory_after = memory_mb()
        cpu_end = process.cpu_times()

        elapsed = end - start

        cpu_time_used = (
            (cpu_end.user - cpu_start.user)
            +
            (cpu_end.system - cpu_start.system)
        )

        if elapsed > 0:
            cpu_percent = (
                cpu_time_used
                / elapsed
                / psutil.cpu_count()
            ) * 100
        else:
            cpu_percent = 0

        times.append(elapsed)

        memory_values.append(
            (memory_before + memory_after) / 2
        )

        cpu_values.append(cpu_percent)

        if response.status_code not in [200, 302]:
            print(
                f"WARNING: {name} returned "
                f"HTTP {response.status_code}"
            )

    average_time = sum(times) / len(times)
    average_memory = (
        sum(memory_values)
        / len(memory_values)
    )
    average_cpu = (
        sum(cpu_values)
        / len(cpu_values)
    )

    print()
    print("=" * 55)
    print(name)
    print("=" * 55)

    print(
        f"Average response time: "
        f"{average_time:.4f} seconds"
    )

    print(
        f"Average RAM usage: "
        f"{average_memory:.2f} MB"
    )

    print(
        f"Average CPU usage: "
        f"{average_cpu:.2f}%"
    )


with app.app_context():

    # ---------------------------------------
    # TEMPORARY DATABASE
    # ---------------------------------------

    db.drop_all()
    db.create_all()

    user = User(
        full_name="Performance Doctor",
        username="performance_doctor",
        password=generate_password_hash(
            "Test123!"
        ),
        role="DOCTOR",
        is_active=True
    )

    db.session.add(user)
    db.session.commit()


    patient = Patient(
        patient_id="123456789",
        full_name="Performance Patient"
    )

    db.session.add(patient)
    db.session.commit()


    wound = Wound(
        patient_id=patient.id,
        location="Front - Left Lower Leg",
        wound_type="Surgical Wound",
        status="ACTIVE"
    )

    db.session.add(wound)
    db.session.commit()


 

    # SQLAlchemy expects a date object,
    # therefore create visits separately below.


    from datetime import date

    visit1 = Visit(
        wound_id=wound.id,
        visit_date=date(2026, 10, 1),
        length_cm=5,
        width_cm=4,
        depth_cm=1,
        pain_level=6,
        wound_condition="Stable"
    )

    visit2 = Visit(
        wound_id=wound.id,
        visit_date=date(2026, 10, 5),
        length_cm=4,
        width_cm=3,
        depth_cm=0.8,
        pain_level=4,
        wound_condition="Improving"
    )

    visit3 = Visit(
        wound_id=wound.id,
        visit_date=date(2026, 10, 7),
        length_cm=3,
        width_cm=2.5,
        depth_cm=0.5,
        pain_level=2,
        wound_condition="Improving"
    )

    db.session.add_all([
        visit1,
        visit2,
        visit3
    ])

    db.session.commit()


    client = app.test_client()


    # ---------------------------------------
    # ACTION 1 - LOGIN
    # ---------------------------------------

    def login_request():

        return client.post(
            "/login",
            data={
                "username": "performance_doctor",
                "password": "Test123!"
            },
            follow_redirects=True
        )


    measure_request(
        "1. User Login",
        login_request
    )


    # Ensure logged in
    client.post(
        "/login",
        data={
            "username": "performance_doctor",
            "password": "Test123!"
        },
        follow_redirects=True
    )


    # ---------------------------------------
    # ACTION 2 - PATIENT DETAILS
    # ---------------------------------------

    def patient_details_request():

        return client.get(
            f"/patients/{patient.id}"
        )


    measure_request(
        "2. Open Patient and Wound History",
        patient_details_request
    )


    # ---------------------------------------
    # ACTION 3 - PATIENT REPORT
    # ---------------------------------------

    def patient_report_request():

        return client.get(
            f"/patients/{patient.id}/report"
        )


    measure_request(
        "3. Generate Patient Report",
        patient_report_request
    )


    print()
    print("=" * 55)
    print("Performance measurement completed.")
    print("The real application database was not modified.")
    print("=" * 55)