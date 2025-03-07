from flask_mail import Mail, Message
from flask import current_app

mail = Mail()

def send_completion_notification(user_email, task_id, task_name, status):
    """Send email notification when a download completes or fails"""
    if not current_app.config['MAIL_ENABLED']:
        return
        
    status_word = "completed successfully" if status == "completed" else "failed"
    msg = Message(
        f"Download {status_word}: {task_name}",
        recipients=[user_email]
    )
    msg.body = f"""
Your download task has {status_word}.

Task Details:
- Name: {task_name}
- ID: {task_id}
- Status: {status}

You can view the details on your dashboard.
    """
    
    mail.send(msg)
