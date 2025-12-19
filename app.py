# app.py
from flask import Flask, request, jsonify, session, redirect, url_for ,Response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth
from tqdm import tqdm
from gemma2.classifier import summarize_research_paper
from datetime import datetime, timedelta, timezone
import jwt
import os
import re
import uuid
from functools import wraps
import time, json
from flask import Response, jsonify, request
import json
from service.auto_site import auto_cite_paragraph


from gemma2.ieee_reference import generate_ieee_reference_for_doc

analysis_cache = {}


#imports 
from service.web_searcher import getUserInput
from service.web_scraper import researchPipeline
from rag.raptor import RaptorPipeline
from rag.raptor_middleman import asking_llm
from models import db, User, UserSession, Document, Project, Message, Response, PaperBucket
from service.email_service import send_invitation_email



def create_app():
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL',
        'postgresql://postgres:password@db:5432/flaskapp'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'jwt-secret-change-this')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)

    # Google OAuth config
    app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
    app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')

    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    CORS(app, supports_credentials=True)
    oauth = OAuth(app)
    
    

    # Google OAuth
    google =oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )

    # -----------------------
    # Utility functions
    # -----------------------
    def validate_email(email):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

    def validate_password(password):
        return len(password) >= 8

    def generate_token(user_id):
        payload = {
            'user_id': user_id,
            'exp': datetime.utcnow() + app.config['JWT_ACCESS_TOKEN_EXPIRES']
        }
        return jwt.encode(payload, app.config['JWT_SECRET_KEY'], algorithm='HS256')

    def verify_token(token):
        try:
            payload = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
            return payload['user_id']
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def token_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = None
            auth_header = request.headers.get('Authorization')

            if auth_header:
                try:
                    token = auth_header.split(' ')[1]  # Bearer <token>
                except IndexError:
                    return jsonify({'error': 'Invalid token format'}), 401

            if not token:
                return jsonify({'error': 'Token is missing'}), 401

            user_id = verify_token(token)
            if user_id is None:
                return jsonify({'error': 'Token is invalid or expired'}), 401

            current_user = User.query.get(user_id)
            if not current_user:
                return jsonify({'error': 'User not found'}), 401

            return f(current_user, *args, **kwargs)

        return decorated_function

    # Routes
    @app.route('/health', methods=['GET'])
    def health_check():
        return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})


