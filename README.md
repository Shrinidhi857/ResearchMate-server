<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/Shrinidhi857/ResearchMate-server">
    <img src="logo.png" alt="Logo" width="80" height="80">
  </a>

  <h3 align="center">ResearchMate Server</h3>

  <p align="center">
    An intelligent research management platform powered by AI.
    <br />
    Organize documents, extract insights, and collaborate seamlessly.
    <br />
    <br />
    <a href="https://github.com/Shrinidhi857/ResearchMate-server">View Demo</a>
    ·
    <a href="https://github.com/Shrinidhi857/ResearchMate-server/issues">Report Bug</a>
    ·
    <a href="https://github.com/Shrinidhi857/ResearchMate-server/issues">Request Feature</a>
    ·
    <a href="https://github.com/Shrinidhi857/ResearchMate">Frontend</a>
  </p>

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.3-000000?style=for-the-badge&logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![LangChain](https://img.shields.io/badge/🦜_LangChain-0.1-green?style=for-the-badge)
![Ollama](https://img.shields.io/badge/Ollama-Run_Locally-orange?style=for-the-badge)
![Qwen](https://img.shields.io/badge/Qwen-2.5_Coder_3B-blue?style=for-the-badge)
![ChromaDB](https://img.shields.io/badge/ChromaDB-Run_Locally-orange?style=for-the-badge)

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

## 📊Diagram

<img src="diagram.png" alt="Diagram" height="100%">

## ⚙️ Tech Stack

| Category           | Technologies                               |
| ------------------ | ------------------------------------------ |
| **Framework**      | Flask (Python)                             |
| **Database**       | PostgreSQL (Relational), ChromaDB (Vector) |
| **AI/ML**          | LangChain, Ollama, Qwen 2.5b-coder         |
| **Authentication** | Authlib (OAuth), PyJWT                     |
| **Asynchronous**   | Celery & Redis (Optional/Planned)          |

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
ollama serve
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

_The server will start at `http://localhost:5000`_

## 🤖 LaTeX Agent: ReAct-Based Paper Writing Assistant

The **LaTeX Agent** is an advanced tool powered by **Ollama's Qwen 2.5 Coder 3B** model that uses a **Reasoning + Acting (ReAct)** architecture to help you draft and iteratively edit research papers in LaTeX format. It combines agentic reasoning with access to your project documents to produce contextually relevant academic writing.

### Conceptual Overview

The LaTeX Agent operates on a **thought-action-observation loop**:

1. **Thought**: The agent reasons about the user's request and decides which tool to use
2. **Action**: The agent calls one of its available tools to gather information
3. **Observation**: The agent processes the tool's response and updates its understanding
4. **Repeat/Complete**: Based on observations, the agent either loops to gather more data or returns the final LaTeX code

This iterative process allows the agent to:

- Search through your uploaded research documents
- Read specific documents for detailed content
- Analyze the current LaTeX paper structure
- Make informed, context-aware edits to your paper
- Preserve existing content while adding or modifying sections

### Available Tools

The LaTeX Agent can invoke four primary tools:

| Tool                      | Purpose                                                                                                                           | Usage                                                           |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `search_docs(query: str)` | Search document titles and keywords by query term. Returns a list of matching document IDs for retrieval.                         | Discover relevant documents before reading their content.       |
| `read_doc(doc_id: str)`   | Retrieve the full content of a specific document by its unique ID. Returns up to 5000 characters of document content.             | Access detailed information from a targeted document.           |
| `read_current_paper()`    | Retrieve the current LaTeX source code of the project's paper. Helps the agent understand existing structure before making edits. | Understand the current paper state before making modifications. |
| `none()`                  | Signal task completion. The agent must call this tool with the final LaTeX code to return its response.                           | Complete the reasoning loop and deliver the final result.       |

### How It Works: The Editing Workflow

When you request a modification to your paper, the agent:

1. **Analyzes the Request**: Parses your instruction to understand the scope (e.g., "add methodology section", "update introduction")
2. **Reads Current State**: Calls `read_current_paper()` to understand existing LaTeX structure
3. **Gathers Context**: Uses `search_docs()` and `read_doc()` to retrieve relevant information from your uploaded research documents
4. **Reasons & Plans**: Develops a modification strategy that aligns with the user's request
5. **Preserves Existing Content**: Critically, the agent makes **targeted, incremental edits** rather than complete rewrites
6. **Returns Result**: Calls `none()` tool and delivers the updated LaTeX code with only the requested changes applied

### Key Characteristics

- **Incremental Editing**: Modifies only the specific sections requested; preserves all existing content
- **Context-Aware**: Leverages project documents to inform writing decisions
- **Step-Limited Reasoning**: Operates with a maximum of 20 reasoning steps (configurable) to ensure efficiency
- **Loop Detection**: Automatically detects infinite loops and forces completion when necessary
- **WebSocket-Based**: Uses real-time WebSocket communication for live agent thinking feedback

### Running the LaTeX Agent Server

The LaTeX Agent runs as a **standalone FastAPI service** with WebSocket support for real-time communication. It integrates with your Flask application database for document and project retrieval.

#### Start the Agent Server

Open a new terminal (keeping the main Flask server running) and run:

```bash
python -m app.codeagent.routes
```

#### Expected Server Output

```bash
PS C:\code-2025\Research-Management> python -m app.codeagent.routes

╔══════════════════════════════════════════════════════════════╗
║            LaTeX Agent Backend Server (Project Integrated)   ║
╠══════════════════════════════════════════════════════════════╣
║  LLM Provider: ollama                                        ║
║  Server:       0.0.0.0:8001                                  ║
║  WebSocket:    ws://0.0.0.0:8001/ws/{client_id}/{project_id}║
╚══════════════════════════════════════════════════════════════╝

INFO:     Started server process [47432]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```

The agent server listens on **port 8001** by default and is ready to accept WebSocket connections.

### Configuration Options

Control the LaTeX Agent behavior via environment variables in your `.env` file:

```bash
# LaTeX Agent Configuration
AGENT_MAX_STEPS=20                          # Maximum reasoning steps (default: 20)
MAX_COMPILATION_ATTEMPTS=20                  # Max LaTeX compilation retries (default: 20)
AGENT_TIMEOUT=180                            # Agent execution timeout in seconds (default: 180)
MAX_CONTEXT_LENGTH=5000                      # Max context window per tool call (default: 5000)
MAX_OBSERVATION_LENGTH=2000                  # Max observation length per tool response (default: 2000)

# Server Configuration
LLM_PROVIDER=ollama                          # LLM provider (options: ollama, openai, anthropic)
OLLAMA_BASE_URL=http://localhost:11434      # Ollama API endpoint
OLLAMA_MODEL=qwen2.5-coder:3b               # Model to use for reasoning
```

### WebSocket Connection Protocol

The agent communicates via WebSocket at: `ws://0.0.0.0:8001/ws/{client_id}/{project_id}`

**Message Types:**

- **USER_MESSAGE**: Send a request to the agent

  ```json
  {
    "type": "USER_MESSAGE",
    "content": "Add a methodology section to the paper",
    "document_ids": ["doc_id_1", "doc_id_2"] // Optional: pre-select specific documents
  }
  ```

- **AGENT_THINKING**: Agent's reasoning step (received from server)

  ```json
  {
    "type": "AGENT_THINKING",
    "content": "Reading current paper structure..."
  }
  ```

- **CODE_GENERATED**: Final LaTeX code from agent (received from server)

  ```json
  {
    "type": "CODE_GENERATED",
    "content": "\\documentclass{article}...",
    "thought": "Added methodology section with content from retrieved papers",
    "attempt": 1,
    "max_attempts": 20
  }
  ```

- **ERROR**: Error message from agent (received from server)
  ```json
  {
    "type": "ERROR",
    "content": "Project not found"
  }
  ```

### Example: Drafting a Paper Section

**User Request:**

> "Add a comprehensive related work section with citations from the uploaded papers"

**Agent Reasoning Process:**

1. Reads current paper to understand existing structure
2. Searches documents for relevant content: `search_docs("related work", "literature review")`
3. Reads 2-3 top documents to extract background information
4. Crafts a LaTeX section with cited references
5. Preserves all existing sections (introduction, abstract, etc.)
6. Returns updated paper with new "Related Work" section

### Performance Considerations

- **First Request**: ~30-45 seconds (model warm-up + first reasoning loop)
- **Subsequent Requests**: ~15-30 seconds (Ollama model cached in memory)
- **Large Papers**: May require additional reasoning steps if heavy modification requested
- **Large Document Sets**: Agent intelligently limits document reads to top 5 matches per search

### Troubleshooting

| Issue                             | Solution                                                                |
| --------------------------------- | ----------------------------------------------------------------------- |
| "Connection refused on port 8001" | Ensure agent server is running (`python -m app.codeagent.routes`)       |
| Agent times out                   | Increase `AGENT_TIMEOUT` in `.env` (default: 180 seconds)               |
| Ollama model not found            | Run `ollama pull qwen2.5-coder:3b` before starting agent                |
| WebSocket disconnection           | Check network connectivity; ensure Flask and agent servers both running |
| Loop detected, forcing completion | Agent hit reasoning limit; increase `AGENT_MAX_STEPS` if needed         |

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

## 📄 References

- [LangChain](https://github.com/hwchase17/langchain)
- [Ollama](https://github.com/ollama/ollama)
- [ChromaDB](https://github.com/chroma-core/chroma)
