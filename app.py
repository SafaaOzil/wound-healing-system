from datetime import datetime, timedelta


import os
import tempfile

import matplotlib.pyplot as plt

from reportlab.platypus import Image

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    g
)

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)

from models import db, User, Patient, Wound, Visit, AuditLog
import csv
from io import StringIO
from flask import Response
import os
from werkzeug.utils import secure_filename
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import os

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///wound_system.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "development-secret-key"
)
app.config["UPLOAD_FOLDER"] = "static/uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db.init_app(app)



def create_audit_log(action, record_type, record_id=None, details=None):

    user_id = None

    if g.user is not None:
        user_id = g.user.id

    log = AuditLog(
        user_id=user_id,
        action=action,
        record_type=record_type,
        record_id=record_id,
        details=details
    )

    db.session.add(log)


@app.before_request
def load_logged_in_user():

    user_id = session.get("user_id")

    if user_id is None:
        g.user = None

    else:
        g.user = db.session.get(User, user_id)


def login_required(view):

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        if g.user is None:

            flash(
                "Please log in to continue.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        return view(*args, **kwargs)

    return wrapped_view


def roles_required(*roles):

    def decorator(view):

        @wraps(view)
        def wrapped_view(*args, **kwargs):

            if g.user is None:

                return redirect(
                    url_for("login")
                )

            if g.user.role not in roles:

                flash(
                    "You do not have permission to access this page.",
                    "error"
                )

                return redirect(
                    url_for("dashboard")
                )

            return view(*args, **kwargs)

        return wrapped_view

    return decorator

@app.route("/login", methods=["GET", "POST"])
def login():

    if g.user is not None:
        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        user = User.query.filter_by(
            username=username
        ).first()

        if user is None:

            flash(
                "Invalid username or password.",
                "error"
            )

            return render_template(
                "login.html"
            )

        if not user.is_active:

            flash(
                "This account is inactive.",
                "error"
            )

            return render_template(
                "login.html"
            )

        if not check_password_hash(
            user.password,
            password
        ):

            flash(
                "Invalid username or password.",
                "error"
            )

            return render_template(
                "login.html"
            )

        session.clear()

        session["user_id"] = user.id

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "login.html"
    )



@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )




@app.route("/admin/users")
@roles_required("ADMIN")
def manage_users():

    users = User.query.order_by(User.created_at.desc()).all()

    return render_template(
        "users.html",
        users=users
    )


@app.route("/admin/users/add", methods=["GET", "POST"])
@roles_required("ADMIN")
def add_user():

    if request.method == "POST":

        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "").strip()

        if not full_name or not username or not password or not role:

            flash(
                "All fields are required.",
                "error"
            )

            return redirect(
                url_for("add_user")
            )

        if role not in ["ADMIN", "DOCTOR", "NURSE"]:

            flash(
                "Invalid role.",
                "error"
            )

            return redirect(
                url_for("add_user")
            )

        existing_user = User.query.filter_by(
            username=username
        ).first()

        if existing_user:

            flash(
                "Username already exists.",
                "error"
            )

            return redirect(
                url_for("add_user")
            )

        new_user = User(
            full_name=full_name,
            username=username,
            password=generate_password_hash(password),
            role=role,
            is_active=True
        )

        db.session.add(new_user)
        db.session.commit()

        flash(
            "User created successfully.",
            "success"
        )

        return redirect(
            url_for("manage_users")
        )

    return render_template(
        "add_user.html"
    )


@app.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
@roles_required("ADMIN")
def toggle_user(user_id):

    user = User.query.get_or_404(user_id)

    if user.id == g.user.id:

        flash(
            "You cannot deactivate your own account.",
            "error"
        )

        return redirect(
            url_for("manage_users")
        )

    user.is_active = not user.is_active

    db.session.commit()

    flash(
        "User status updated.",
        "success"
    )

    return redirect(
        url_for("manage_users")
    )




@app.route("/")
@login_required

def dashboard():

    total_patients = Patient.query.count()
    total_wounds = Wound.query.count()
    total_visits = Visit.query.count()

    active_wounds = Wound.query.filter_by(
        status="ACTIVE"
    ).count()

    improving_wounds = 0
    stable_wounds = 0
    needs_attention_wounds = 0

    wounds = Wound.query.all()

    for wound in wounds:

        visits = sorted(
            wound.visits,
            key=lambda v: v.visit_date
        )

        if len(visits) < 2:
            continue

        previous_visit = visits[-2]
        latest_visit = visits[-1]

        if previous_visit.area <= 0:
            continue

        change_percent = (
            (previous_visit.area - latest_visit.area)
            / previous_visit.area
        ) * 100

        if change_percent > 5:

            improving_wounds += 1

        elif change_percent < -5:

            needs_attention_wounds += 1

        else:

            stable_wounds += 1

    return render_template(
        "dashboard.html",
        total_patients=total_patients,
        total_wounds=total_wounds,
        total_visits=total_visits,
        active_wounds=active_wounds,
        improving_wounds=improving_wounds,
        stable_wounds=stable_wounds,
        needs_attention_wounds=needs_attention_wounds
    )


@app.route("/patients")
@login_required

def patients():
    all_patients = Patient.query.order_by(Patient.created_at.desc()).all()

    return render_template(
        "patients.html",
        patients=all_patients
    )



