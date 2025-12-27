# 🎓 ResearchMate Server

<div align="center">

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.3-000000?style=for-the-badge&logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![LangChain](https://img.shields.io/badge/🦜_LangChain-0.1-green?style=for-the-badge)
![Ollama](https://img.shields.io/badge/Ollama-Run_Locally-orange?style=for-the-badge)

**An intelligent research management platform powered by AI.**
*Organize documents, extract insights, and collaborate seamlessly.*

</div>

---

## 📖 About The Project

**ResearchMate Server** is the robust backend powering the ResearchMate ecosystem. It provides a secure and scalable API for managing research projects, analyzing academic papers, and leveraging Generative AI to synthesize information.

Built with **Flask**, it integrates **Google's Gemini** models and a **RAG (Retrieval-Augmented Generation)** pipeline using **ChromaDB** to offer intelligent context-aware answers from your uploaded documents.

## ✨ Key Features

- **🔐 Secure Authentication**
  - **Google OAuth 2.0**: Seamless login with Google accounts.
  - **JWT Auth**: Secure session management for APIs.
  - **Role-Based Access**: Granular user permissions.

- **📚 Smart Document Management**
  - **Upload & Organize**: Support for PDF and other formats.
  - **Vector Embeddings**: Automatic vectorization of documents for semantic search.
  - **Project Workspaces**: Group related research into dedicated projects.

- **🤖 AI & RAG Engine**
  - **Local LLM Support**: Powered by **Ollama** running **Qwen 2.5b-coder**.
  - **Contextual QA**: Ask questions about your PDF library and get cited answers.
  - **Summarization**: Generate concise summaries of complex papers.
  - **Feature Extraction**: Identify key methodologies, results, and citations automatically.

- **🛠️ Advanced Tools**
   - **Ollama Qwen 2.5 Coder 3B Agent**: A specialized ReAct-based agent for drafting and editing research papers in LaTeX.
    - **Context-Aware**: Searches and reads project documents to inform writing.
    - **Incremental Editing**: Performs targeted edits while preserving existing content.
    - **Intelligent Reasoning**: Uses a thought-action-observation loop to plan complex tasks.


## ⚙️ Tech Stack

| Category | Technologies |
|----------|--------------|
| **Framework** | Flask (Python) |
| **Database** | PostgreSQL (Relational), ChromaDB (Vector) |
| **AI/ML** | LangChain, Ollama, Qwen 2.5b-coder |
| **Authentication** | Authlib (OAuth), PyJWT |
| **Asynchronous** | Celery & Redis (Optional/Planned) |

## 🚀 Getting Started

Follow these steps to set up the backend locally.

### Prerequisites

- **Python 3.9+**
- **PostgreSQL** installed and running.
- **Ollama** installed and running.
- **Google Cloud Console** account (for OAuth credentials).

### 1. Clone the Repository

```bash
git clone https://github.com/Shrinidhi857/ResearchMate-server.git
cd ResearchMate-server
```

### 2. Set Up Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Setup Ollama

Ensure Ollama is running and pull the required model:

```bash
ollama pull qwen2.5-coder:3b
```

### 4. Configure Environment

Create a `.env` file in the root directory. You can copy the example if available or use the template below:

```bash
# Security
SECRET_KEY=your_super_secret_key
JWT_SECRET_KEY=your_jwt_secret_key

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/research_db

# Google OAuth
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# AI Services
# GOOGLE_API_KEY=your_gemini_api_key (Optional/Fallback)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:3b

# Frontend Integration
FRONTEND_URL=http://localhost:5173
```

### 5. Initialize Database

Run the database migrations to create the necessary tables.

```bash
flask db upgrade
```

### 6. Run the Application

```bash
python run.py
```
*The server will start at `http://localhost:5000`*

## 📂 Project Structure

```bash
research-mate-server/
├── app/
│   ├── ai/            # AI logic & Prompt templates
│   ├── auth/          # Authentication routes (OAuth/JWT)
│   ├── codeagent/     # LLM coding assistant modules
│   ├── documents/     # File handling & parsing
│   ├── models/        # SQLAlchemy Database Models
│   ├── rag/           # RAG pipeline & Vector store logic
│   └── users/         # User management
├── db/                # Database utilities
├── migrations/        # Alembic migrations
├── run.py             # Entry point
└── requirements.txt   # Dependencies
```

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the project.
2. Create feature branch (`git checkout -b feature/NewFeature`).
3. Commit changes (`git commit -m 'Add NewFeature'`).
4. Push to branch (`git push origin feature/NewFeature`).
5. Open a Pull Request.

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
