import os
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_wtf.csrf import CSRFError
import io
import csv
import logging

load_dotenv()

from models import db, Ticket, TicketCorrection, FixedIssue
from classifier import classify_text

csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///tickets.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET', 'dev-secret')
    # Disable CSRF in testing mode
    app.config['WTF_CSRF_ENABLED'] = os.environ.get('FLASK_ENV') != 'testing'
    # Session lifetime for admin login
    app.permanent_session_lifetime = timedelta(hours=int(os.environ.get('SESSION_HOURS', '1')))
    db.init_app(app)
    csrf.init_app(app)
    # Configure basic logging for server-side events
    app.logger.setLevel(logging.INFO)

    # Setup admin password hash: prefer ADMIN_PASSWORD_HASH, fall back to ADMIN_PASSWORD
    admin_hash = os.environ.get('ADMIN_PASSWORD_HASH')
    admin_plain = os.environ.get('ADMIN_PASSWORD')
    if not admin_hash and admin_plain:
        # derive a hash for use at runtime (do NOT write back to .env automatically)
        admin_hash = generate_password_hash(admin_plain)
    app.config['ADMIN_PASSWORD_HASH'] = admin_hash

    with app.app_context():
        db.create_all()

    @app.route('/')
    def index():
        return redirect(url_for('submit_ticket'))

    @app.route('/submit', methods=['GET', 'POST'])
    def submit_ticket():
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            if not description:
                flash('Please provide a description of the issue', 'warning')
                return redirect(url_for('submit_ticket'))

            # Call classifier (OpenAI) to predict category & priority
            result = classify_text(description)
            category = result.get('category', 'other')
            priority = result.get('priority', 'Medium')
            confidence = result.get('confidence', 0.0)

            ticket = Ticket(
                title=title or (description[:60] + '...'),
                description=description,
                category=category,
                priority=priority,
                confidence=confidence,
                status='Open',
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.session.add(ticket)
            db.session.commit()
            flash(f'Ticket submitted — category: {category} (confidence {confidence:.2f}), priority: {priority}', 'success')
            return redirect(url_for('list_tickets'))

        return render_template('submit.html')

    @app.route('/tickets')
    def list_tickets():
        # server-side pagination
        try:
            page = int(request.args.get('page', 1))
        except Exception:
            page = 1
        per_page = int(os.environ.get('TICKETS_PER_PAGE', 10))
        q = Ticket.query.order_by(Ticket.created_at.desc())
        pagination = q.paginate(page=page, per_page=per_page, error_out=False)
        tickets = pagination.items
        return render_template('tickets.html', tickets=tickets, pagination=pagination)

    def admin_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get('admin_logged_in'):
                return redirect(url_for('admin_login', next=request.path))
            return f(*args, **kwargs)
        return decorated

    @app.route('/admin')
    @admin_required
    def admin_index():
        try:
            page = int(request.args.get('page', 1))
        except Exception:
            page = 1
        per_page = int(os.environ.get('ADMIN_TICKETS_PER_PAGE', 15))
        q = Ticket.query.order_by(Ticket.created_at.desc())
        pagination = q.paginate(page=page, per_page=per_page, error_out=False)
        tickets = pagination.items
        # compute recent (today) count server-side using a simple query
        today = datetime.utcnow().date()
        recent_count = Ticket.query.filter(db.func.date(Ticket.created_at) == today).count()
        return render_template('admin.html', tickets=tickets, recent_count=recent_count, pagination=pagination)

    @app.route('/admin/ticket/<int:ticket_id>/edit', methods=['GET', 'POST'])
    @admin_required
    def edit_ticket(ticket_id):
        ticket = Ticket.query.get_or_404(ticket_id)
        if request.method == 'POST':
            new_category = request.form.get('category') or ticket.category
            new_priority = request.form.get('priority') or ticket.priority
            corrected_by = request.form.get('corrected_by') or 'admin'
            notes = request.form.get('notes')

            if (new_category != ticket.category) or (new_priority != ticket.priority):
                correction = TicketCorrection(
                    ticket_id=ticket.id,
                    old_category=ticket.category,
                    new_category=new_category,
                    old_priority=ticket.priority,
                    new_priority=new_priority,
                    corrected_by=corrected_by,
                    notes=notes,
                )
                db.session.add(correction)
                ticket.category = new_category
                ticket.priority = new_priority
                ticket.updated_at = datetime.utcnow()
                db.session.commit()
                flash('Ticket updated and correction logged.', 'success')
            else:
                flash('No changes were made to the ticket.', 'warning')
            return redirect(url_for('admin_index'))

        return render_template('edit_ticket.html', ticket=ticket)


    @app.route('/admin/ticket/<int:ticket_id>/complete', methods=['POST'])
    @admin_required
    def complete_ticket(ticket_id):
        ticket = Ticket.query.get_or_404(ticket_id)
        fixed_by = request.form.get('fixed_by') or 'admin'
        notes = request.form.get('notes') or request.form.get('note') or ''

        # Create a record in the FixedIssue table for audit/reference
        fixed = FixedIssue(
            ticket_id=ticket.id,
            title=ticket.title,
            description=ticket.description,
            category=ticket.category,
            priority=ticket.priority,
            confidence=ticket.confidence,
            status='Fixed',
            fixed_by=fixed_by,
            notes=notes,
        )
        db.session.add(fixed)

        # Mark the original ticket as fixed/closed
        try:
            ticket.status = 'Fixed'
            ticket.updated_at = datetime.utcnow()
        except Exception:
            pass

        db.session.commit()
        flash('Ticket marked as fixed and archived for reference.', 'success')
        return redirect(url_for('admin_index'))


    @app.route('/admin/ticket/<int:ticket_id>/complete-confirm')
    @admin_required
    def confirm_complete(ticket_id):
        ticket = Ticket.query.get_or_404(ticket_id)
        return render_template('complete_ticket.html', ticket=ticket)


    @app.route('/admin/fixed-issues')
    @admin_required
    def list_fixed_issues():
        # support simple filtering via query params: category, priority, fixed_by
        q = FixedIssue.query
        category = request.args.get('category')
        priority = request.args.get('priority')
        fixed_by = request.args.get('fixed_by')
        if category:
            q = q.filter(FixedIssue.category == category)
        if priority:
            q = q.filter(FixedIssue.priority == priority)
        if fixed_by:
            q = q.filter(FixedIssue.fixed_by == fixed_by)

        try:
            page = int(request.args.get('page', 1))
        except Exception:
            page = 1
        per_page = int(os.environ.get('FIXED_PER_PAGE', 15))
        pagination = q.order_by(FixedIssue.fixed_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
        fixed_issues = pagination.items
        return render_template('fixed_issues.html', fixed_issues=fixed_issues, pagination=pagination)


    @app.route('/admin/fixed-issues/export.csv')
    @admin_required
    def export_fixed_issues_csv():
        # Stream a CSV of fixed issues
        fixed_issues = FixedIssue.query.order_by(FixedIssue.fixed_at.desc()).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['id', 'ticket_id', 'title', 'category', 'priority', 'fixed_by', 'fixed_at', 'notes'])
        for f in fixed_issues:
            writer.writerow([f.id, f.ticket_id, f.title, f.category, f.priority, f.fixed_by, f.fixed_at.isoformat(), (f.notes or '')])
        resp = make_response(output.getvalue())
        resp.headers['Content-Type'] = 'text/csv'
        resp.headers['Content-Disposition'] = 'attachment; filename=fixed_issues.csv'
        return resp

    @app.route('/ticket/<int:ticket_id>')
    def ticket_detail(ticket_id):
        ticket = Ticket.query.get_or_404(ticket_id)
        corrections = TicketCorrection.query.filter_by(ticket_id=ticket.id).order_by(TicketCorrection.corrected_at.desc()).all()
        return render_template('ticket_detail.html', ticket=ticket, corrections=corrections)

    @app.route('/admin/login', methods=['GET', 'POST'])
    def admin_login():
        if request.method == 'POST':
            password = request.form.get('password')
            expected_hash = app.config.get('ADMIN_PASSWORD_HASH')
            if expected_hash and check_password_hash(expected_hash, password):
                session.permanent = True
                session['admin_logged_in'] = True
                flash('Logged in as admin.', 'success')
                next_url = request.args.get('next') or url_for('admin_index')
                return redirect(next_url)
            else:
                # Log the failed attempt for auditing
                try:
                    app.logger.warning('Failed admin login attempt from %s', request.remote_addr)
                except Exception:
                    pass
                flash('Invalid password', 'warning')
        return render_template('admin_login.html')

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        # Friendly handling for missing/invalid CSRF tokens so the
        # Werkzeug debugger stacktrace isn't shown to end users.
        try:
            app.logger.warning('CSRF failure: %s from %s', getattr(e, 'description', str(e)), request.remote_addr)
        except Exception:
            pass
        flash('Form submission failed due to a security token issue. Please refresh the page and try again.', 'danger')
        # If the request referenced a 'next' parameter, keep it on redirect
        next_url = request.args.get('next') or request.referrer or url_for('index')
        return redirect(next_url)

    @app.route('/admin/logout')
    def admin_logout():
        session.pop('admin_logged_in', None)
        flash('Logged out', 'success')
        return redirect(url_for('index'))

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