@app.route("/patients/add", methods=["GET", "POST"])
@login_required
def add_patient():

    if request.method == "POST":

        patient_id = request.form.get("patient_id", "").strip()
        full_name = request.form.get("full_name", "").strip()
        birth_date = request.form.get("birth_date", "").strip()

        if not patient_id or not full_name:
            flash(
                "Patient ID and full name are required.",
                "error"
            )

            return redirect(
                url_for("add_patient")
            )

        existing_patient = Patient.query.filter_by(
            patient_id=patient_id
        ).first()

        if existing_patient:

            flash(
                "A patient with this ID already exists.",
                "error"
            )

            return redirect(
                url_for("add_patient")
            )

        parsed_birth_date = None

        if birth_date:

            try:

                parsed_birth_date = datetime.strptime(
                    birth_date,
                    "%Y-%m-%d"
                ).date()

                if parsed_birth_date > datetime.today().date():

                    flash(
                        "Birth date cannot be in the future.",
                        "error"
                    )

                    return redirect(
                        url_for("add_patient")
                    )

            except ValueError:

                flash(
                    "Invalid birth date.",
                    "error"
                )

                return redirect(
                    url_for("add_patient")
                )

        new_patient = Patient(
            patient_id=patient_id,
            full_name=full_name,
            birth_date=parsed_birth_date
        )

        db.session.add(new_patient)
        db.session.flush()

        create_audit_log(
            action="CREATE",
            record_type="PATIENT",
            record_id=new_patient.id,
            details=(
                f"Created patient: "
                f"{new_patient.full_name}"
            )
        )

        db.session.commit()

        flash(
            "Patient added successfully.",
            "success"
        )

        return redirect(
            url_for("patients")
        )

    return render_template(
        "add_patient.html"
    )






@app.route("/patients/<int:patient_db_id>")
def patient_details(patient_db_id):

    patient = Patient.query.get_or_404(patient_db_id)

    wound_progress = {}
    wound_alerts = {}

    for wound in patient.wounds:

        visits = sorted(
            wound.visits,
            key=lambda v: v.visit_date
        )

        progress_data = []

        previous_visit = None

        for visit in visits:

            change_percent = None
            progress_status = "First Visit"

            if previous_visit and previous_visit.area > 0:

                change_percent = round(
                    (
                        (previous_visit.area - visit.area)
                        / previous_visit.area
                    ) * 100,
                    2
                )

                if change_percent > 5:
                    progress_status = "Improving"

                elif change_percent < -5:
                    progress_status = "Worsening"

                else:
                    progress_status = "Stable"

            progress_data.append({
                "visit": visit,
                "change_percent": change_percent,
                "progress_status": progress_status
            })

            previous_visit = visit

        wound_progress[wound.id] = progress_data

        no_progress_alert = False

        if len(progress_data) >= 3:

            last_changes = [
                item["change_percent"]
                for item in progress_data[-2:]
                if item["change_percent"] is not None
            ]

            if len(last_changes) == 2:

                if all(abs(change) <= 5 for change in last_changes):
                    no_progress_alert = True

        wound_alerts[wound.id] = no_progress_alert

    return render_template(
        "patient_details.html",
        patient=patient,
        wound_progress=wound_progress,
        wound_alerts=wound_alerts
    )


@app.route("/patients/<int:patient_db_id>/wounds/add", methods=["GET", "POST"])
@login_required

def add_wound(patient_db_id):

    patient = Patient.query.get_or_404(patient_db_id)

    if request.method == "POST":

        location = request.form.get("location", "").strip()
        wound_type = request.form.get("wound_type", "").strip()
        status = request.form.get("status", "ACTIVE").strip()

        if not location:
            flash("Wound location is required.", "error")
            return redirect(
                url_for(
                    "add_wound",
                    patient_db_id=patient.id
                )
            )

        new_wound = Wound(
            patient_id=patient.id,
            location=location,
            wound_type=wound_type if wound_type else None,
            status=status
        )

        db.session.add(new_wound)
        db.session.flush()

        create_audit_log(
            action="CREATE",
            record_type="WOUND",
            record_id=new_wound.id,
            details=(
                f"Created wound for patient {patient.full_name}. "
                f"Location: {new_wound.location}. "
                f"Type: {new_wound.wound_type or '-'}"
            )
        )

        db.session.commit()
        flash("Wound added successfully.", "success")

        return redirect(
            url_for(
                "patient_details",
                patient_db_id=patient.id
            )
        )

    return render_template(
        "add_wound.html",
        patient=patient
    )

