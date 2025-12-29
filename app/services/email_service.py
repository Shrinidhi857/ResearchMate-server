import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv(override=True)

class EmailService:
    """Service for sending emails via SMTP"""
    
    def __init__(self):
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_email = os.getenv('SMTP_EMAIL')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '').strip()
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
            print(f"   Error type: {type(e).__name__}")
            print(f"   Full error details: {repr(e)}")
            import traceback
            traceback.print_exc()
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
    
    def send_signup_invitation_email(self, recipient_email, project_name, inviter_name):
        """
        Send an invitation email to someone who doesn't have an account yet
        
        Args:
            recipient_email (str): Email address of the person being invited
            project_name (str): Name of the project they're being invited to
            inviter_name (str): Name of the person who sent the invitation
        
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Debug: Print SMTP configuration
            print(f"\n📧 Attempting to send signup invitation email...")
            print(f"   SMTP Server: {self.smtp_server}:{self.smtp_port}")
            print(f"   From Email: {self.smtp_email}")
            print(f"   Password Set: {'Yes' if self.smtp_password else 'No'}")
            print(f"   Password Length: {len(self.smtp_password) if self.smtp_password else 0}")
            print(f"   To Email: {recipient_email}")
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.smtp_email
            msg['To'] = recipient_email
            msg['Subject'] = f'{inviter_name} invited you to join "{project_name}"'
            
            # Create HTML email body
            html_body = self._create_signup_invitation_html(
                recipient_email,
                project_name, 
                inviter_name
            )
            
            # Attach HTML body
            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)
            
            # Send email
            print(f"   Connecting to SMTP server...")
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                print(f"   Starting TLS...")
                server.starttls()
                print(f"   Logging in...")
                server.login(self.smtp_email, self.smtp_password)
                print(f"   Sending message...")
                server.send_message(msg)
            
            print(f"✅ Signup invitation email sent to {recipient_email}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to send signup email to {recipient_email}: {str(e)}")
            print(f"   Error type: {type(e).__name__}")
            print(f"   Full error details: {repr(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _create_signup_invitation_html(self, recipient_email, project_name, inviter_name):
        """Create HTML template for signup invitation email"""
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
                            <h1 style="margin: 0; color: #ffffff; font-size: 28px; font-weight: 600;">Research Management</h1>
                            <p style="margin: 10px 0 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">Collaborate • Discover • Research</p>
                        </td>
                    </tr>
                    
                    <!-- Body -->
                    <tr>
                        <td style="padding: 40px;">
                            <h2 style="margin: 0 0 20px 0; color: #333333; font-size: 24px; font-weight: 600;">
                                You've been invited to collaborate! 🎉
                            </h2>
                            
                            <p style="margin: 0 0 15px 0; color: #666666; font-size: 16px; line-height: 1.6;">
                                Hi there,
                            </p>
                            
                            <p style="margin: 0 0 15px 0; color: #666666; font-size: 16px; line-height: 1.6;">
                                <strong style="color: #333333;">{inviter_name}</strong> wants to collaborate with you on their research project:
                            </p>
                            
                            <div style="background-color: #f8f9fa; border-left: 4px solid #667eea; padding: 20px; margin: 25px 0; border-radius: 4px;">
                                <p style="margin: 0; color: #333333; font-size: 18px; font-weight: 600;">
                                    📚 {project_name}
                                </p>
                            </div>
                            
                            <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 20px; margin: 25px 0; border-radius: 4px;">
                                <p style="margin: 0 0 10px 0; color: #856404; font-size: 14px; font-weight: 600;">
                                    ⚠️ Account Required
                                </p>
                                <p style="margin: 0; color: #856404; font-size: 14px; line-height: 1.5;">
                                    We noticed you don't have an account yet. Please sign up first to accept this invitation and start collaborating!
                                </p>
                            </div>
                            
                            <p style="margin: 0 0 25px 0; color: #666666; font-size: 16px; line-height: 1.6;">
                                Create your free account now and join the collaborative research platform.
                            </p>
                            
                            <!-- CTA Buttons -->
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td align="center" style="padding: 20px 0;">
                                        <a href="{self.app_url}/signup?email={recipient_email}" style="display: inline-block; padding: 15px 40px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #ffffff; text-decoration: none; border-radius: 6px; font-size: 16px; font-weight: 600; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);">
                                            Sign Up Now
                                        </a>
                                    </td>
                                </tr>
                                <tr>
                                    <td align="center" style="padding: 10px 0;">
                                        <p style="margin: 0; color: #999999; font-size: 14px;">
                                            Already have an account? <a href="{self.app_url}/login" style="color: #667eea; text-decoration: none; font-weight: 600;">Log in</a>
                                        </p>
                                    </td>
                                </tr>
                            </table>
                            
                            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e9ecef;">
                                <p style="margin: 0 0 10px 0; color: #666666; font-size: 14px; font-weight: 600;">
                                    Why join our platform?
                                </p>
                                <ul style="margin: 0; padding-left: 20px; color: #666666; font-size: 14px; line-height: 1.8;">
                                    <li>Collaborate with researchers worldwide</li>
                                    <li>Manage and organize research papers</li>
                                    <li>AI-powered research assistance</li>
                                    <li>LaTeX editor for academic writing</li>
                                </ul>
                            </div>
                            
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
                                © 2025 Research Management. All rights reserved.
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
# Re-instantiate to ensure we get the latest env vars
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


def send_signup_invitation_email(recipient_email, project_name, inviter_name):
    """
    Convenience function to send signup invitation email to non-registered users
    
    Args:
        recipient_email (str): Email address of the person being invited
        project_name (str): Name of the project they're being invited to
        inviter_name (str): Name of the person who sent the invitation
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    return email_service.send_signup_invitation_email(
        recipient_email,
        project_name,
        inviter_name
    )