#Authentication handling -------------------------------------------------------------------------------------------------------------------------------------------
    @app.route('/auth/register', methods=['POST'])
    def register():
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        
        if not email or not validate_email(email):
            return jsonify({'error': 'Valid email is required'}), 400
        
        if not password or not validate_password(password):
            return jsonify({'error': 'Password must be at least 8 characters long'}), 400
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({'error': 'User with this email already exists'}), 409
        
        try:
            # Create new user
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_verified=False
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            # Generate token
            token = generate_token(user.id)
            
            # Store session
            session_record = UserSession(
                user_id=user.id,
                token=token,
                expires_at=datetime.utcnow() + app.config['JWT_ACCESS_TOKEN_EXPIRES']
            )
            db.session.add(session_record)
            db.session.commit()
            
            return jsonify({
                'message': 'User registered successfully',
                'token': token,
                'user': user.to_dict()
            }), 201
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': 'Registration failed'}), 500

    @app.route('/auth/login', methods=['POST'])
    def login():
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        try:
            user = User.query.filter_by(email=email).first()
            
            if not user or not user.check_password(password):
                return jsonify({'error': 'Invalid credentials'}), 401
            
            # Generate token
            token = generate_token(user.id)
            
            # Store session
            session_record = UserSession(
                user_id=user.id,
                token=token,
                expires_at=datetime.utcnow() + app.config['JWT_ACCESS_TOKEN_EXPIRES']
            )
            db.session.add(session_record)
            db.session.commit()
            
            return jsonify({
                'message': 'Login successful',
                'token': token,
                'user': user.to_dict()
            }), 200
            
        except Exception as e:
            return jsonify({'error': 'Login failed'}), 500

    @app.route('/auth/google')
    def google_auth():
        redirect_uri = url_for('google_callback', _external=True)
        return google.authorize_redirect(redirect_uri)

    @app.route('/auth/google/callback')
    def google_callback():
        try:
            
            frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
            token = google.authorize_access_token()

            resp = google.get("https://www.googleapis.com/oauth2/v3/userinfo")
            user_info = resp.json()
                        
            if not user_info:
                return jsonify({'error': 'Failed to get user info from Google'}), 400
            
            email = user_info.get('email')
            google_id = user_info.get('sub')
            first_name = user_info.get('given_name', '')
            last_name = user_info.get('family_name', '')
            
            user = User.query.filter_by(email=email).first()
            
            if not user:
                user = User(
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    google_id=google_id,
                    is_verified=True
                )
                db.session.add(user)
            else:
                if not user.google_id:
                    user.google_id = google_id
                    user.is_verified = True
            
            db.session.commit()
            
            jwt_token = generate_token(user.id)
            
            session_record = UserSession(
                user_id=user.id,
                token=jwt_token,
                expires_at=datetime.utcnow() + app.config['JWT_ACCESS_TOKEN_EXPIRES']
            )
            db.session.add(session_record)
            db.session.commit()
            
            
            return redirect(f"{frontend_url}/auth/success?token={jwt_token}")
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Google authentication failed: {str(e)}'}), 500


            
       

    @app.route('/auth/logout', methods=['POST'])
    @token_required
    def logout(current_user):
        try:
            auth_header = request.headers.get('Authorization')
            if auth_header:
                token = auth_header.split(' ')[1]
                
                session_record = UserSession.query.filter_by(token=token).first()
                if session_record:
                    db.session.delete(session_record)
                    db.session.commit()
            
            return jsonify({'message': 'Logged out successfully'}), 200
            
        except Exception as e:
            return jsonify({'error': 'Logout failed'}), 500

    @app.route('/auth/profile', methods=['GET'])
    @token_required
    def get_profile(current_user):
        return jsonify({'user': current_user.to_dict()}), 200
    
    

    @app.route('/auth/profile', methods=['PUT'])
    @token_required
    def update_profile(current_user):
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        try:
            # Update allowed fields
            if 'first_name' in data:
                current_user.first_name = data['first_name'].strip()
            if 'last_name' in data:
                current_user.last_name = data['last_name'].strip()
            
            current_user.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'message': 'Profile updated successfully',
                'user': current_user.to_dict()
            }), 200
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': 'Profile update failed'}), 500

    @app.route('/auth/change-password', methods=['POST'])
    @token_required
    def change_password(current_user):
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        
        if not current_password or not new_password:
            return jsonify({'error': 'Current password and new password are required'}), 400
        
        if not validate_password(new_password):
            return jsonify({'error': 'New password must be at least 8 characters long'}), 400
        
        try:
            # Check current password
            if not current_user.check_password(current_password):
                return jsonify({'error': 'Current password is incorrect'}), 401
            
            # Update password
            current_user.set_password(new_password)
            current_user.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({'message': 'Password changed successfully'}), 200
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': 'Password change failed'}), 500
        
