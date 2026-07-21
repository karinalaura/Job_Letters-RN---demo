from flask import Flask, render_template, request, jsonify, make_response, flash, redirect, url_for, session, current_app, send_file, g
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import Base, Person, PayRecord, Organisation, GeneratedPDF, FlashKey
import os
import sys
import secrets
from datetime import datetime, timedelta, date
from num2words import num2words
from decimal import Decimal

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get(
    "SECRET_KEY",
    "dev_secret_key_change_me_in_prod"
)
app.config['ADMIN_USER_ID'] = 'admin'
app.config['ADMIN_USERNAME'] = os.environ.get('ADMIN_USERNAME', 'admin')
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', 'password')

# --- Custom Timeout Setting ---
SESSION_TIMEOUT_MINUTES = 30 # User logs out after 30 minutes of inactivity

# --- APP CONFIG for SQLite ---
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///sql_app.db"
)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

with app.app_context():
    Base.metadata.create_all(bind=engine)

login_manager = LoginManager()
login_manager.init_app(app)

setattr(login_manager, 'login_view', 'login')
setattr(login_manager, 'login_message', 'Please log in to access this page.')

class User(UserMixin):
    def __init__(self, person_id, employee_badge_number, email, full_name, rank=None, acting_rank=None, is_admin=False):
        self.id = person_id
        self.badge_number = employee_badge_number
        self.email = email
        self.full_name = full_name
        self.rank = rank
        self.acting_rank = acting_rank
        self.is_admin = is_admin

    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(person_id):
    db = SessionLocal()
    user = None
    try:
        if str(person_id) == str(app.config['ADMIN_USER_ID']):
            user = User(
                app.config['ADMIN_USER_ID'],
                None,
                None,
                app.config['ADMIN_USERNAME'],
                rank='Administrator',
                acting_rank=None,
                is_admin=True
            )
        else:
            person_data = db.query(Person).filter(Person.emp_id == person_id).first()
            if person_data:
                user = User(
                    person_data.emp_id,
                    person_data.badge_number,
                    person_data.email,
                    person_data.full_name,
                    person_data.rank,
                    person_data.acting_rank
                )
    except Exception as e:
        print(f"Error loading user (Person ID: {person_id}): {e}")
    finally:
        db.close()
    return user

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('Please enter both username and password.', 'danger')
            return render_template('login.html')

        if username == app.config['ADMIN_USERNAME'] and password == app.config['ADMIN_PASSWORD']:
            user = User(
                app.config['ADMIN_USER_ID'],
                None,
                None,
                username,
                rank='Administrator',
                acting_rank=None,
                is_admin=True
            )

            session.permanent = False
            login_user(user, remember=False)
            session['last_active'] = datetime.now().isoformat()
            session.pop('selected_badge_number', None)
            return redirect(url_for('index'))

        flash('Invalid credentials. Please try again.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear() # Clear all session data, including 'last_active'
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# --- STATIC FILES CONFIG ---
if getattr(sys, 'frozen', False):
    # PyInstaller creates a temp folder and stores path in _MEIPASS
    bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))

@app.before_request
def before_request():
    g.db = SessionLocal()
    
    if current_user.is_authenticated:
        ajax_endpoints = ['get_institutions', 'get_branches', 'get_org_details_ajax']
        is_ajax_request = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Check timeout for non-login, non-AJAX requests
        if request.endpoint != 'login' and request.endpoint not in ajax_endpoints and not is_ajax_request:
            last_active_str = session.get('last_active')
            if last_active_str:
                last_active_time = datetime.fromisoformat(last_active_str)
                if datetime.now() - last_active_time > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                    logout_user()
                    session.clear()
                    flash(f'Your session has expired due to {SESSION_TIMEOUT_MINUTES} minutes of inactivity.', 'info')
                    return redirect(url_for('login'))
        
        # Update activity timestamp for all authenticated requests
        session['last_active'] = datetime.now().isoformat()
        session.modified = True

