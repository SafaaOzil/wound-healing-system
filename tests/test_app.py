from models import db, Patient, Wound, Visit, AuditLog


def test_login_success(client):

    response = client.post(
        "/login",
        data={
            "username": "admin_test",
            "password": "Test123!"
        },
        follow_redirects=True
    )

    assert response.status_code == 200

    assert b"Wound Healing Dashboard" in response.data


def test_login_wrong_password(client):

    response = client.post(
        "/login",
        data={
            "username": "admin_test",
            "password": "WrongPassword"
        },
        follow_redirects=True
    )

    assert response.status_code == 200

    assert b"Invalid username or password" in response.data


def test_add_patient(admin_login):

    response = admin_login.post(
        "/patients/add",
        data={
            "patient_id": "123456789",
            "full_name": "Test Patient",
            "birth_date": "2000-01-01"
        },
        follow_redirects=True
    )

    assert response.status_code == 200

    assert b"Patient added successfully" in response.data

    patient = Patient.query.filter_by(
        patient_id="123456789"
    ).first()

    assert patient is not None
    assert patient.full_name == "Test Patient"


def test_future_birth_date_rejected(admin_login):

    response = admin_login.post(
        "/patients/add",
        data={
            "patient_id": "999999999",
            "full_name": "Future Patient",
            "birth_date": "2099-01-01"
        },
        follow_redirects=True
    )

    assert b"Birth date cannot be in the future" in response.data

    patient = Patient.query.filter_by(
        patient_id="999999999"
    ).first()

    assert patient is None


def test_add_wound(admin_login):

    patient = Patient(
        patient_id="111111111",
        full_name="Wound Patient"
    )

    db.session.add(patient)
    db.session.commit()

    response = admin_login.post(
        f"/patients/{patient.id}/wounds/add",
        data={
            "location": "Front - Left Knee",
            "wound_type": "Surgical Wound",
            "status": "ACTIVE"
        },
        follow_redirects=True
    )

    assert response.status_code == 200

    wound = Wound.query.filter_by(
        patient_id=patient.id
    ).first()

    assert wound is not None
    assert wound.location == "Front - Left Knee"
    assert wound.status == "ACTIVE"


def test_add_visit(admin_login):

    patient = Patient(
        patient_id="222222222",
        full_name="Visit Patient"
    )

    db.session.add(patient)
    db.session.commit()

    wound = Wound(
        patient_id=patient.id,
        location="Left Leg",
        wound_type="Traumatic Wound",
        status="ACTIVE"
    )

    db.session.add(wound)
    db.session.commit()

    response = admin_login.post(
        f"/wounds/{wound.id}/visits/add",
        data={
            "visit_date": "2026-10-01",
            "length_cm": "5",
            "width_cm": "4",
            "depth_cm": "1",
            "pain_level": "6",
            "wound_condition": "Stable",
            "notes": "Test visit"
        },
        follow_redirects=True
    )

    assert response.status_code == 200

    visit = Visit.query.filter_by(
        wound_id=wound.id
    ).first()

    assert visit is not None
    assert visit.length_cm == 5
    assert visit.width_cm == 4
    assert visit.area == 20


def test_visit_zero_length_rejected(admin_login):

    patient = Patient(
        patient_id="333333333",
        full_name="Invalid Visit Patient"
    )

    db.session.add(patient)
    db.session.commit()

    wound = Wound(
        patient_id=patient.id,
        location="Right Leg",
        status="ACTIVE"
    )

    db.session.add(wound)
    db.session.commit()

    response = admin_login.post(
        f"/wounds/{wound.id}/visits/add",
        data={
            "visit_date": "2026-10-01",
            "length_cm": "0",
            "width_cm": "4"
        },
        follow_redirects=True
    )

    assert b"Length must be greater than zero" in response.data

    visit = Visit.query.filter_by(
        wound_id=wound.id
    ).first()

    assert visit is None


def test_pain_above_10_rejected(admin_login):

    patient = Patient(
        patient_id="444444444",
        full_name="Pain Patient"
    )

    db.session.add(patient)
    db.session.commit()

    wound = Wound(
        patient_id=patient.id,
        location="Back",
        status="ACTIVE"
    )

    db.session.add(wound)
    db.session.commit()

    response = admin_login.post(
        f"/wounds/{wound.id}/visits/add",
        data={
            "visit_date": "2026-10-01",
            "length_cm": "4",
            "width_cm": "3",
            "pain_level": "11"
        },
        follow_redirects=True
    )

    assert b"Pain level must be between 0 and 10" in response.data


def test_nurse_cannot_access_users(nurse_login):

    response = nurse_login.get(
        "/admin/users",
        follow_redirects=True
    )

    assert response.status_code == 200

    assert b"You do not have permission" in response.data


def test_doctor_cannot_access_users(doctor_login):

    response = doctor_login.get(
        "/admin/users",
        follow_redirects=True
    )

    assert response.status_code == 200

    assert b"You do not have permission" in response.data


def test_admin_can_access_users(admin_login):

    response = admin_login.get(
        "/admin/users"
    )

    assert response.status_code == 200

    assert b"User Management" in response.data