@app.route("/wounds/<int:wound_id>/visits/add", methods=["GET", "POST"])
@login_required
def add_visit(wound_id):

    wound = Wound.query.get_or_404(wound_id)

    if request.method == "POST":

        visit_date = request.form.get("visit_date", "").strip()
        length_cm = request.form.get("length_cm", "").strip()
        width_cm = request.form.get("width_cm", "").strip()
        depth_cm = request.form.get("depth_cm", "").strip()
        pain_level = request.form.get("pain_level", "").strip()
        wound_condition = request.form.get("wound_condition", "").strip()
        notes = request.form.get("notes", "").strip()

        # Required fields
        if not visit_date or not length_cm or not width_cm:

            flash(
                "Visit date, length and width are required.",
                "error"
            )

            return redirect(
                url_for(
                    "add_visit",
                    wound_id=wound.id
                )
            )

        try:

            # -------------------------
            # Visit Date
            # -------------------------

            parsed_date = datetime.strptime(
                visit_date,
                "%Y-%m-%d"
            ).date()

            if parsed_date > datetime.today().date():

                flash(
                    "Visit date cannot be in the future.",
                    "error"
                )

                return redirect(
                    url_for(
                        "add_visit",
                        wound_id=wound.id
                    )
                )

            # -------------------------
            # Length
            # -------------------------

            length_value = float(length_cm)

            if length_value <= 0:

                flash(
                    "Length must be greater than zero.",
                    "error"
                )

                return redirect(
                    url_for(
                        "add_visit",
                        wound_id=wound.id
                    )
                )

            # -------------------------
            # Width
            # -------------------------

            width_value = float(width_cm)

            if width_value <= 0:

                flash(
                    "Width must be greater than zero.",
                    "error"
                )

                return redirect(
                    url_for(
                        "add_visit",
                        wound_id=wound.id
                    )
                )

            # -------------------------
            # Depth
            # -------------------------

            depth_value = None

            if depth_cm:

                depth_value = float(depth_cm)

                if depth_value < 0:

                    flash(
                        "Depth cannot be negative.",
                        "error"
                    )

                    return redirect(
                        url_for(
                            "add_visit",
                            wound_id=wound.id
                        )
                    )

            # -------------------------
            # Pain Level
            # -------------------------

            pain_value = None

            if pain_level:

                pain_value = int(pain_level)

                if pain_value < 0 or pain_value > 10:

                    flash(
                        "Pain level must be between 0 and 10.",
                        "error"
                    )

                    return redirect(
                        url_for(
                            "add_visit",
                            wound_id=wound.id
                        )
                    )

        except ValueError:

            flash(
                "Invalid visit data. Please enter valid numeric values.",
                "error"
            )

            return redirect(
                url_for(
                    "add_visit",
                    wound_id=wound.id
                )
            )

        # -------------------------
        # Wound Condition
        # -------------------------

        allowed_conditions = [
            "",
            "Improving",
            "Stable",
            "Worsening",
            "Infected"
        ]

        if wound_condition not in allowed_conditions:

            flash(
                "Invalid wound condition.",
                "error"
            )

            return redirect(
                url_for(
                    "add_visit",
                    wound_id=wound.id
                )
            )

        # -------------------------
        # Image Upload
        # -------------------------

        image_path = None

        image = request.files.get("image")

        if image and image.filename:

            allowed_extensions = {
                "png",
                "jpg",
                "jpeg",
                "webp"
            }

            filename = secure_filename(
                image.filename
            )

            if "." not in filename:

                flash(
                    "Invalid image file.",
                    "error"
                )

                return redirect(
                    url_for(
                        "add_visit",
                        wound_id=wound.id
                    )
                )

            extension = filename.rsplit(
                ".",
                1
            )[1].lower()

            if extension not in allowed_extensions:

                flash(
                    "Image must be PNG, JPG, JPEG or WEBP.",
                    "error"
                )

                return redirect(
                    url_for(
                        "add_visit",
                        wound_id=wound.id
                    )
                )

            filename = (
                f"{wound.id}_"
                f"{datetime.now().timestamp()}_"
                f"{filename}"
            )

            save_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )

            image.save(
                save_path
            )

            image_path = (
                f"uploads/{filename}"
            )

        # -------------------------
        # Create Visit
        # -------------------------

        new_visit = Visit(
            wound_id=wound.id,
            visit_date=parsed_date,
            length_cm=length_value,
            width_cm=width_value,
            depth_cm=depth_value,
            pain_level=pain_value,
            wound_condition=(
                wound_condition
                if wound_condition
                else None
            ),
            notes=(
                notes
                if notes
                else None
            ),
            image_path=image_path
        )

        db.session.add(
            new_visit
        )

        db.session.flush()

        # -------------------------
        # Audit Trail
        # -------------------------

        create_audit_log(
            action="CREATE",
            record_type="VISIT",
            record_id=new_visit.id,
            details=(
                f"Added visit for wound #{wound.id}. "
                f"Date: {new_visit.visit_date}. "
                f"Length: {new_visit.length_cm} cm. "
                f"Width: {new_visit.width_cm} cm. "
                f"Depth: "
                f"{new_visit.depth_cm if new_visit.depth_cm is not None else '-'}. "
                f"Area: {new_visit.area} cm². "
                f"Pain: "
                f"{new_visit.pain_level if new_visit.pain_level is not None else '-'}. "
                f"Condition: "
                f"{new_visit.wound_condition or '-'}."
            )
        )

        db.session.commit()

        flash(
            "Visit added successfully.",
            "success"
        )

        return redirect(
            url_for(
                "patient_details",
                patient_db_id=wound.patient.id
            )
        )

    return render_template(
        "add_visit.html",
        wound=wound
    )





@app.route("/wounds/<int:wound_id>/compare")
@login_required

