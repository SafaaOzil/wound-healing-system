from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash

from models import db, Patient, Wound, Visit


app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///wound_system.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "dev-secret-key"

db.init_app(app)


@app.route("/")
def dashboard():
    total_patients = Patient.query.count()
    total_wounds = Wound.query.count()
    total_visits = Visit.query.count()

    active_wounds = Wound.query.filter_by(status="ACTIVE").count()

    return render_template(
        "dashboard.html",
        total_patients=total_patients,
        total_wounds=total_wounds,
        total_visits=total_visits,
        active_wounds=active_wounds
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

    return render_template(
        "patient_details.html",
        patient=patient
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













if __name__ == "__main__":

    with app.app_context():
        db.create_all()

    app.run(debug=True)


