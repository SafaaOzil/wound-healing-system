from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    full_name = db.Column(
        db.String(120),
        nullable=False
    )

    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        nullable=False
    )

    is_active = db.Column(
        db.Boolean,
        default=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    
class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(30), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    birth_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    wounds = db.relationship(
        "Wound",
        backref="patient",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Wound(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patient.id"),
        nullable=False
    )

    location = db.Column(db.String(100), nullable=False)
    wound_type = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(30), default="ACTIVE")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    visits = db.relationship(
        "Visit",
        backref="wound",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    wound_id = db.Column(
        db.Integer,
        db.ForeignKey("wound.id"),
        nullable=False
    )

    visit_date = db.Column(db.Date, nullable=False)
    length_cm = db.Column(db.Float, nullable=False)
    width_cm = db.Column(db.Float, nullable=False)
    depth_cm = db.Column(db.Float, nullable=True)
    pain_level = db.Column(db.Integer, nullable=True)
    wound_condition = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def area(self):
        return round(self.length_cm * self.width_cm, 2)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(100), nullable=False)
    record_type = db.Column(db.String(50), nullable=False)
    record_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
