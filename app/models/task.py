from app import db
import json
from datetime import datetime

class DownloadTask(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    directory = db.Column(db.String(200))
    status = db.Column(db.String(20), default="running")
    progress = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    name = db.Column(db.String(200))
    error_message = db.Column(db.Text)
    file_data = db.Column(db.Text)  # JSON string of file info
    
    @property
    def files(self):
        if not self.file_data:
            return []
        return json.loads(self.file_data)
    
    @files.setter
    def files(self, value):
        self.file_data = json.dumps(value)
    
    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "directory": self.directory,
            "status": self.status,
            "progress": self.progress,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "name": self.name,
            "error_message": self.error_message,
            "files": self.files
        }
