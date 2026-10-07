from datetime import datetime


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


app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///wound_system.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "dev-secret-key"

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
            flash("Patient ID and full name are required.", "error")
            return redirect(url_for("add_patient"))

        existing_patient = Patient.query.filter_by(
            patient_id=patient_id
        ).first()

        if existing_patient:
            flash("A patient with this ID already exists.", "error")
            return redirect(url_for("add_patient"))

        parsed_birth_date = None

        if birth_date:
            try:
                parsed_birth_date = datetime.strptime(
                    birth_date,
                    "%Y-%m-%d"
                ).date()

            except ValueError:
                flash("Invalid birth date.", "error")
                return redirect(url_for("add_patient"))

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
            details=f"Created patient: {new_patient.full_name}"
        )

        db.session.commit()
        flash("Patient added successfully.", "success")

        return redirect(url_for("patients"))

    return render_template("add_patient.html")

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

        visit_date = request.form.get("visit_date")
        length_cm = request.form.get("length_cm")
        width_cm = request.form.get("width_cm")
        depth_cm = request.form.get("depth_cm")
        pain_level = request.form.get("pain_level")
        wound_condition = request.form.get("wound_condition")
        notes = request.form.get("notes")

        if not visit_date or not length_cm or not width_cm:
            flash("Visit date, length and width are required.", "error")
            return redirect(
                url_for("add_visit", wound_id=wound.id)
            )

        try:
            parsed_date = datetime.strptime(
                visit_date,
                "%Y-%m-%d"
            ).date()

            length_cm = float(length_cm)
            width_cm = float(width_cm)

            depth_cm = (
                float(depth_cm)
                if depth_cm
                else None
            )

            pain_level = (
                int(pain_level)
                if pain_level
                else None
            )

        except ValueError:
            flash("Invalid visit data.", "error")
            return redirect(
                url_for("add_visit", wound_id=wound.id)
            )

        image_path = None

        image = request.files.get("image")

        if image and image.filename:

            filename = secure_filename(image.filename)

            filename = f"{wound.id}_{datetime.now().timestamp()}_{filename}"

            save_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )

            image.save(save_path)

            image_path = f"uploads/{filename}"

        new_visit = Visit(
            wound_id=wound.id,
            visit_date=parsed_date,
            length_cm=length_cm,
            width_cm=width_cm,
            depth_cm=depth_cm,
            pain_level=pain_level,
            wound_condition=wound_condition,
            notes=notes,
            image_path=image_path
        )

        db.session.add(new_visit)
        db.session.flush()

        create_audit_log(
            action="CREATE",
            record_type="VISIT",
            record_id=new_visit.id,
            details=(
                f"Added visit for wound #{wound.id}. "
                f"Area: {new_visit.area} cm². "
                f"Pain: {new_visit.pain_level if new_visit.pain_level is not None else '-'}"
            )
        )

        db.session.commit()

        flash("Visit added successfully.", "success")

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



if __name__ == "__main__":

    with app.app_context():

        db.create_all()

        admin = User.query.filter_by(
            username="admin"
        ).first()

        if admin is None:

            admin = User(
                full_name="System Administrator",
                username="admin",
                password=generate_password_hash(
                    "Admin123!"
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


