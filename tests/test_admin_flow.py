"""Integration tests for admin auth gating, correction logging and CSV export."""
import pytest

from app import create_app
from models import db, Ticket, TicketCorrection, FixedIssue


@pytest.fixture
def app(tmp_path, monkeypatch):
    db_file = tmp_path / 'test.db'
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{db_file}')
    monkeypatch.setenv('FLASK_ENV', 'testing')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    application = create_app()
    application.config['TESTING'] = True
    with application.app_context():
        db.create_all()
    return application


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def _login(client):
    with client.session_transaction() as sess:
        sess['admin_logged_in'] = True


def _make_ticket(app, **kwargs):
    defaults = dict(title='T', description='desc', category='software',
                    priority='Medium', confidence=0.5, status='Open')
    defaults.update(kwargs)
    with app.app_context():
        ticket = Ticket(**defaults)
        db.session.add(ticket)
        db.session.commit()
        return ticket.id


def test_admin_requires_login(client):
    resp = client.get('/admin')
    assert resp.status_code == 302
    assert '/admin/login' in resp.headers['Location']


def test_admin_accessible_after_login(client):
    _login(client)
    resp = client.get('/admin')
    assert resp.status_code == 200


def test_edit_logs_correction(app, client):
    tid = _make_ticket(app, category='software', priority='Medium')
    _login(client)
    resp = client.post(f'/admin/ticket/{tid}/edit',
                       data={'category': 'networking', 'priority': 'High',
                             'corrected_by': 'tester', 'notes': 'reclassified'},
                       follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        ticket = Ticket.query.get(tid)
        assert ticket.category == 'networking'
        assert ticket.priority == 'High'
        corrections = TicketCorrection.query.filter_by(ticket_id=tid).all()
        assert len(corrections) == 1
        assert corrections[0].old_category == 'software'
        assert corrections[0].new_category == 'networking'
        assert corrections[0].corrected_by == 'tester'


def test_edit_without_changes_logs_nothing(app, client):
    tid = _make_ticket(app, category='software', priority='Medium')
    _login(client)
    client.post(f'/admin/ticket/{tid}/edit',
                data={'category': 'software', 'priority': 'Medium'})
    with app.app_context():
        assert TicketCorrection.query.filter_by(ticket_id=tid).count() == 0


def test_csv_export_contains_fixed_issue(app, client):
    tid = _make_ticket(app, title='Broken laptop')
    _login(client)
    client.post(f'/admin/ticket/{tid}/complete',
                data={'fixed_by': 'tester', 'notes': 'replaced'})

    resp = client.get('/admin/fixed-issues/export.csv')
    assert resp.status_code == 200
    assert resp.headers['Content-Type'].startswith('text/csv')
    body = resp.get_data(as_text=True)
    assert 'ticket_id' in body  # header row
    assert 'Broken laptop' in body
    assert 'tester' in body

    with app.app_context():
        assert FixedIssue.query.filter_by(ticket_id=tid).count() == 1


def test_csv_export_requires_login(client):
    resp = client.get('/admin/fixed-issues/export.csv')
    assert resp.status_code == 302
    assert '/admin/login' in resp.headers['Location']