def test_nurse_cannot_mark_wound_healed(nurse_login):

    patient = Patient(
        patient_id="555555555",
        full_name="Role Patient"
    )

    db.session.add(patient)
    db.session.commit()

    wound = Wound(
        patient_id=patient.id,
        location="Left Foot",
        wound_type="Diabetic Ulcer",
        status="ACTIVE"
    )

    db.session.add(wound)
    db.session.commit()

    response = nurse_login.post(
        f"/wounds/{wound.id}/edit",
        data={
            "location": "Left Foot",
            "wound_type": "Diabetic Ulcer",
            "status": "HEALED"
        },
        follow_redirects=True
    )

    assert b"Only a Doctor or Admin" in response.data

    updated_wound = db.session.get(
        Wound,
        wound.id
    )

    assert updated_wound.status == "ACTIVE"


def test_doctor_can_mark_wound_healed(doctor_login):

    patient = Patient(
        patient_id="666666666",
        full_name="Doctor Role Patient"
    )

    db.session.add(patient)
    db.session.commit()

    wound = Wound(
        patient_id=patient.id,
        location="Right Foot",
        wound_type="Surgical Wound",
        status="ACTIVE"
    )

    db.session.add(wound)
    db.session.commit()

    response = doctor_login.post(
        f"/wounds/{wound.id}/edit",
        data={
            "location": "Right Foot",
            "wound_type": "Surgical Wound",
            "status": "HEALED"
        },
        follow_redirects=True
    )

    assert response.status_code == 200

    updated_wound = db.session.get(
        Wound,
        wound.id
    )

    assert updated_wound.status == "HEALED"


def test_audit_log_created_after_patient_creation(admin_login):

    admin_login.post(
        "/patients/add",
        data={
            "patient_id": "777777777",
            "full_name": "Audit Patient",
            "birth_date": "2001-05-10"
        },
        follow_redirects=True
    )

    log = AuditLog.query.filter_by(
        record_type="PATIENT",
        action="CREATE"
    ).first()

    assert log is not None

    assert "Audit Patient" in log.details


def test_admin_can_open_audit_trail(admin_login):

    response = admin_login.get(
        "/audit"
    )

    assert response.status_code == 200

    assert b"Audit Trail" in response.data


def test_nurse_cannot_open_audit_trail(nurse_login):

    response = nurse_login.get(
        "/audit",
        follow_redirects=True
    )

    assert response.status_code == 200

    assert b"You do not have permission" in response.data


def test_duplicate_patient_id_rejected(admin_login):

    admin_login.post(
        "/patients/add",
        data={
            "patient_id": "888888888",
            "full_name": "First Patient",
            "birth_date": "2000-01-01"
        },
        follow_redirects=True
    )

    response = admin_login.post(
        "/patients/add",
        data={
            "patient_id": "888888888",
            "full_name": "Second Patient",
            "birth_date": "2001-01-01"
        },
        follow_redirects=True
    )

    assert b"A patient with this ID already exists" in response.data

    patients = Patient.query.filter_by(
        patient_id="888888888"
    ).all()

    assert len(patients) == 1


def test_visit_future_date_rejected(admin_login):

    patient = Patient(
        patient_id="999999991",
        full_name="Future Visit Patient"
    )

    db.session.add(patient)
    db.session.commit()

    wound = Wound(
        patient_id=patient.id,
        location="Left Arm",
        status="ACTIVE"
    )

    db.session.add(wound)
    db.session.commit()

    response = admin_login.post(
        f"/wounds/{wound.id}/visits/add",
        data={
            "visit_date": "2099-01-01",
            "length_cm": "3",
            "width_cm": "2"
        },
        follow_redirects=True
    )

    assert b"Visit date cannot be in the future" in response.data

    visit = Visit.query.filter_by(
        wound_id=wound.id
    ).first()

    assert visit is None


def test_negative_depth_rejected(admin_login):

    patient = Patient(
        patient_id="999999992",
        full_name="Depth Patient"
    )

    db.session.add(patient)
    db.session.commit()

    wound = Wound(
        patient_id=patient.id,
        location="Right Arm",
        status="ACTIVE"
    )

    db.session.add(wound)
    db.session.commit()

    response = admin_login.post(
        f"/wounds/{wound.id}/visits/add",
        data={
            "visit_date": "2026-10-01",
            "length_cm": "3",
            "width_cm": "2",
            "depth_cm": "-1"
        },
        follow_redirects=True
    )

    assert b"Depth cannot be negative" in response.data


def test_wound_area_calculation():

    visit = Visit(
        wound_id=1,
        visit_date=None,
        length_cm=5,
        width_cm=4
    )

    assert visit.area == 20


def test_wound_area_decimal_calculation():

    visit = Visit(
        wound_id=1,
        visit_date=None,
        length_cm=3.5,
        width_cm=2.5
    )

    assert visit.area == 8.75


def test_inactive_user_cannot_login(client):

    from models import User
    from werkzeug.security import generate_password_hash

    user = User(
        full_name="Inactive User",
        username="inactive_user",
        password=generate_password_hash("Test123!"),
        role="NURSE",
        is_active=False
    )

    db.session.add(user)
    db.session.commit()

    response = client.post(
        "/login",
        data={
            "username": "inactive_user",
            "password": "Test123!"
        },
        follow_redirects=True
    )

    assert b"This account is inactive" in response.data


def test_admin_can_open_reports(admin_login):

    response = admin_login.get(
        "/reports"
    )

    assert response.status_code == 200

    assert b"Reports Center" in response.data


def test_patient_report_page(admin_login):

    patient = Patient(
        patient_id="999999993",
        full_name="Report Patient"
    )

    db.session.add(patient)
    db.session.commit()

    response = admin_login.get(
        f"/patients/{patient.id}/report"
    )

    assert response.status_code == 200

    assert b"Patient Wound Report" in response.data