def compare_visits(wound_id):

    wound = Wound.query.get_or_404(wound_id)

    visits = sorted(
        wound.visits,
        key=lambda v: v.visit_date
    )

    first_visit_id = request.args.get("first_visit", type=int)
    second_visit_id = request.args.get("second_visit", type=int)

    first_visit = None
    second_visit = None
    comparison = None

    if first_visit_id and second_visit_id:

        first_visit = Visit.query.filter_by(
            id=first_visit_id,
            wound_id=wound.id
        ).first_or_404()

        second_visit = Visit.query.filter_by(
            id=second_visit_id,
            wound_id=wound.id
        ).first_or_404()

        area_change = None
        status = None

        if first_visit.area > 0:

            area_change = round(
                (
                    (first_visit.area - second_visit.area)
                    / first_visit.area
                ) * 100,
                2
            )

            if area_change > 5:
                status = "Improved"

            elif area_change < -5:
                status = "Worsened"

            else:
                status = "Stable"

        comparison = {
            "area_change": area_change,
            "status": status
        }

    return render_template(
        "compare_visits.html",
        wound=wound,
        visits=visits,
        first_visit=first_visit,
        second_visit=second_visit,
        comparison=comparison
    )


@app.route("/audit")
@roles_required("ADMIN")
def audit_trail():

    logs = AuditLog.query.order_by(
        AuditLog.timestamp.desc()
    ).all()

    users = {
        user.id: user
        for user in User.query.all()
    }

    return render_template(
        "audit_trail.html",
        logs=logs,
        users=users
    )




@app.route("/patients/<int:patient_db_id>/report")
@login_required
def patient_report(patient_db_id):

    patient = Patient.query.get_or_404(patient_db_id)

    wound_progress = {}

    for wound in patient.wounds:

        visits = sorted(
            wound.visits,
            key=lambda v: v.visit_date
        )

        progress_data = []
        previous_visit = None

        for visit in visits:

            change_percent = None
            progress_status = "First Visit"

            if previous_visit and previous_visit.area > 0:

                change_percent = round(
                    (
                        (previous_visit.area - visit.area)
                        / previous_visit.area
                    ) * 100,
                    2
                )

                if change_percent > 5:
                    progress_status = "Improving"

                elif change_percent < -5:
                    progress_status = "Worsening"

                else:
                    progress_status = "Stable"

            progress_data.append({
                "visit": visit,
                "change_percent": change_percent,
                "progress_status": progress_status
            })

            previous_visit = visit

        wound_progress[wound.id] = progress_data

    create_audit_log(
        action="VIEW_REPORT",
        record_type="PATIENT",
        record_id=patient.id,
        details=f"Viewed patient report for {patient.full_name}"
    )

    db.session.commit()

    return render_template(
        "patient_report.html",
        patient=patient,
        wound_progress=wound_progress
    )

@app.route("/wounds/<int:wound_id>/export/csv")
@login_required
def export_wound_csv(wound_id):

    wound = Wound.query.get_or_404(wound_id)

    visits = sorted(
        wound.visits,
        key=lambda v: v.visit_date
    )

    output = StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "Visit Date",
        "Length (cm)",
        "Width (cm)",
        "Depth (cm)",
        "Area (cm2)",
        "Pain Level",
        "Condition",
        "Notes"
    ])

    for visit in visits:

        writer.writerow([
            visit.visit_date.strftime("%d/%m/%Y"),
            visit.length_cm,
            visit.width_cm,
            visit.depth_cm if visit.depth_cm is not None else "",
            visit.area,
            visit.pain_level if visit.pain_level is not None else "",
            visit.wound_condition or "",
            visit.notes or ""
        ])

    create_audit_log(
        action="EXPORT",
        record_type="WOUND",
        record_id=wound.id,
        details="Exported wound visit history to CSV"
    )

    db.session.commit()

    response = Response(
        output.getvalue(),
        mimetype="text/csv"
    )

    response.headers["Content-Disposition"] = (
        f"attachment; filename=wound_{wound.id}_visits.csv"
    )

    return response