@app.teardown_request
def teardown_request(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()

# --- Database Query Helper Functions ---
def get_person_by_badge(badge_number):
    """Get person record by badge number"""
    if not badge_number:
        return None
    db = g.db
    return db.query(Person).filter(Person.badge_number == badge_number).first()


def get_selected_badge_number():
    return session.get('selected_badge_number')


def get_selected_person():
    badge_number = get_selected_badge_number()
    if not badge_number:
        return None
    return get_person_by_badge(badge_number)


def get_active_person():
    """Return the active employee record for the current flow."""
    if current_user.is_authenticated and getattr(current_user, 'is_admin', False):
        return get_selected_person()

    if current_user.is_authenticated and current_user.badge_number:
        return get_person_by_badge(current_user.badge_number)

    return None


def get_active_employee_details():
    active_person = get_active_person()
    if not active_person:
        return None
    return get_employee_details(str(active_person.badge_number))


def get_current_pdf_record(db, pdf_id):
    pdf_record = db.query(GeneratedPDF).filter(GeneratedPDF.id == pdf_id).first()
    if not pdf_record:
        return None

    active_person = get_active_person()
    if current_user.is_authenticated and getattr(current_user, 'is_admin', False):
        if not active_person or pdf_record.emp_id != active_person.emp_id:
            return None
    else:
        if pdf_record.emp_id != current_user.id:
            return None

    return pdf_record


def get_pay_record_by_person_id(emp_id):
    """Get most recent pay record for a person"""
    db = g.db
    return db.query(PayRecord).filter(PayRecord.emp_id == emp_id).order_by(PayRecord.period_end.desc()).first()

def get_all_org_types():
    """Get list of unique organization types"""
    db = g.db
    types = db.query(Organisation.type).distinct().all()
    return [t[0] for t in types]

def get_institutions_by_type(org_type):
    """Get list of institutions for a given type"""
    db = g.db
    institutions = db.query(Organisation.institution).filter(Organisation.type == org_type).distinct().all()
    return [i[0] for i in institutions]

def get_branches_by_type_and_institution(org_type, institution_name):
    """Get list of branches for given type and institution"""
    db = g.db
    branches = db.query(Organisation.branch).filter(
        Organisation.type == org_type,
        Organisation.institution == institution_name,
        Organisation.branch.isnot(None),
        Organisation.branch != ''
    ).distinct().order_by(Organisation.branch).all()
    return [b[0] for b in branches]

def get_organisation(org_type, institution, branch=None):
    """Get organization record by type, institution, and optionally branch"""
    db = g.db
    query = db.query(Organisation).filter(
        Organisation.type == org_type,
        Organisation.institution == institution
    )
    
    if branch:
        query = query.filter(Organisation.branch == branch)
    
    return query.first()

def check_organisation_has_branches(org_type, institution):
    """Check if an organization has any meaningful branches"""
    db = g.db
    count = db.query(Organisation).filter(
        Organisation.type == org_type,
        Organisation.institution == institution,
        Organisation.branch.isnot(None),
        Organisation.branch != ''
    ).count()
    return count > 0


def number_to_words_currency(amount):
    if not isinstance(amount, (int, float)):
        return ""

    dollars = int(amount)
    cents = int(round((amount - dollars) * 100))

    words = num2words(dollars).replace('-', ' ').title()

    if cents > 0:
        cents_words = num2words(cents).replace('-', ' ').title()
        return f"{words} Dollars and {cents_words} Cents"
    else:
        return f"{words} Dollars"

def generate_flash_key():
    """Generate a unique URL-safe flash key for document verification"""
    return secrets.token_urlsafe(8)

def get_employee_details(badge_number_str):
    """Get employee details by badge number using direct DB queries"""
    badge_number = str(badge_number_str)
    
    person = get_person_by_badge(badge_number)
    if not person:
        return {'error': f"Badge number {badge_number} not found."}
    
    pay_record = get_pay_record_by_person_id(person.emp_id)
    if not pay_record:
        return {'error': f"No payslip data for badge number {badge_number}."}
    
    # Format engagement date
    formatted_date = person.enlistment_date.strftime('%B %d, %Y') if person.enlistment_date else 'N/A'
    
    # Use gross_total directly from pay record
    gross_total = float(pay_record.gross_total) if pay_record.gross_total else 0.0

    return {
        'badge': person.badge_number,
        'rank': person.rank,
        'acting_rank': person.acting_rank if person.acting_rank else None,
        'full_name': person.full_name,
        'engagement_date': formatted_date,
        'total_gross': gross_total,
        'total_gross_words': number_to_words_currency(gross_total)
    }


def get_org_details(org_type, institution, branch=None):
    """Get organization details using direct DB queries"""
    if not org_type or not institution:
        return {'error': 'Type and Institution must be selected.'}
    
    # Check if branches exist for this institution
    has_branches = check_organisation_has_branches(org_type, institution)
    
    if branch and branch != '':
        # Specific branch selected
        org = get_organisation(org_type, institution, branch)
    elif not has_branches:
        # No branches exist, get the institution record
        org = get_organisation(org_type, institution)
    else:
        # Branches exist but none selected
        return {'error': 'Please select a branch to view specific organization details.'}
    
    if not org:
        return {'error': 'No details found for the selected institution and branch.'}
    
    return {
        'type': org.type,
        'manager': org.manager if org.manager else '',
        'institution': org.institution,
        'branch': org.branch if org.branch else '',
        'address1': org.address1 if org.address1 else '',
        'address2': org.address2 if org.address2 else '',
        'address3': org.address3 if org.address3 else '',
        'city': org.city if org.city else ''
    }

# --- ROUTES ---

@app.route('/', methods=['GET'])
@login_required
def index():
    employee_data = None
    selected_badge = get_selected_badge_number()
    types = []

    if selected_badge:
        employee_data = get_employee_details(str(selected_badge))

    types = get_all_org_types()

    return render_template('index.html',
                           employee_data=employee_data,
                           selected_badge=selected_badge,
                           types=types,
                           selected_type='',
                           institutions=[],
                           selected_institution='',
                           branches_for_selected_institution=[],
                           selected_branch='',
                           org_details=None,
                           current_badge=selected_badge)


@app.route('/search_badge', methods=['POST'])
@login_required
def search_badge():
    badge_number = request.form.get('badge_number', '').strip()
    if not badge_number:
        flash('Please enter a badge number to search.', 'danger')
        return redirect(url_for('index'))

    g.db = SessionLocal()
    try:
        person_data = get_person_by_badge(badge_number)
    finally:
        g.db.close()

    if not person_data:
        flash(f'Badge number {badge_number} not found.', 'danger')
        session.pop('selected_badge_number', None)
    else:
        session['selected_badge_number'] = badge_number
        flash(f'Employee details loaded for badge {badge_number}.', 'success')

    return redirect(url_for('index'))


@app.route('/clear_badge_selection')
@login_required
def clear_badge_selection():
    session.pop('selected_badge_number', None)
    flash('Badge selection cleared. Search for a badge to populate employee details.', 'info')
    return redirect(url_for('index'))


@app.route('/get_institutions/<org_type>')
@login_required
def get_institutions(org_type):
    institutions = get_institutions_by_type(org_type)
    return jsonify(institutions)


@app.route('/get_branches/<org_type>/<institution_name>')
@login_required
def get_branches(org_type, institution_name):
    branches = get_branches_by_type_and_institution(org_type, institution_name)
    return jsonify(branches)


@app.route('/update_gross_amount', methods=['POST'])
@login_required
def update_gross_amount():
    """Update the gross_total in the pay record for the selected employee."""
    try:
        data = request.get_json()
        new_amount = data.get('amount')
        
        if new_amount is None or not isinstance(new_amount, (int, float)) or new_amount <= 0:
            return jsonify({'success': False, 'error': 'Invalid amount'}), 400
        
        selected_person = get_selected_person()
        if not selected_person:
            return jsonify({'success': False, 'error': 'No employee selected'}), 400
        
        db = SessionLocal()
        try:
            pay_record = db.query(PayRecord).filter(
                PayRecord.emp_id == selected_person.emp_id
            ).first()
            
            if not pay_record:
                return jsonify({'success': False, 'error': 'No pay record found'}), 404
            
            pay_record.gross_total = Decimal(str(new_amount))  # type: ignore
            db.commit()
            
            return jsonify({
                'success': True,
                'message': 'Gross amount updated successfully',
                'new_amount': new_amount
            })
        finally:
            db.close()
            
    except Exception as e:
        print(f"Error updating gross amount: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/get_org_details_ajax', methods=['POST'])
@login_required
def get_org_details_ajax():
    data = request.get_json()
    org_type = data.get('type')
    institution = data.get('institution')
    branch = data.get('branch')

    org_details = get_org_details(org_type, institution, branch)

    if org_details and not org_details.get('error'):
        response_data = {
            'type': org_details.get('type', ''),
            'manager': org_details.get('manager',''),
            'institution': org_details.get('institution', ''),
            'branch': org_details.get('branch', ''),
            'address1': org_details.get('address1', ''),
            'address2': org_details.get('address2', ''),
            'address3': org_details.get('address3',''),
            'city': org_details.get('city', ''),
            'error': False
        }
        return jsonify(response_data)
    else:
        print(f"Org details not found for type={org_type}, inst={institution}, branch={branch}. Error: {org_details.get('error', 'Unknown error') if org_details else 'No details returned'}")
        return jsonify({'error': org_details.get('error', 'Organization details not found.') if org_details else 'Organization details not found.'}), 404


@app.route('/generate_job_letter_preview', methods=['POST'])
@login_required
def generate_job_letter_preview():
    selected_person = get_selected_person()
    is_other_org = request.form.get('is_other_org_for_letter') == 'true'

    employee_data = None
    if selected_person:
        employee_data = get_employee_details(str(selected_person.badge_number))
    else:
        flash('Please search and select an employee badge before generating a job letter.', 'danger')
        return redirect(url_for('index'))

    if employee_data and employee_data.get('error'):
        flash(employee_data['error'], 'danger')
        return redirect(url_for('index'))

    org_details = None
    if is_other_org:
        org_details = {
            'type': 'Other',
            'institution': request.form.get('other_institution_name_for_letter'),
            'branch': '',
            'address1': request.form.get('other_address_line1_for_letter'),
            'address2': request.form.get('other_address_line2_for_letter'),
            'address3': request.form.get('other_address_line3_for_letter'),
            'city': request.form.get('other_city_for_letter')
        }
        if not org_details['institution'] or not org_details['address1'] or not org_details['city']:
            flash("Missing required fields for 'Other Organization'.", 'danger')
            return redirect(url_for('index'))
    else:
        type_for_letter = request.form.get('type_for_letter')
        institution_for_letter = request.form.get('institution_for_letter')
        branch_for_letter = request.form.get('branch_for_letter')
        if type_for_letter and institution_for_letter:
            # Check if branches exist for this institution before proceeding
            has_branches = check_organisation_has_branches(type_for_letter, institution_for_letter)
            
            # If branches exist but none is selected, require branch selection
            if has_branches and (not branch_for_letter or branch_for_letter.strip() == ''):
                flash("Please select a branch for the selected institution.", 'danger')
                return redirect(url_for('index'))
                
            org_details = get_org_details(type_for_letter, institution_for_letter, branch_for_letter)
            if org_details.get('error'):
                flash(org_details['error'], 'danger')
                return redirect(url_for('index'))
        else:
            flash("Missing organization selection or details.", 'danger')
            return redirect(url_for('index'))

    current_date = datetime.now().strftime('%B %d, %Y')

    session['job_letter_data'] = {
        'employee_data': employee_data,
        'org_details': org_details,
        'current_date': current_date
    }

    return render_template('job_letter.html',
                           employee_data=employee_data,
                           org_details=org_details,
                           current_date=current_date,
                           preview_mode=True)




@app.route('/pdf_history')
@login_required
def pdf_history():
    """View history of generated PDFs for the selected employee (past 6 months only)"""
    selected_person = get_selected_person()
    db = SessionLocal()
    try:
        six_months_ago = datetime.now() - timedelta(days=180)
        if selected_person:
            pdfs = db.query(GeneratedPDF).filter(
                GeneratedPDF.emp_id == selected_person.emp_id,
                GeneratedPDF.generated_at >= six_months_ago
            ).order_by(GeneratedPDF.id.desc()).all()
            employee_data = get_active_employee_details()
        else:
            pdfs = []
            employee_data = None
            flash('Please search for a badge number to view PDF history.', 'info')
        
        return render_template('pdf_history.html', pdfs=pdfs, employee_data=employee_data, selected_badge=get_selected_badge_number())
    finally:
        db.close()



@app.route('/pdfs/<int:pdf_id>/<path:filename>')
@login_required
def serve_pdf(pdf_id, filename):
    """Serve PDF wrapped in HTML with proper title"""
    db = SessionLocal()
    try:
        pdf_record = get_current_pdf_record(db, pdf_id)
        
        if not pdf_record or not os.path.exists(str(pdf_record.file_path)):
            flash('PDF not found or no longer available', 'error')
            return redirect(url_for('pdf_history'))
        
        # Return HTML page that embeds the PDF with proper title
        pdf_data_url = url_for('serve_pdf_direct', pdf_id=pdf_id, filename=filename)
        
        html_content = f'''
<!DOCTYPE html>
<html>
<head>
    <title>Job Letter</title>
    <style>
        body {{ margin: 0; padding: 0; }}
        iframe {{ width: 100%; height: 100vh; border: none; }}
    </style>
</head>
<body>
    <iframe src="{pdf_data_url}" type="application/pdf"></iframe>
</body>
</html>
'''
        return html_content
    finally:
        db.close()

@app.route('/pdf_direct/<int:pdf_id>/<path:filename>')
@login_required  
def serve_pdf_direct(pdf_id, filename):
    """Serve PDF file directly"""
    db = SessionLocal()
    try:
        pdf_record = get_current_pdf_record(db, pdf_id)
        
        if not pdf_record or not os.path.exists(str(pdf_record.file_path)):
            return "PDF not found", 404
        
        # Use send_file for direct PDF serving
        return send_file(
            str(pdf_record.file_path),
            mimetype='application/pdf',
            as_attachment=False,
            download_name='Job Letter.pdf'
        )
    finally:
        db.close()

@app.route('/view_saved_pdf/<int:pdf_id>')
@login_required
def view_saved_pdf(pdf_id):
    """Redirect to proper PDF serving route with filename"""
    db = SessionLocal()
    try:
        pdf_record = get_current_pdf_record(db, pdf_id)
        
        if not pdf_record:
            flash('PDF not found or no longer available', 'error')
            return redirect(url_for('pdf_history'))
        
        # Simple filename for browser tab
        view_filename = "Job_Letter.pdf"
        
        return redirect(url_for('serve_pdf', pdf_id=pdf_id, filename=view_filename))
    finally:
        db.close()

@app.route('/download_saved_pdf/<int:pdf_id>')
@login_required
def download_saved_pdf(pdf_id):
    """Download a previously generated PDF"""
    db = SessionLocal()
    try:
        pdf_record = get_current_pdf_record(db, pdf_id)
        
        if not pdf_record or not os.path.exists(str(pdf_record.file_path)):
            flash('PDF not found or no longer available', 'error')
            return redirect(url_for('pdf_history'))
        
        with open(str(pdf_record.file_path), 'rb') as f:
            pdf_data = f.read()
        
        response = make_response(pdf_data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename={pdf_record.filename}'
        return response
    finally:
        db.close()

@app.route('/download_job_letter_pdf', methods=['GET'])
@login_required
def download_job_letter_pdf():
    letter_data = session.get('job_letter_data')

    if not letter_data:
        flash("No letter data found for PDF generation. Please generate the letter first.", 'danger')
        return redirect(url_for('index'))

    employee_data = letter_data['employee_data']
    org_details = letter_data['org_details']
    current_date = letter_data['current_date']

    # Generate flash key for verification
    flash_key = generate_flash_key()

    # Generate PDF using ReportLab with flash key
    from pdf_generator import create_job_letter_pdf
    
    try:
        pdf_bytes = create_job_letter_pdf(employee_data, org_details, current_date, flash_key)
    except Exception as e:
        print(f"ReportLab error: {e}")
        flash("Error generating PDF.", 'danger')
        return redirect(url_for('generate_job_letter_preview'))

    # Save PDF to server directory
    pdf_directory = os.path.join(current_app.root_path, 'generated_pdfs')
    os.makedirs(pdf_directory, exist_ok=True)
    
    filename = "JobLetter"
    if employee_data and not employee_data.get('error'):
        filename = f"JobLetter_{employee_data['full_name'].replace(' ', '_')}"
    
    # Add timestamp to avoid conflicts
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    full_filename = f"{filename}_{timestamp}.pdf"
    pdf_path = os.path.join(pdf_directory, full_filename)
    
    # Save to file
    with open(pdf_path, 'wb') as f:
        f.write(pdf_bytes)
    
    # Log to database with verification information and create flash key
    try:
        db = SessionLocal()
        selected_person = get_selected_person()
        if not selected_person:
            flash('No employee selected for PDF generation.', 'danger')
            return redirect(url_for('index'))
        
        pdf_record = GeneratedPDF(
            emp_id=selected_person.emp_id,
            filename=full_filename,
            file_path=pdf_path,
            organization_name=org_details.get('institution', '') if org_details else '',
            generated_at=datetime.now(),  # Explicitly set local time
            
            # Verification data for QR code generation
            employee_badge_number=employee_data.get('badge'),
            employee_full_name=employee_data.get('full_name'),
            employee_rank=employee_data.get('rank'),
            employee_acting_rank=employee_data.get('acting_rank'),
            employee_engagement_date=datetime.strptime(employee_data.get('engagement_date'), '%B %d, %Y').date() if employee_data.get('engagement_date') and employee_data.get('engagement_date') != 'N/A' else None,
            employee_gross_salary=employee_data.get('total_gross')
        )
        db.add(pdf_record)
        db.flush()  # Flush to get the pdf_record.id before commit
        
        # Save the flash key that was already generated and embedded in the PDF
        flash_record = FlashKey(
            key=flash_key,
            pdf_id=pdf_record.id
        )
        db.add(flash_record)
        db.commit()
        db.close()
    except Exception as e:
        print(f"Error logging PDF to database: {e}")

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={full_filename}'

    return response


# ============================================================================
# DOCUMENT VERIFICATION ROUTE (PUBLIC)
# ============================================================================
# This section handles the public verification of job letters using flash keys.
# Update the verification.html template.
# ============================================================================

@app.route('/verify/<flash_key>')
def verify_document(flash_key):
    """
    Public route to verify document authenticity using flash key.
    
    This endpoint is accessed by scanning the QR code on job letters.
    It validates the flash key and displays document information.
    
    
    - This route is PUBLIC (no login required)
    - Template: templates/verification.html
    - Status values: 'valid', 'invalid', or 'error'
    - Change the verification.html template, was used for testing
    """
    db = SessionLocal()
    try:
        # ========================================
        # Step 1: Look up the flash key in database
        # ========================================
        flash_record = db.query(FlashKey).filter(FlashKey.key == flash_key).first()
        
        if not flash_record:
            # Flash key doesn't exist
            return render_template('verification.html', 
                                   status='invalid',
                                   message='Invalid verification key. This document could not be verified.')
        
        # ========================================
        # Step 2: Get the associated PDF record
        # ========================================
        pdf_record = db.query(GeneratedPDF).filter(GeneratedPDF.id == flash_record.pdf_id).first()
        
        if not pdf_record:
            # Flash key exists but PDF record is missing
            return render_template('verification.html',
                                   status='error',
                                   message='Verification record found but document details are unavailable.')
        
        # ========================================
        # Step 3: Get current employee status
        # ========================================
        employee = db.query(Person).filter(Person.emp_id == pdf_record.emp_id).first()
        
        # ========================================
        # Step 4: Prepare verification data
        # Add/remove fields as needed
        # ========================================
        verification_data = {
            'flash_key': flash_key,
            'badge_number': pdf_record.employee_badge_number,
            'rank': pdf_record.employee_rank,
            'acting_rank': pdf_record.employee_acting_rank if pdf_record.employee_acting_rank is not None else 'N/A',
            'full_name': pdf_record.employee_full_name,
            'engagement_date': pdf_record.employee_engagement_date.strftime('%d %B %Y') if pdf_record.employee_engagement_date is not None else 'N/A',
            'total_gross': f"${pdf_record.employee_gross_salary:,.2f}" if pdf_record.employee_gross_salary is not None else 'N/A',
            'org_name': pdf_record.organization_name,
            'issue_date': pdf_record.generated_at.strftime('%d %B %Y %I:%M %p'),
            'current_employment': 'Active' if employee else 'Record Not Found'
        }
        
        # ========================================
        # Step 5: Render verification template
        # Customize verification.html
        # ========================================
        return render_template('verification.html',
                               status='valid',
                               data=verification_data)
        
    except Exception as e:
        # Log error and show generic error message
        print(f"Error verifying document: {e}")
        return render_template('verification.html',
                               status='error',
                               message='An error occurred during verification. Please try again later.')
    finally:
        db.close()


# ============================================================================
# END OF VERIFICATION SECTION
# ============================================================================


if __name__ == '__main__':
    app.run(host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )