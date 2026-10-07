from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash

from models import db, Patient, Wound, Visit


import os
from werkzeug.utils import secure_filename



app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///wound_system.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "dev-secret-key"

app.config["UPLOAD_FOLDER"] = "static/uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db.init_app(app)


@app.route("/")
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
def patients():
    all_patients = Patient.query.order_by(Patient.created_at.desc()).all()

    return render_template(
        "patients.html",
        patients=all_patients
    )


@app.route("/patients/add", methods=["GET", "POST"])
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



if __name__ == "__main__":

    with app.app_context():
        db.create_all()

    app.run(debug=True)