#handling user data---------------------------------------------------------------------------------------------------------------------------------       
    @app.route("/api/user", methods=["GET"])
    @token_required
    def get_user(current_user):
        try:
            return jsonify({
                "id": current_user.id,
                "email": current_user.email,
                "first_name": current_user.first_name if hasattr(current_user, "first_name") else None,
                "last_name": current_user.last_name if hasattr(current_user, "last_name") else None
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # Protected route example
    @app.route('/api/protected', methods=['GET'])
    @token_required
    def protected_route(current_user):
        return jsonify({
            'message': f'Hello {current_user.first_name or current_user.email}!',
            'user_id': current_user.id,
            'timestamp': datetime.utcnow().isoformat()
        }), 200

#scraper handling-------------------------------------------------------------------------------------------------------------------------------
    @app.route('/api/getlinks', methods=['POST'])
    @token_required
    def askai_route(current_user):
        data = request.get_json()
        
        if not data or "prompt" not in data:
            return jsonify({"error": "Prompt is required"}), 400
        
        try:
            result = getUserInput(data['prompt'])
            return jsonify({
                "message": f"Hello {current_user.first_name or current_user.email}!",
                "user_id": current_user.id,
                "timestamp": datetime.utcnow().isoformat(),
                "result": result
            }), 200   
        except Exception as e:
            return jsonify({"error": str(e)}), 500


    @app.route('/api/scraper', methods=['POST'])
    @token_required
    def scraper_route(current_user):
        data = request.get_json()
        
        if not data or "answers" not in data:
            return jsonify({"error": "Answers are required"}), 400

        try:
            # Convert the dict of answers into a topic string
            topic = " ".join([f"{k}: {v}" for k, v in data["answers"].items()])
            
            # Run research pipeline (downloads PDFs, extracts text, cleans up)
            extracted_texts ,links= researchPipeline(topic)

            return jsonify({
                "message": f"Hello {current_user.first_name }!",
                "user_id": current_user.id,
                "timestamp": datetime.utcnow().isoformat(),
                "topic": topic,
                "links":links,
                "documents": extracted_texts   # list of extracted text from PDFs
            }), 200
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500




#document handling---------------------------------------------------------------------------------------------------------------------------------------------------------------
    @app.route('/api/documents', methods=['POST'])
    @token_required
    def add_document(current_user):
        data = request.get_json()
        if not data or "content" not in data:
            return jsonify({"error": "Document content is required"}), 400

        try:
            doc = Document(user_id=current_user.id,title=data["title"],content=data["content"])
            db.session.add(doc)
            db.session.commit()
            return jsonify({
                "message": "Document saved successfully",
                "doc_id": doc.doc_id,
                "title": doc.title,
                "user_id": current_user.id
            }), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500


    # Get all documents of current user
    @app.route('/api/documents', methods=['GET'])
    @token_required
    def get_documents(current_user):
        docs = Document.query.filter_by(user_id=current_user.id).all()
        return jsonify([{
            "doc_id": d.doc_id,
            "title": d.title,
            "content": d.content,
            "created_at": d.created_at.isoformat()
        } for d in docs]), 200


    @app.route('/api/documents/<doc_id>', methods=['GET'])
    @token_required
    def get_document(current_user, doc_id):
        # Find the document for this user with the given doc_id
        doc = Document.query.filter_by(doc_id=doc_id, user_id=current_user.id).first()
        
        if not doc:
            return jsonify({"error": "Document not found"}), 404

        return jsonify({
            "doc_id": doc.doc_id,
            "title": doc.title,
            "content": doc.content,
            "created_at": doc.created_at.isoformat()
        }), 200
            
            
        
    # Update document
    @app.route('/api/documents/<doc_id>', methods=['PUT'])
    @token_required
    def update_document(current_user, doc_id):
        data = request.get_json()
        if not data or "content" not in data:
            return jsonify({"error": "Document content is required"}), 400

        doc = Document.query.filter_by(doc_id=doc_id, user_id=current_user.id).first()
        if not doc:
            return jsonify({"error": "Document not found"}), 404

        doc.content = data["content"]
        doc.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"message": "Document updated successfully"}), 200
    
    # Delete document
    @app.route('/api/documents/<doc_id>', methods=['DELETE'])
    @token_required
    def delete_document(current_user, doc_id):
        doc = Document.query.filter_by(doc_id=doc_id, user_id=current_user.id).first()
        if not doc:
            return jsonify({"error": "Document not found"}), 404

        db.session.delete(doc)
        db.session.commit()
        return jsonify({"message": "Document deleted successfully"}), 200

    
    @app.route('/api/documents/summary', methods=['GET'])
    @token_required
    def get_documents_summary(current_user):
        try:
            docs = Document.query.with_entities(Document.doc_id, Document.title).filter_by(user_id=current_user.id).all()

            result = [
                {"doc_id": doc.doc_id, "title": doc.title}
                for doc in docs
            ]

            return jsonify(result), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        
        
       
    


#RAG handling --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- 
    @app.route('/api/analyse', methods=['POST'])
    @token_required
    def raptor_analysis(current_user):
        global retriever
        retriever = None
        data = request.get_json()

        if not data or len(data) == 0:
            return jsonify({"message": "No document selected"}), 400

        try:
            retriever = RaptorPipeline(current_user, data)
        except Exception as e:
            return jsonify({"message": str(e)}), 500

        return jsonify({"message": "Document successfully Analysed"}), 200

    @app.route('/api/ask', methods=['POST'])
    @token_required
    def raptor_ask(current_user):
        data = request.get_json()
        
        if retriever is not None:
            try:
                answer = asking_llm(retriever, data.get("question"))
            except Exception as e:
                # Print error to console + return it to frontend
                import traceback
                traceback.print_exc()
                return jsonify({"message": f"Error asking Question: {str(e)}"}), 500
        else:
            return jsonify({"message": "No document Context"}), 500
        
        return jsonify({"message": "Success", "answer": answer}), 200

    def get_documents(current_user):
        from app import Document
        Doc = Document()
        docs = Doc.query.filter_by(user_id=current_user.id).all()
        return [{
            "doc_id": str(d.doc_id),   
            "content": d.content,
            "created_at": d.created_at.isoformat()
        } for d in docs]



# Ai features -----------------------------------------------------------------------------------------------------------------------------------
    @app.route('/api/summarize', methods=['POST'])
    @token_required
    def summarize_api():
        """
        API endpoint to summarize research paper text into structured JSON
        """
        data = request.get_json()

        if not data or 'text' not in data:
            return jsonify({"message": "Missing 'text' in request body"}), 400

        result = summarize_research_paper(data['text'])

        if result["success"]:
            return jsonify({"message": "Success", "summary": result["data"]}), 200
        elif "raw_output" in result:
            return jsonify({
                "message": "Model did not return perfect JSON",
                "raw_output": result["raw_output"]
            }), 200
        else:
            return jsonify({"message": f"Error: {result['error']}"}), 500

    @app.route('/api/ieee-ref', methods=['POST'])
    @token_required
    def generate_ieee_reference(current_user):
        """
        API endpoint to generate IEEE-style reference for a document
        """
        try:
            # Ensure user exists
            if not current_user:
                return jsonify({
                    "success": False,
                    "message": "Authentication required"
                }), 401

            # Parse request body
            data = request.get_json()

            # Expecting a list: [{ "doc_id": "..." }]
            if not isinstance(data, list) or len(data) == 0:
                return jsonify({
                    "success": False,
                    "message": "Request body must be a non-empty list"
                }), 400

            # Extract first element
            first_item = data[0]

            if 'doc_id' not in first_item:
                return jsonify({
                    "success": False,
                    "message": "Missing 'doc_id' in the first object"
                }), 400

            doc_id = first_item['doc_id']

            # Generate IEEE reference
            result = generate_ieee_reference_for_doc(current_user, doc_id)

            # result is assumed (json_response, status)
            return result

        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({
                "success": False,
                "message": "Server error while generating IEEE reference",
                "error": str(e)
            }), 500


    
    @app.route('/api/generate_reference/<string:doc_id>', methods=['POST'])
    @token_required
    def generate_reference(current_user, doc_id):
        return generate_ieee_reference_for_doc(current_user, doc_id)

    @app.route('/api/auto_cite', methods=['POST'])
    @token_required
    def auto_cite_endpoint(current_user):
        """
        Endpoint: /api/auto_cite
        Takes JSON with 'paragraph' and 'references' keys,
        returns paragraph with citations added.
        """
        try:
            data = request.get_json()
            paragraph = data.get("paragraph", "")
            references = data.get("references", {})

            if not paragraph or not references:
                return jsonify({"message": "Missing paragraph or references"}), 400

            result = auto_cite_paragraph(paragraph, references)

            return jsonify({
                "message": "Success",
                "cited_paragraph": result
            }), 200

        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"message": f"Error: {str(e)}"}), 500
    
    @app.route('/api/test', methods=['GET'])
    def test_stream():
        def generate():
            for i in range(5):
                msg = {"phase": i + 1, "status": "running", "message": f"Processing phase {i + 1}..."}
                yield f"data: {json.dumps(msg)}\n\n"
                time.sleep(1)
            yield f"data: {json.dumps({'phase': 6, 'status': 'complete', 'message': '✅ Test stream finished successfully!'})}\n\n"

        response = Response(generate(), mimetype='text/event-stream')
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Connection'] = 'keep-alive'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response


    @app.route('/api/start', methods=['POST'])
    def start_analysis():
        data = request.json
        print("Received from frontend:", data)
        return {"status": "ok", "message": "Processing started!"}


    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Endpoint not found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500

    return app

