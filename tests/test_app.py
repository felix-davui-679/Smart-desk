import os
import tempfile
import pytest
from app import create_app
from models import db, Ticket


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / 'test.db'
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{db_file}')
    monkeypatch.setenv('FLASK_ENV', 'testing')
    app = create_app()
    app.config['TESTING'] = True

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client


def test_submit_and_list(client):
    # Submit a ticket
    resp = client.post('/submit', data={'title': 'Test', 'description': 'My printer is on fire'})
    assert resp.status_code == 302

    # List tickets
    resp = client.get('/tickets')
    assert resp.status_code == 200
    assert b'printer' in resp.data.lower() or b'printer' in resp.data
