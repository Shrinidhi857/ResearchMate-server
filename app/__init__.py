def create_app():
    """Return the FastAPI application instance."""
    from app.main import app
    return app

def get_app():
    from app.main import app
    return app

__all__ = ['create_app', 'get_app']
