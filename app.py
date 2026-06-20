import os
import json
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_wtf.csrf import CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import io
import csv
import logging

load_dotenv()

from models import db, Ticket, TicketCorrection, FixedIssue, utcnow
from classifier import classify_text

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)


def _safe_next(target):
    """Return target only if it's a same-site relative path, else None.

    Guards against open-redirects: rejects absolute URLs (with scheme and/or
    netloc) and anything that isn't an in-app path.
    """
    if not target:
        return None
    u = urlparse(target)
    return target if (not u.scheme and not u.netloc and target.startswith('/')) else None


def _csv_safe(v):
    """Neutralize CSV formula injection by prefixing risky values with a quote."""
    s = '' if v is None else str(v)
    if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + s
    return s


def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///tickets.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Session signing key. Require an explicit secret in production; in
    # development fall back to a random per-process key so sessions still work
    # without a hard-coded, guessable default.
    is_production = os.environ.get('FLASK_ENV') == 'production'
    flask_secret = os.environ.get('FLASK_SECRET')
    if not flask_secret:
        if is_production:
            raise RuntimeError(
                'FLASK_SECRET must be set in production. Generate one with '
                '`python -c "import secrets; print(secrets.token_hex(32))"`.'
            )
        flask_secret = secrets.token_hex(32)
    app.config['SECRET_KEY'] = flask_secret
    # Harden the session cookie.
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = is_production
    # Disable CSRF in testing mode
    app.config['WTF_CSRF_ENABLED'] = os.environ.get('FLASK_ENV') != 'testing'
    # Disable rate limiting during tests so the suite doesn't trip the limits.
    app.config['RATELIMIT_ENABLED'] = os.environ.get('FLASK_ENV') != 'testing'
    # Session lifetime for admin login
    app.permanent_session_lifetime = timedelta(hours=int(os.environ.get('SESSION_HOURS', '1')))
    # In development, don't let the browser cache static assets (CSS/JS/SVG)
    # so design changes show up immediately on refresh.
    if not is_production:
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    # Expose a cache-busting version string to templates based on the CSS
    # file's last-modified time, so updated styles bypass the browser cache.
    @app.context_processor
    def inject_asset_version():
        try:
            css_path = os.path.join(app.static_folder, 'style.css')
            version = str(int(os.path.getmtime(css_path)))
        except OSError:
            version = '0'
        return {'asset_version': version}

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
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
    @limiter.limit("10 per hour", methods=["POST"])
    def submit_ticket():
        if request.method == 'POST':
            title = request.form.get('title', '').strip()[:255]
            description = request.form.get('description', '').strip()[:5000]
            if not description:
                flash('Please provide a description of the issue', 'warning')
                return redirect(url_for('submit_ticket'))
            # Hard-cap input size to limit classifier cost / DoS.
            if not (1 <= len(description) <= 5000):
                flash('Description must be between 1 and 5000 characters', 'warning')
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
                created_at=utcnow(),
                updated_at=utcnow(),
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
        today = utcnow().date()
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
                ticket.updated_at = utcnow()
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
            ticket.updated_at = utcnow()
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
            writer.writerow([_csv_safe(v) for v in [
                f.id, f.ticket_id, f.title, f.category, f.priority,
                f.fixed_by, f.fixed_at.isoformat(), (f.notes or ''),
            ]])
        resp = make_response(output.getvalue())
        resp.headers['Content-Type'] = 'text/csv'
        resp.headers['Content-Disposition'] = 'attachment; filename=fixed_issues.csv'
        return resp

    @app.route('/ticket/<int:ticket_id>')
    def ticket_detail(ticket_id):
        ticket = Ticket.query.get_or_404(ticket_id)
        # The ticket queue (title/description/category/priority/confidence) is
        # public by design. Correction history exposes staff identity and
        # internal notes, so only fetch it for logged-in admins.
        if session.get('admin_logged_in'):
            corrections = TicketCorrection.query.filter_by(ticket_id=ticket.id).order_by(TicketCorrection.corrected_at.desc()).all()
        else:
            corrections = []
        return render_template('ticket_detail.html', ticket=ticket, corrections=corrections)

    @app.route('/admin/login', methods=['GET', 'POST'])
    @limiter.limit("5 per minute; 30 per hour", methods=["POST"])
    def admin_login():
        if request.method == 'POST':
            password = request.form.get('password')
            expected_hash = app.config.get('ADMIN_PASSWORD_HASH')
            if expected_hash and check_password_hash(expected_hash, password):
                session.permanent = True
                session['admin_logged_in'] = True
                flash('Logged in as admin.', 'success')
                next_url = _safe_next(request.args.get('next')) or url_for('admin_index')
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
        # If the request referenced a 'next' parameter, keep it on redirect, but
        # only when it's a safe same-site path (avoid open-redirects).
        next_url = _safe_next(request.args.get('next')) or _safe_next(request.referrer) or url_for('index')
        return redirect(next_url)

    @app.route('/admin/logout', methods=['POST'])
    def admin_logout():
        session.clear()
        flash('Logged out', 'success')
        return redirect(url_for('index'))

    @app.after_request
    def set_security_headers(resp):
        resp.headers['X-Frame-Options'] = 'DENY'
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        resp.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net "
            "https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "script-src 'self' https://cdn.jsdelivr.net"
        )
        # Only advertise HSTS when serving over HTTPS (production).
        if app.config.get('SESSION_COOKIE_SECURE'):
            resp.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return resp

    return app


if __name__ == '__main__':
    app = create_app()
    # Only enable the Werkzeug debug server outside of production. Exposing the
    # debugger in production is a remote-code-execution risk.
    debug = os.environ.get('FLASK_ENV') != 'production'
    # Bind to loopback by default; exposing on all interfaces must be an
    # explicit opt-in via the HOST env var.
    host = os.environ.get('HOST', '127.0.0.1')
    app.run(host=host, port=int(os.environ.get('PORT', 5000)), debug=debug)
