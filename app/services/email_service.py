import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

class EmailService:
    """Service for sending emails via SMTP"""
    
    def __init__(self):
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_email = os.getenv('SMTP_EMAIL')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.app_url = os.getenv('APP_URL', 'http://localhost:5173')
        
    def send_invitation_email(self, recipient_email, recipient_name, project_name, inviter_name):
        """
        Send a project invitation email to a user
        
        Args:
            recipient_email (str): Email address of the person being invited
            recipient_name (str): Name of the person being invited
            project_name (str): Name of the project they're being invited to
            inviter_name (str): Name of the person who sent the invitation
        
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.smtp_email
            msg['To'] = recipient_email
            msg['Subject'] = f'You\'ve been invited to collaborate on "{project_name}"'
            
            # Create HTML email body
            html_body = self._create_invitation_html(
                recipient_name, 
                project_name, 
                inviter_name
            )
            
            # Attach HTML body
            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_email, self.smtp_password)
                server.send_message(msg)
            
            print(f"✅ Invitation email sent to {recipient_email}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to send email to {recipient_email}: {str(e)}")
            return False
    
    def _create_invitation_html(self, recipient_name, project_name, inviter_name):
        """Create HTML template for invitation email"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f5; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <!-- Header -->
                    <tr>
                        <td style="padding: 40px 40px 20px 40px; text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px 8px 0 0;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 28px; font-weight: 600;">Research Collaboration</h1>
                        </td>
                    </tr>
                    
                    <!-- Body -->
                    <tr>
                        <td style="padding: 40px;">
                            <h2 style="margin: 0 0 20px 0; color: #333333; font-size: 24px; font-weight: 600;">
                                You've been invited! 🎉
                            </h2>
                            
                            <p style="margin: 0 0 15px 0; color: #666666; font-size: 16px; line-height: 1.6;">
                                Hi {recipient_name or 'there'},
                            </p>
                            
                            <p style="margin: 0 0 15px 0; color: #666666; font-size: 16px; line-height: 1.6;">
                                <strong style="color: #333333;">{inviter_name}</strong> has invited you to collaborate on the research project:
                            </p>
                            
                            <div style="background-color: #f8f9fa; border-left: 4px solid #667eea; padding: 20px; margin: 25px 0; border-radius: 4px;">
                                <p style="margin: 0; color: #333333; font-size: 18px; font-weight: 600;">
                                    📚 {project_name}
                                </p>
                            </div>
                            
                            <p style="margin: 0 0 25px 0; color: #666666; font-size: 16px; line-height: 1.6;">
                                Start collaborating now by logging into your account and accessing the project workspace.
                            </p>
                            
                            <!-- CTA Button -->
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td align="center" style="padding: 20px 0;">
                                        <a href="{self.app_url}" style="display: inline-block; padding: 15px 40px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #ffffff; text-decoration: none; border-radius: 6px; font-size: 16px; font-weight: 600; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);">
                                            View Project
                                        </a>
                                    </td>
                                </tr>
                            </table>
                            
                            <p style="margin: 25px 0 0 0; color: #999999; font-size: 14px; line-height: 1.6;">
                                If you have any questions, feel free to reach out to {inviter_name} or our support team.
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 30px 40px; background-color: #f8f9fa; border-radius: 0 0 8px 8px; border-top: 1px solid #e9ecef;">
                            <p style="margin: 0; color: #999999; font-size: 12px; text-align: center; line-height: 1.5;">
                                This is an automated message from Research Management Platform.<br>
                                © 2024 Research Management. All rights reserved.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
        """


# Create a singleton instance
email_service = EmailService()


def send_invitation_email(recipient_email, recipient_name, project_name, inviter_name):
    """
    Convenience function to send invitation email
    
    Args:
        recipient_email (str): Email address of the person being invited
        recipient_name (str): Name of the person being invited
        project_name (str): Name of the project they're being invited to
        inviter_name (str): Name of the person who sent the invitation
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    return email_service.send_invitation_email(
        recipient_email, 
        recipient_name, 
        project_name, 
        inviter_name
    )