@app.route("/patients/<int:patient_db_id>/report/pdf")
@login_required
def export_patient_pdf(patient_db_id):

    patient = Patient.query.get_or_404(patient_db_id)

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm
    )

    styles = getSampleStyleSheet()

    elements = []

    elements.append(
        Paragraph(
            "Patient Wound Report",
            styles["Title"]
        )
    )

    elements.append(
        Spacer(1, 12)
    )

    patient_info = [
        ["Patient ID", patient.patient_id],
        ["Full Name", patient.full_name],
        [
            "Birth Date",
            patient.birth_date.strftime("%d/%m/%Y")
            if patient.birth_date
            else "-"
        ],
        ["Total Wounds", str(len(patient.wounds))]
    ]

    patient_table = Table(
        patient_info,
        colWidths=[5 * cm, 11 * cm]
    )

    patient_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 8)
        ])
    )

    elements.append(patient_table)
    elements.append(Spacer(1, 20))

    for wound in patient.wounds:

        elements.append(
            Paragraph(
                f"Wound #{wound.id}",
                styles["Heading2"]
            )
        )

        wound_info = [
            ["Location", wound.location],
            ["Type", wound.wound_type or "-"],
            ["Status", wound.status],
            ["Total Visits", str(len(wound.visits))]
        ]

        wound_table = Table(
            wound_info,
            colWidths=[5 * cm, 11 * cm]
        )

        wound_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("PADDING", (0, 0), (-1, -1), 7)
            ])
        )

        elements.append(wound_table)
        elements.append(Spacer(1, 12))

        visits = sorted(
            wound.visits,
            key=lambda v: v.visit_date
        )

        if visits:

            visit_rows = [[
                "Date",
                "Length",
                "Width",
                "Depth",
                "Area",
                "Pain",
                "Progress"
            ]]

            previous_visit = None

            chart_dates = []
            chart_areas = []

            for visit in visits:

                progress_status = "First Visit"

                if previous_visit and previous_visit.area > 0:

                    change_percent = (
                        (
                            previous_visit.area - visit.area
                        )
                        / previous_visit.area
                    ) * 100

                    if change_percent > 5:
                        progress_status = "Improving"

                    elif change_percent < -5:
                        progress_status = "Worsening"

                    else:
                        progress_status = "Stable"

                visit_rows.append([
                    visit.visit_date.strftime("%d/%m/%Y"),
                    f"{visit.length_cm} cm",
                    f"{visit.width_cm} cm",
                    (
                        f"{visit.depth_cm} cm"
                        if visit.depth_cm is not None
                        else "-"
                    ),
                    f"{visit.area} cm2",
                    (
                        f"{visit.pain_level}/10"
                        if visit.pain_level is not None
                        else "-"
                    ),
                    progress_status
                ])

                chart_dates.append(
                    visit.visit_date.strftime("%d/%m/%Y")
                )

                chart_areas.append(
                    visit.area
                )

                previous_visit = visit

            visits_table = Table(
                visit_rows,
                repeatRows=1,
                colWidths=[
                    2.4 * cm,
                    2.1 * cm,
                    2.1 * cm,
                    2.1 * cm,
                    2.2 * cm,
                    1.8 * cm,
                    2.8 * cm
                ]
            )

            visits_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 5)
                ])
            )

            elements.append(visits_table)
            elements.append(Spacer(1, 15))

            # ==========================
            # WOUND PROGRESS CHART
            # ==========================

            if len(chart_areas) > 1:

                temp_chart = tempfile.NamedTemporaryFile(
                    suffix=".png",
                    delete=False
                )

                temp_chart.close()

                plt.figure(figsize=(7, 3.5))

                plt.plot(
                    chart_dates,
                    chart_areas,
                    marker="o"
                )

                plt.title(
                    f"Wound #{wound.id} - Area Progress"
                )

                plt.xlabel("Visit Date")
                plt.ylabel("Area (cm²)")

                plt.grid(True)

                plt.tight_layout()

                plt.savefig(
                    temp_chart.name,
                    dpi=150
                )

                plt.close()

                elements.append(
                    Paragraph(
                        "Healing Progress Chart",
                        styles["Heading3"]
                    )
                )

                elements.append(
                    Image(
                        temp_chart.name,
                        width=16 * cm,
                        height=8 * cm
                    )
                )

                elements.append(
                    Spacer(1, 15)
                )

            # ==========================
            # VISIT IMAGES
            # ==========================

            image_elements = []

            for visit in visits:

                if not visit.image_path:
                    continue

                image_file = os.path.join(
                    app.root_path,
                    "static",
                    visit.image_path
                )

                if not os.path.exists(image_file):
                    continue

                visit_image_content = []

                visit_image_content.append(
                    Paragraph(
                        (
                            f"Visit: "
                            f"{visit.visit_date.strftime('%d/%m/%Y')}"
                        ),
                        styles["Heading4"]
                    )
                )

                visit_image_content.append(
                    Image(
                        image_file,
                        width=6 * cm,
                        height=6 * cm
                    )
                )

                image_elements.append(
                    visit_image_content
                )

            if image_elements:

                elements.append(
                    Paragraph(
                        "Wound Images",
                        styles["Heading3"]
                    )
                )

                image_rows = []

                current_row = []

                for visit_image in image_elements:

                    cell = []

                    for item in visit_image:
                        cell.append(item)

                    current_row.append(cell)

                    if len(current_row) == 2:

                        image_rows.append(current_row)
                        current_row = []

                if current_row:

                    current_row.append("")

                    image_rows.append(
                        current_row
                    )

                image_table = Table(
                    image_rows,
                    colWidths=[
                        8 * cm,
                        8 * cm
                    ]
                )

                image_table.setStyle(
                    TableStyle([
                        (
                            "VALIGN",
                            (0, 0),
                            (-1, -1),
                            "TOP"
                        ),
                        (
                            "BOX",
                            (0, 0),
                            (-1, -1),
                            0.5,
                            colors.lightgrey
                        ),
                        (
                            "INNERGRID",
                            (0, 0),
                            (-1, -1),
                            0.25,
                            colors.lightgrey
                        ),
                        (
                            "PADDING",
                            (0, 0),
                            (-1, -1),
                            8
                        )
                    ])
                )

                elements.append(
                    image_table
                )

        else:

            elements.append(
                Paragraph(
                    "No visits recorded.",
                    styles["Normal"]
                )
            )

        elements.append(
            Spacer(1, 25)
        )

    elements.append(
        Spacer(1, 15)
    )

    elements.append(
        Paragraph(
            (
                f"Generated by: "
                f"{g.user.full_name} "
                f"({g.user.role})"
            ),
            styles["Normal"]
        )
    )

    doc.build(elements)

    create_audit_log(
        action="EXPORT",
        record_type="PATIENT",
        record_id=patient.id,
        details=(
            "Exported patient wound report "
            "to PDF with charts and wound images"
        )
    )

    db.session.commit()

    buffer.seek(0)

    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
                (
                    "attachment; "
                    f"filename=patient_"
                    f"{patient.patient_id}_report.pdf"
                )
        }
    )


