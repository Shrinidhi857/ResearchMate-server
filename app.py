# app.py
from flask import Flask, request, jsonify, session, redirect, url_for ,Response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth

from datetime import datetime, timedelta, timezone
import jwt
import os
import re
import uuid
from functools import wraps
import time, json
from flask import Response, jsonify, request
import json

from service.analysis_tool import (
    semantic_search,
    extract_entities,
    train_sentence_classifier,
    predict_sentence_labels,
    extract_relations_from_sentences,
    detect_contradictions,
    build_citation_graph,
    analyze_graph,
)

#imports 
from service.web_searcher import getUserInput
from service.web_scraper import researchPipeline
from service.raptor import RaptorPipeline
from service.raptor_middleman import asking_llm
from models import db, User, UserSession, Document



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

    # Protected route example
    @app.route('/api/protected', methods=['GET'])
    @token_required
    def protected_route(current_user):
        return jsonify({
            'message': f'Hello {current_user.first_name or current_user.email}!',
            'user_id': current_user.id,
            'timestamp': datetime.utcnow().isoformat()
        }), 200


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
            "doc_id": str(d.doc_id),   # ✅ convert UUID to string
            "content": d.content,
            "created_at": d.created_at.isoformat()
        } for d in docs]

  

    @app.route('/api/nlp', methods=['POST'])
    @token_required
    def analyse_pipeline(current_user):
        data = request.get_json()
        if not data or len(data) == 0:
            return jsonify({"message": "No document selected"}), 400

        docs = get_documents(current_user)
        selected_ids = {d["doc_id"] for d in data}
        print("documents:", selected_ids)
        docs = [d for d in docs if d["doc_id"] in selected_ids]

        if not docs:
            raise ValueError("No matching documents found")

        sentences = [d["content"] for d in docs]

        def generate():
            try:
                # === PHASE 1: Semantic Search ===
                yield f"data: {json.dumps({'phase': 1, 'status': 'start', 'message': 'Running semantic search...'})}\n\n"
                time.sleep(1)

                limitation_queries = ["a limitation of this study is", "we were unable to", "a weakness of our approach"]
                future_queries = ["future research should focus on", "the next step is to", "further investigation is needed"]
                queries = limitation_queries + future_queries

                semres = semantic_search(sentences, queries, top_k=10, threshold=0.6)
                yield f"data: {json.dumps({'phase': 1, 'status': 'done', 'message': '=== Semantic search candidates ==='})}\n\n"

                for q, items in semres.items():
                    yield f"data: {json.dumps({'phase': 1, 'query': q, 'message': 'Query results:'})}\n\n"
                    for s, score in items:
                        yield f"data: {json.dumps({'phase': 1, 'query': q, 'score': score, 'sentence': s})}\n\n"

                # === PHASE 2: Entity Extraction ===
                candidate_sents = list({s for items in semres.values() for s, _ in items})
                ents = extract_entities(candidate_sents)
                yield f"data: {json.dumps({'phase': 2, 'status': 'done', 'message': '=== Entities extracted ===', 'entities': ents})}\n\n"

                # === PHASE 3: Classifier Training ===
                clf_obj = train_sentence_classifier(sentences)
                yield f"data: {json.dumps({'phase': 3, 'status': 'done', 'message': '=== Classifier report ===', 'report': clf_obj['report'], 'accuracy': clf_obj['accuracy']})}\n\n"

                # === PHASE 4: Prediction ===
                preds = predict_sentence_labels(sentences, clf_obj)
                for s, p in zip(sentences, preds):
                    yield f"data: {json.dumps({'phase': 4, 'sentence': s, 'predicted_label': p})}\n\n"

                # === PHASE 5: Relation Extraction ===
                relations = extract_relations_from_sentences(sentences)
                for r in relations:
                    yield f"data: {json.dumps({'phase': 5, 'relation': r})}\n\n"

                # === PHASE 6: Contradiction Detection ===
                contradictions = detect_contradictions(relations, min_support=1)
                for c in contradictions:
                    yield f"data: {json.dumps({'phase': 6, 'pair': c['pair'], 'relations': c['relations']})}\n\n"

                # === DONE ===
                yield f"data: {json.dumps({'phase': 7, 'status': 'complete', 'message': '✅ Pipeline finished successfully!'})}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'phase': 'error', 'error': str(e)})}\n\n"

        # Build response
        response = Response(generate(), mimetype='text/event-stream')
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Connection'] = 'keep-alive'
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['X-Accel-Buffering'] = 'no'  # prevent buffering in nginx, etc.
        return response

    
    
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

if __name__ == '__main__':
    app=create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