#Project handling----------------------------------------------------------------------------------------------------------
    @app.route("/api/projects/create", methods=["POST"])
    @token_required
    def create_project(current_user):
        data = request.get_json()

        project_name = data.get("project_name")

        if not project_name:
            return jsonify({"error": "project_name is required"}), 400

        project = Project(
            project_name=project_name,
            owner_id=current_user.id
        )

        # add creator as first user
        project.users.append(current_user)

        db.session.add(project)
        db.session.commit()

        return jsonify({
            "message": "Project created successfully",
            "project_id": project.project_id
        }), 201
        
        
    @app.route("/api/projects/<project_id>/invite", methods=["POST"])
    @token_required
    def invite_user(current_user, project_id):
        """Invite a user to collaborate on a project and send them an email notification"""
        data = request.get_json()
        user_email = data.get("email")

        if not user_email:
            return jsonify({"error": "Email is required"}), 400

        project = Project.query.filter_by(project_id=project_id).first()

        if not project:
            return jsonify({"error": "Project not found"}), 404

        if project.owner_id != current_user.id:
            return jsonify({"error": "Only project owner can invite users"}), 403

        invited_user = User.query.filter_by(email=user_email).first()

        if not invited_user:
            return jsonify({"error": "User does not exist"}), 404

        if invited_user in project.users:
            return jsonify({"error": "User already added"}), 400

        # Add user to project
        project.users.append(invited_user)
        db.session.commit()

        # Send invitation email
        try:
            inviter_name = f"{current_user.first_name} {current_user.last_name}".strip() or current_user.email
            recipient_name = f"{invited_user.first_name} {invited_user.last_name}".strip() or invited_user.email
            
            email_sent = send_invitation_email(
                recipient_email=invited_user.email,
                recipient_name=recipient_name,
                project_name=project.project_name,
                inviter_name=inviter_name
            )
            
            if email_sent:
                return jsonify({
                    "message": "User invited successfully and notification email sent"
                }), 200
            else:
                return jsonify({
                    "message": "User invited successfully but failed to send notification email"
                }), 200
                
        except Exception as e:
            # Even if email fails, the user was added successfully
            print(f"Email sending error: {str(e)}")
            return jsonify({
                "message": "User invited successfully but failed to send notification email",
                "error": str(e)
            }), 200


    @app.route("/api/projects/<project_id>/messages", methods=["POST"])
    @token_required
    def save_message(current_user, project_id):
        project = Project.query.filter_by(project_id=project_id).first()

        if not project:
            return jsonify({"error": "Project not found"}), 404

        if current_user not in project.users:
            return jsonify({"error": "Not allowed"}), 403

        data = request.get_json()

        msg = Message(
            message_number = len(project.messages) + 1,
            message_sender = current_user.email,
            message_content = data.get("content"),
            project_id = project.id
        )

        db.session.add(msg)
        db.session.commit()

        return jsonify({"message": "Message saved"})
    
    @app.route("/api/messages/<int:msg_id>", methods=["DELETE"])
    @token_required
    def delete_message(current_user, msg_id):

        msg = Message.query.get(msg_id)
        if not msg:
            return jsonify({"error": "Message not found"}), 404

        project = msg.project

        if project.owner_id != current_user.id and msg.message_sender != current_user.email:
            return jsonify({"error": "You cannot delete this message"}), 403

        db.session.delete(msg)
        db.session.commit()

        return jsonify({"message": "Message deleted"})
    
    @app.route("/api/projects/<project_id>/responses", methods=["POST"])
    @token_required
    def save_response(current_user, project_id):
        project = Project.query.filter_by(project_id=project_id).first()

        if not project:
            return jsonify({"error": "Project not found"}), 404

        if current_user not in project.users:
            return jsonify({"error": "Not allowed"}), 403

        data = request.get_json()

        res = Response(
            summary = data.get("summary"),
            response_by = current_user.email,
            project_id = project.id
        )

        db.session.add(res)
        db.session.commit()

        return jsonify({"message": "Response saved"})


    @app.route("/api/projects", methods=["GET"])
    @token_required
    def get_user_projects(current_user):
        """Get all projects where the user is a member"""
        projects = current_user.projects
        return jsonify([p.to_dict() for p in projects]), 200


    @app.route("/api/projects/<project_id>", methods=["GET"])
    @token_required
    def get_project(current_user, project_id):
        """Get project details with messages and responses"""
        project = Project.query.filter_by(project_id=project_id).first()
        
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        if current_user not in project.users:
            return jsonify({"error": "Not allowed"}), 403
        
        project_dict = project.to_dict()
        project_dict['messages'] = [m.to_dict() for m in project.messages]
        project_dict['responses'] = [r.to_dict() for r in project.responses]
        
        return jsonify(project_dict), 200


    @app.route("/api/projects/<project_id>/messages", methods=["GET"])
    @token_required
    def get_project_messages(current_user, project_id):
        """Get all messages for a project"""
        project = Project.query.filter_by(project_id=project_id).first()
        
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        if current_user not in project.users:
            return jsonify({"error": "Not allowed"}), 403
        
        return jsonify([m.to_dict() for m in project.messages]), 200


    @app.route("/api/projects/<project_id>/responses", methods=["GET"])
    @token_required
    def get_project_responses(current_user, project_id):
        """Get all responses for a project"""
        project = Project.query.filter_by(project_id=project_id).first()
        
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        if current_user not in project.users:
            return jsonify({"error": "Not allowed"}), 403
        
        return jsonify([r.to_dict() for r in project.responses]), 200


    @app.route("/api/projects/<project_id>/top-users", methods=["GET"])
    @token_required
    def get_project_top_users(current_user, project_id):
        """Get top 3 users in a project (prioritizing owner and current user)"""
        project = Project.query.filter_by(project_id=project_id).first()
        
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        if current_user not in project.users:
            return jsonify({"error": "Not allowed"}), 403
        
        # Collect users: prioritize owner, then current user, then others
        top_users = []
        user_ids_added = set()
        
        # Add owner first
        if project.owner:
            top_users.append({
                'id': project.owner.id,
                'email': project.owner.email,
                'first_name': project.owner.first_name,
                'last_name': project.owner.last_name
            })
            user_ids_added.add(project.owner.id)
        
        # Add current user if not already added
        if current_user.id not in user_ids_added and len(top_users) < 3:
            top_users.append({
                'id': current_user.id,
                'email': current_user.email,
                'first_name': current_user.first_name,
                'last_name': current_user.last_name
            })
            user_ids_added.add(current_user.id)
        
        # Add other users until we have 3
        for user in project.users:
            if user.id not in user_ids_added and len(top_users) < 3:
                top_users.append({
                    'id': user.id,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name
                })
                user_ids_added.add(user.id)
        
        return jsonify({"users": top_users}), 200


    @app.route("/api/projects/<project_id>", methods=["DELETE"])
    @token_required
    def delete_project(current_user, project_id):
        """Delete a project (owner only)"""
        project = Project.query.filter_by(project_id=project_id).first()
        
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        if project.owner_id != current_user.id:
            return jsonify({"error": "Only the owner can delete this project"}), 403
        
        db.session.delete(project)
        db.session.commit()
        
        return jsonify({"message": "Project deleted successfully"}), 200


    @app.route("/api/responses/<response_id>", methods=["DELETE"])
    @token_required
    def delete_response(current_user, response_id):
        """Delete a response"""
        response = Response.query.filter_by(response_id=response_id).first()
        
        if not response:
            return jsonify({"error": "Response not found"}), 404
        
        project = response.project
        
        # Only owner or response creator can delete
        if project.owner_id != current_user.id and response.response_by != current_user.email:
            return jsonify({"error": "You cannot delete this response"}), 403
        
        db.session.delete(response)
        db.session.commit()
        
        return jsonify({"message": "Response deleted successfully"}), 200


    # Paper Bucket Management Endpoints
    @app.route("/api/projects/<project_id>/paper-bucket", methods=["GET"])
    @token_required
    def get_paper_bucket(current_user, project_id):
        """Get paper bucket for a project"""
        project = Project.query.filter_by(project_id=project_id).first()
        
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        if current_user not in project.users:
            return jsonify({"error": "Not allowed"}), 403
        
        paper_bucket = PaperBucket.query.filter_by(project_id=project.id).first()
        
        if not paper_bucket:
            return jsonify({"paper_ids": []}), 200
        
        return jsonify({"paper_ids": paper_bucket.paper_ids if paper_bucket.paper_ids else []}), 200


    @app.route("/api/projects/<project_id>/paper-bucket", methods=["PUT"])
    @token_required
    def update_paper_bucket(current_user, project_id):
        """Update/replace entire paper bucket for a project"""
        project = Project.query.filter_by(project_id=project_id).first()
        
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        if current_user not in project.users:
            return jsonify({"error": "Not allowed"}), 403
        
        data = request.get_json()
        paper_ids = data.get("paper_ids", [])
        
        if not isinstance(paper_ids, list):
            return jsonify({"error": "paper_ids must be an array"}), 400
        
        paper_bucket = PaperBucket.query.filter_by(project_id=project.id).first()
        
        if not paper_bucket:
            paper_bucket = PaperBucket(
                project_id=project.id,
                paper_ids=paper_ids
            )
            db.session.add(paper_bucket)
        else:
            paper_bucket.paper_ids = paper_ids
            paper_bucket.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({"message": "Paper bucket updated successfully", "paper_ids": paper_ids}), 200


    @app.route("/api/projects/<project_id>/paper-bucket/add", methods=["POST"])
    @token_required
    def add_paper_to_bucket(current_user, project_id):
        """Add a single paper to the bucket"""
        project = Project.query.filter_by(project_id=project_id).first()
        
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        if current_user not in project.users:
            return jsonify({"error": "Not allowed"}), 403
        
        data = request.get_json()
        paper_id = data.get("paper_id")
        
        if not paper_id:
            return jsonify({"error": "paper_id is required"}), 400
        
        paper_bucket = PaperBucket.query.filter_by(project_id=project.id).first()
        
        if not paper_bucket:
            paper_bucket = PaperBucket(
                project_id=project.id,
                paper_ids=[paper_id]
            )
            db.session.add(paper_bucket)
        else:
            if paper_bucket.paper_ids is None:
                paper_bucket.paper_ids = []
            
            if paper_id not in paper_bucket.paper_ids:
                paper_bucket.paper_ids = paper_bucket.paper_ids + [paper_id]
                paper_bucket.updated_at = datetime.utcnow()
            else:
                return jsonify({"message": "Paper already in bucket", "paper_ids": paper_bucket.paper_ids}), 200
        
        db.session.commit()
        
        return jsonify({"message": "Paper added to bucket", "paper_ids": paper_bucket.paper_ids}), 200


    @app.route("/api/projects/<project_id>/paper-bucket/<paper_id>", methods=["DELETE"])
    @token_required
    def remove_paper_from_bucket(current_user, project_id, paper_id):
        """Remove a single paper from the bucket"""
        project = Project.query.filter_by(project_id=project_id).first()
        
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        if current_user not in project.users:
            return jsonify({"error": "Not allowed"}), 403
        
        paper_bucket = PaperBucket.query.filter_by(project_id=project.id).first()
        
        if not paper_bucket or not paper_bucket.paper_ids:
            return jsonify({"error": "Paper bucket is empty"}), 404
        
        if paper_id in paper_bucket.paper_ids:
            paper_bucket.paper_ids = [pid for pid in paper_bucket.paper_ids if pid != paper_id]
            paper_bucket.updated_at = datetime.utcnow()
            db.session.commit()
            return jsonify({"message": "Paper removed from bucket", "paper_ids": paper_bucket.paper_ids}), 200
        else:
            return jsonify({"error": "Paper not found in bucket"}), 404

    return app


if __name__ == '__main__':
    app=create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