@app.route("/patients/<int:patient_db_id>/edit", methods=["GET", "POST"])
@login_required
def edit_patient(patient_db_id):

    patient = Patient.query.get_or_404(patient_db_id)

    if request.method == "POST":

        old_full_name = patient.full_name
        old_birth_date = patient.birth_date

        full_name = request.form.get("full_name", "").strip()
        birth_date = request.form.get("birth_date", "").strip()

        if not full_name:
            flash("Full name is required.", "error")
            return redirect(
                url_for(
                    "edit_patient",
                    patient_db_id=patient.id
                )
            )

        parsed_birth_date = None

        if birth_date:
            try:
                parsed_birth_date = datetime.strptime(
                    birth_date,
                    "%Y-%m-%d"
                ).date()

                if parsed_birth_date > datetime.today().date():
                    flash(
                        "Birth date cannot be in the future.",
                        "error"
                    )

                    return redirect(
                        url_for(
                            "edit_patient",
                            patient_db_id=patient.id
                        )
                    )

            except ValueError:

                flash(
                    "Invalid birth date.",
                    "error"
                )

                return redirect(
                    url_for(
                        "edit_patient",
                        patient_db_id=patient.id
                    )
                )

        patient.full_name = full_name
        patient.birth_date = parsed_birth_date

        create_audit_log(
            action="UPDATE",
            record_type="PATIENT",
            record_id=patient.id,
            details=(
                f"Patient updated. "
                f"Name: {old_full_name} -> {patient.full_name}. "
                f"Birth date: {old_birth_date} -> {patient.birth_date}"
            )
        )

        db.session.commit()

        flash(
            "Patient updated successfully.",
            "success"
        )

        return redirect(
            url_for(
                "patient_details",
                patient_db_id=patient.id
            )
        )

    return render_template(
        "edit_patient.html",
        patient=patient
    )


@app.route("/wounds/<int:wound_id>/edit", methods=["GET", "POST"])
@login_required
def edit_wound(wound_id):

    wound = Wound.query.get_or_404(wound_id)

    if request.method == "POST":

        old_location = wound.location
        old_type = wound.wound_type
        old_status = wound.status

        location = request.form.get("location", "").strip()
        wound_type = request.form.get("wound_type", "").strip()
        status = request.form.get("status", "").strip()

        if (
            status in ["HEALED", "CLOSED"]
            and g.user.role not in ["ADMIN", "DOCTOR"]
        ):

            flash(
                "Only a Doctor or Admin can mark a wound as healed or closed.",
                "error"
            )

            return redirect(
                url_for(
                    "edit_wound",
                    wound_id=wound.id
                )
            )

        if not location:
            flash(
                "Wound location is required.",
                "error"
            )

            return redirect(
                url_for(
                    "edit_wound",
                    wound_id=wound.id
                )
            )

        if status not in ["ACTIVE", "HEALED", "CLOSED"]:

            flash(
                "Invalid wound status.",
                "error"
            )

            return redirect(
                url_for(
                    "edit_wound",
                    wound_id=wound.id
                )
            )

        wound.location = location
        wound.wound_type = wound_type if wound_type else None
        wound.status = status

        create_audit_log(
            action="UPDATE",
            record_type="WOUND",
            record_id=wound.id,
            details=(
                f"Wound updated. "
                f"Location: {old_location} -> {wound.location}. "
                f"Type: {old_type or '-'} -> {wound.wound_type or '-'}. "
                f"Status: {old_status} -> {wound.status}"
            )
        )

        db.session.commit()

        flash(
            "Wound updated successfully.",
            "success"
        )

        return redirect(
            url_for(
                "patient_details",
                patient_db_id=wound.patient.id
            )
        )

    return render_template(
        "edit_wound.html",
        wound=wound
    )

