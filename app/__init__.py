from flask import Flask
from flask_cors import CORS
from datetime import timedelta
import os

from app.extensions import db, migrate, oauth
from app.config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app, supports_credentials=True)
    oauth.init_app(app)
    
    # Register blueprints
    from app.auth.routes import auth_bp
    from app.users.routes import users_bp
    from app.documents.routes import documents_bp
    from app.projects.routes import projects_bp
    from app.rag.routes import rag_bp
    from app.ai.routes import ai_bp
    from app.scraper.routes import scraper_bp
    
    from app.analyse.routes import analyse_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(users_bp, url_prefix='/api')
    app.register_blueprint(documents_bp, url_prefix='/api')
    app.register_blueprint(projects_bp, url_prefix='/api')
    app.register_blueprint(rag_bp, url_prefix='/api')
    app.register_blueprint(ai_bp, url_prefix='/api')
    app.register_blueprint(scraper_bp, url_prefix='/api')
    app.register_blueprint(analyse_bp, url_prefix='/api')
    
    # Health check route
    @app.route('/health', methods=['GET'])
    def health_check():
        from datetime import datetime
        from flask import jsonify
        return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        from flask import jsonify
        return jsonify({'error': 'Endpoint not found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        from flask import jsonify
        return jsonify({'error': 'Internal server error'}), 500
    
    return app