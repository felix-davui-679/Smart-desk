from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Ticket(db.Model):
    __tablename__ = 'tickets'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), nullable=True)
    priority = db.Column(db.String(50), nullable=True)
    confidence = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='Open')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    corrections = db.relationship('TicketCorrection', backref='ticket', lazy=True)

    def __repr__(self):
        return f"<Ticket {self.id} {self.title}>"


class TicketCorrection(db.Model):
    __tablename__ = 'ticket_corrections'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    old_category = db.Column(db.String(100), nullable=True)
    new_category = db.Column(db.String(100), nullable=True)
    old_priority = db.Column(db.String(50), nullable=True)
    new_priority = db.Column(db.String(50), nullable=True)
    corrected_by = db.Column(db.String(100), nullable=True)
    corrected_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<TicketCorrection {self.id} ticket={self.ticket_id}>"


class FixedIssue(db.Model):
    __tablename__ = 'fixed_issues'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), nullable=True)
    priority = db.Column(db.String(50), nullable=True)
    confidence = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='Fixed')
    fixed_by = db.Column(db.String(100), nullable=True)
    fixed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<FixedIssue {self.id} ticket={self.ticket_id} fixed_at={self.fixed_at}>"
