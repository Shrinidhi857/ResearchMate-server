import smtplib
import os
from dotenv import load_dotenv
from email.mime.text import MIMEText

# Load environment variables
load_dotenv()

smtp_server = os.getenv('SMTP_SERVER')
smtp_port = int(os.getenv('SMTP_PORT', 587))
smtp_email = os.getenv('SMTP_EMAIL')
smtp_password = os.getenv('SMTP_PASSWORD')

print(f"Testing SMTP Sending:")
print(f"Server: {smtp_server}:{smtp_port}")
print(f"Email: {smtp_email}")

try:
    print("\n1. Connecting...")
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    
    print("2. Logging in...")
    pwd = smtp_password.strip() if smtp_password else ""
    server.login(smtp_email, pwd)
    
    print("3. Sending test email to self...")
    msg = MIMEText("This is a test email from the Research Platform debugger.")
    msg['Subject'] = "SMTP Test Email"
    msg['From'] = smtp_email
    msg['To'] = smtp_email
    
    server.send_message(msg)
    
    print("\n✅ SUCCESS! Email sent successfully.")
    server.quit()
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    # print full traceback
    import traceback
    traceback.print_exc()