@app.route("/visits/<int:visit_id>/edit", methods=["GET", "POST"])
@login_required
def edit_visit(visit_id):

    visit = Visit.query.get_or_404(visit_id)

    if request.method == "POST":

        old_visit_date = visit.visit_date
        old_length = visit.length_cm
        old_width = visit.width_cm
        old_depth = visit.depth_cm
        old_pain = visit.pain_level
        old_condition = visit.wound_condition
        old_notes = visit.notes
        old_image_path = visit.image_path

        visit_date = request.form.get("visit_date", "").strip()
        length_cm = request.form.get("length_cm", "").strip()
        width_cm = request.form.get("width_cm", "").strip()
        depth_cm = request.form.get("depth_cm", "").strip()
        pain_level = request.form.get("pain_level", "").strip()
        wound_condition = request.form.get("wound_condition", "").strip()
        notes = request.form.get("notes", "").strip()

        if not visit_date or not length_cm or not width_cm:

            flash(
                "Visit date, length and width are required.",
                "error"
            )

            return redirect(
                url_for(
                    "edit_visit",
                    visit_id=visit.id
                )
            )

        try:

            parsed_date = datetime.strptime(
                visit_date,
                "%Y-%m-%d"
            ).date()

            if parsed_date > datetime.today().date():

                flash(
                    "Visit date cannot be in the future.",
                    "error"
                )

                return redirect(
                    url_for(
                        "edit_visit",
                        visit_id=visit.id
                    )
                )

            length_value = float(length_cm)
            width_value = float(width_cm)

            if length_value <= 0 or width_value <= 0:

                flash(
                    "Length and width must be greater than zero.",
                    "error"
                )

                return redirect(
                    url_for(
                        "edit_visit",
                        visit_id=visit.id
                    )
                )

            depth_value = None

            if depth_cm:

                depth_value = float(depth_cm)

                if depth_value < 0:

                    flash(
                        "Depth cannot be negative.",
                        "error"
                    )

                    return redirect(
                        url_for(
                            "edit_visit",
                            visit_id=visit.id
                        )
                    )

            pain_value = None

            if pain_level:

                pain_value = int(pain_level)

                if pain_value < 0 or pain_value > 10:

                    flash(
                        "Pain level must be between 0 and 10.",
                        "error"
                    )

                    return redirect(
                        url_for(
                            "edit_visit",
                            visit_id=visit.id
                        )
                    )

        except ValueError:

            flash(
                "Invalid visit data.",
                "error"
            )

            return redirect(
                url_for(
                    "edit_visit",
                    visit_id=visit.id
                )
            )

        image = request.files.get("image")

        if image and image.filename:

            filename = secure_filename(
                image.filename
            )

            filename = (
                f"{visit.wound.id}_"
                f"{datetime.now().timestamp()}_"
                f"{filename}"
            )

            save_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )

            image.save(save_path)

            visit.image_path = (
                f"uploads/{filename}"
            )

        visit.visit_date = parsed_date
        visit.length_cm = length_value
        visit.width_cm = width_value
        visit.depth_cm = depth_value
        visit.pain_level = pain_value
        visit.wound_condition = wound_condition or None
        visit.notes = notes or None

        create_audit_log(
            action="UPDATE",
            record_type="VISIT",
            record_id=visit.id,
            details=(
                f"Visit updated. "
                f"Date: {old_visit_date} -> {visit.visit_date}. "
                f"Length: {old_length} -> {visit.length_cm}. "
                f"Width: {old_width} -> {visit.width_cm}. "
                f"Depth: {old_depth} -> {visit.depth_cm}. "
                f"Pain: {old_pain} -> {visit.pain_level}. "
                f"Condition: {old_condition or '-'} -> "
                f"{visit.wound_condition or '-'}. "
                f"Notes updated: "
                f"{old_notes != visit.notes}. "
                f"Image changed: "
                f"{old_image_path != visit.image_path}"
            )
        )

        db.session.commit()

        flash(
            "Visit updated successfully.",
            "success"
        )

        return redirect(
            url_for(
                "patient_details",
                patient_db_id=visit.wound.patient.id
            )
        )

    return render_template(
        "edit_visit.html",
        visit=visit
    )


@app.route("/reports")
@login_required
def reports_center():

    # =========================
    # PATIENT REPORT SEARCH
    # =========================

    patient = None
    wounds = []

    patient_id = request.args.get(
        "patient_id",
        ""
    ).strip()

    if patient_id:

        patient = Patient.query.filter_by(
            patient_id=patient_id
        ).first()

        if patient:

            wounds = patient.wounds

        else:

            flash(
                "Patient not found.",
                "error"
            )


    # =========================
    # AUDIT TRAIL FILTERS
    # =========================

    audit_logs = []
    audit_users = []

    selected_user_id = request.args.get(
        "audit_user_id",
        "",
        type=str
    )

    selected_action = request.args.get(
        "audit_action",
        ""
    ).strip()

    selected_record_type = request.args.get(
        "audit_record_type",
        ""
    ).strip()

    start_date = request.args.get(
        "audit_start_date",
        ""
    ).strip()

    end_date = request.args.get(
        "audit_end_date",
        ""
    ).strip()


    if g.user.role == "ADMIN":

        audit_users = User.query.order_by(
            User.full_name.asc()
        ).all()

        query = AuditLog.query

        if selected_user_id:

            try:

                query = query.filter(
                    AuditLog.user_id == int(selected_user_id)
                )

            except ValueError:
                pass


        if selected_action:

            query = query.filter(
                AuditLog.action == selected_action
            )


        if selected_record_type:

            query = query.filter(
                AuditLog.record_type == selected_record_type
            )


        if start_date:

            try:

                parsed_start = datetime.strptime(
                    start_date,
                    "%Y-%m-%d"
                )

                query = query.filter(
                    AuditLog.timestamp >= parsed_start
                )

            except ValueError:
                pass


        if end_date:

            try:

                parsed_end = datetime.strptime(
                    end_date,
                    "%Y-%m-%d"
                )

                next_day = parsed_end + timedelta(days=1)

                query = query.filter(
                    AuditLog.timestamp < next_day
                )

            except ValueError:
                pass


        audit_logs = query.order_by(
            AuditLog.timestamp.desc()
        ).all()


    audit_user_map = {
        user.id: user
        for user in audit_users
    }


    return render_template(
        "reports.html",

        patient=patient,
        wounds=wounds,
        patient_id=patient_id,

        audit_logs=audit_logs,
        audit_users=audit_users,
        audit_user_map=audit_user_map,

        selected_user_id=selected_user_id,
        selected_action=selected_action,
        selected_record_type=selected_record_type,
        start_date=start_date,
        end_date=end_date
    )

