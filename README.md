# Flask Backend with PostgreSQL and OAuth

A complete Flask backend application with PostgreSQL database, Google OAuth, and email/password authentication.

## Features

- **Authentication Methods:**

  - Email/password registration and login
  - Google OAuth 2.0 integration
  - JWT token-based authentication
  - Session management

- **Database:**

  - PostgreSQL with SQLAlchemy ORM
  - User management with profiles
  - Session tracking
  - Database migrations

- **Security:**
  - Password hashing with Werkzeug
  - JWT tokens for API authentication
  - CORS support
  - Input validation

## Prerequisites

- Docker and Docker Compose
- Google Cloud Console account (for OAuth)

## Setup Instructions

### 1. Clone and Setup

```bash
# Create project directory
mkdir flask-oauth-backend
cd flask-oauth-backend

# Copy all the provided files to this directory
# (app.py, requirements.txt, Dockerfile, docker-compose.yml, etc.)
```

### 2. Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable Google+ API and Google OAuth2 API
4. Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client ID"
5. Set application type to "Web application"
6. Add authorized redirect URIs:
   - `http://localhost:5000/auth/google/callback`
   - Add your production domain when deploying
7. Copy the Client ID and Client Secret

### 3. Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env file with your values
nano .env
```

Update the `.env` file with:

- Your Google OAuth credentials
- Strong secret keys (generate random strings)
- Database credentials if different

### 4. Run with Docker

```bash
# Build and start services
docker-compose up --build

# Or run in background
docker-compose up -d --build
```

The application will be available at `http://localhost:5000`

### 5. Database Migrations (if needed)

```bash
# Access the running container
docker-compose exec app bash

# Initialize migrations (first time only)
flask db init

# Create migration
flask db migrate -m "Initial migration"

# Apply migration
flask db upgrade
```

## API Endpoints

### Authentication

- `POST /auth/register` - Register with email/password
- `POST /auth/login` - Login with email/password
- `GET /auth/google` - Initiate Google OAuth flow
- `GET /auth/google/callback` - Google OAuth callback
- `POST /auth/logout` - Logout (requires auth token)

### User Management

- `GET /auth/profile` - Get user profile (requires auth token)
- `PUT /auth/profile` - Update user profile (requires auth token)
- `POST /auth/change-password` - Change password (requires auth token)

### Protected Routes

- `GET /api/protected` - Example protected endpoint
- `GET /health` - Health check endpoint

## API Usage Examples

### Register User

```bash
curl -X POST http://localhost:5000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepassword123",
    "first_name": "John",
    "last_name": "Doe"
  }'
```

### Login

```bash
curl -X POST http://localhost:5000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepassword123"
  }'
```

### Access Protected Route

```bash
curl -X GET http://localhost:5000/auth/profile \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Google OAuth Flow

1. Visit `http://localhost:5000/auth/google` in browser
2. Complete Google authentication
3. Get redirected to frontend with token

## Project Structure

```
flask-oauth-backend/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── Dockerfile            # Container configuration
├── docker-compose.yml    # Multi-service setup
├── init.sql              # Database initialization
├── .env.example          # Environment template
├── .dockerignore         # Docker ignore file
└── README.md             # This file
```

## Development

### Local Development (without Docker)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up PostgreSQL locally and update DATABASE_URL in .env

# Run migrations
flask db upgrade

# Start development server
python app.py
```

### Database Management

```bash
# Create new migration
docker-compose exec app flask db migrate -m "Description"

# Apply migrations
docker-compose exec app flask db upgrade

# Access PostgreSQL directly
docker-compose exec db psql -U postgres -d flaskapp
```

## Production Deployment

1. **Environment Variables:**

   - Use strong, random secret keys
   - Use production PostgreSQL instance
   - Set proper FRONTEND_URL
   - Configure Google OAuth with production domains

2. **Security:**

   - Use HTTPS in production
   - Set proper CORS origins
   - Use environment-specific secret keys
   - Consider rate limiting

3. **Database:**
   - Use managed PostgreSQL service
   - Set up proper backups
   - Configure connection pooling

## Troubleshooting

### Common Issues

1. **Google OAuth not working:**

   - Check redirect URI matches exactly
   - Verify Client ID and Secret
   - Ensure APIs are enabled in Google Console

2. **Database connection failed:**

   - Wait for database to be ready (health check)
   - Verify DATABASE_URL format
   - Check PostgreSQL container logs

3.
