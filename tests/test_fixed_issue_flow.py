import os
import json
from app import create_app
from models import db, Ticket, FixedIssue

# Ensure testing environment
os.environ['FLASK_ENV'] = 'testing'


def test_complete_flow():
    app = create_app()
    with app.app_context():
        db.create_all()
        # create ticket
        ticket = Ticket(title='Flow test ticket', description='desc', category='Test', priority='Low', confidence=0.5)
        db.session.add(ticket)
        db.session.commit()
        tid = ticket.id

    with app.test_client() as client:
        # log in as admin
        with client.session_transaction() as sess:
            sess['admin_logged_in'] = True

        # GET confirm page
        r = client.get(f'/admin/ticket/{tid}/complete-confirm')
        assert r.status_code == 200
        assert 'Confirm Fix' in r.get_data(as_text=True)

        # POST complete
        r2 = client.post(f'/admin/ticket/{tid}/complete', data={'fixed_by': 'unittest', 'notes': 'fixed in test'}, follow_redirects=True)
        assert r2.status_code == 200

    with app.app_context():
        fixed = FixedIssue.query.filter_by(ticket_id=tid).first()
        orig = Ticket.query.get(tid)
        assert fixed is not None
        assert fixed.fixed_by == 'unittest'
        assert orig.status == 'Fixed'