@app.route("/reports/audit/pdf")
@roles_required("ADMIN")
def export_audit_pdf():

    selected_user_id = request.args.get(
        "audit_user_id",
        ""
    ).strip()

    selected_action = request.args.get(
        "audit_action",
        ""
    ).strip()

    selected_record_type = request.args.get(
        "audit_record_type",
        ""
    ).strip()

    start_date = request.args.get(
        "audit_start_date",
        ""
    ).strip()

    end_date = request.args.get(
        "audit_end_date",
        ""
    ).strip()


    query = AuditLog.query


    if selected_user_id:

        try:

            query = query.filter(
                AuditLog.user_id == int(selected_user_id)
            )

        except ValueError:
            pass


    if selected_action:

        query = query.filter(
            AuditLog.action == selected_action
        )


    if selected_record_type:

        query = query.filter(
            AuditLog.record_type == selected_record_type
        )


    if start_date:

        try:

            parsed_start = datetime.strptime(
                start_date,
                "%Y-%m-%d"
            )

            query = query.filter(
                AuditLog.timestamp >= parsed_start
            )

        except ValueError:
            pass


    if end_date:

        try:

            parsed_end = datetime.strptime(
                end_date,
                "%Y-%m-%d"
            )

            next_day = parsed_end + timedelta(days=1)

            query = query.filter(
                AuditLog.timestamp < next_day
            )

        except ValueError:
            pass


    logs = query.order_by(
        AuditLog.timestamp.desc()
    ).all()


    users = {
        user.id: user
        for user in User.query.all()
    }


    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm
    )

    styles = getSampleStyleSheet()

    elements = []


    elements.append(
        Paragraph(
            "Audit Trail Report",
            styles["Title"]
        )
    )

    elements.append(
        Spacer(1, 10)
    )


    filter_text = []

    if selected_user_id:

        user = users.get(
            int(selected_user_id)
        )

        if user:

            filter_text.append(
                f"User: {user.full_name} ({user.role})"
            )

    if selected_action:

        filter_text.append(
            f"Action: {selected_action}"
        )

    if selected_record_type:

        filter_text.append(
            f"Record Type: {selected_record_type}"
        )

    if start_date:

        filter_text.append(
            f"From: {start_date}"
        )

    if end_date:

        filter_text.append(
            f"To: {end_date}"
        )


    if filter_text:

        elements.append(
            Paragraph(
                "Filters: " + " | ".join(filter_text),
                styles["Normal"]
            )
        )

    else:

        elements.append(
            Paragraph(
                "Filters: All records",
                styles["Normal"]
            )
        )


    elements.append(
        Spacer(1, 12)
    )


    rows = [[
        "Date & Time",
        "User",
        "Role",
        "Action",
        "Record Type",
        "Record ID",
        "Details"
    ]]


    for log in logs:

        user_name = "System"
        user_role = "-"

        if log.user_id and log.user_id in users:

            user_name = users[
                log.user_id
            ].full_name

            user_role = users[
                log.user_id
            ].role


        rows.append([
            log.timestamp.strftime(
                "%d/%m/%Y %H:%M:%S"
            ),

            user_name,

            user_role,

            log.action,

            log.record_type,

            str(
                log.record_id
                if log.record_id is not None
                else "-"
            ),

            Paragraph(
                log.details or "-",
                styles["BodyText"]
            )
        ])


    audit_table = Table(
        rows,
        repeatRows=1,
        colWidths=[
            2.7 * cm,
            2.6 * cm,
            1.6 * cm,
            1.8 * cm,
            2.0 * cm,
            1.5 * cm,
            5.4 * cm
        ]
    )


    audit_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.lightgrey
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                colors.grey
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP"
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                7
            ),
            (
                "PADDING",
                (0, 0),
                (-1, -1),
                4
            )
        ])
    )


    elements.append(
        audit_table
    )

    elements.append(
        Spacer(1, 15)
    )


    elements.append(
        Paragraph(
            f"Total Records: {len(logs)}",
            styles["Normal"]
        )
    )


    elements.append(
        Paragraph(
            (
                f"Generated by: "
                f"{g.user.full_name} "
                f"({g.user.role})"
            ),
            styles["Normal"]
        )
    )


    doc.build(
        elements
    )


    create_audit_log(
        action="EXPORT",
        record_type="AUDIT",
        record_id=None,
        details=(
            "Exported filtered Audit Trail report to PDF"
        )
    )

    db.session.commit()


    buffer.seek(0)


    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
                "attachment; filename=audit_trail_report.pdf"
        }
    )

#######################################3
if __name__ == "__main__":

    with app.app_context():

        db.create_all()

        admin_username = os.getenv(
            "INITIAL_ADMIN_USERNAME",
            "admin"
        )

        admin_password = os.getenv(
            "INITIAL_ADMIN_PASSWORD"
        )

        admin = User.query.filter_by(
            username=admin_username
        ).first()

        if admin is None and admin_password:

            admin = User(
                full_name="System Administrator",
                username=admin_username,
                password=generate_password_hash(
                    admin_password
                ),
                role="ADMIN",
                is_active=True
            )

            db.session.add(admin)
            db.session.commit()

            print(
                "Initial admin account created."
            )

    app.run(debug=True)