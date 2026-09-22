# Technical Specification: RAG, Retrieval Models & Vector Search Architecture

This document provides an exhaustive, technology-oriented technical specification of all Retrieval-Augmented Generation (RAG) paradigms, vector search mechanics, dimensionality reduction pipelines, clustering algorithms, agentic search tools, and NLP retrieval systems implemented in the **ResearchMate Server** codebase.

---

## Technical Architecture Overview

ResearchMate employs a multi-tier hybrid retrieval ecosystem designed to balance global macro-understanding of academic literature with high-precision micro-retrieval of exact technical claims. The system integrates five primary retrieval and generation paradigms:

```
                               ┌─────────────────────────────────────────────────────────┐
                               │             ResearchMate Retrieval Systems              │
                               └────────────────────────────┬────────────────────────────┘
                                                            │
    ┌──────────────────────────┬────────────────────────────┼────────────────────────────┬──────────────────────────┐
    │                          │                            │                            │                          │
┌───▼──────────────────┐ ┌─────▼──────────────────┐ ┌───────▼──────────────────┐ ┌───────▼──────────────────┐ ┌─────▼──────────────────┐
│   RAPTOR Tree RAG    │ │   Ephemeral FAISS      │ │ ReAct Agentic Search    │ │ NLP & Graph Engine       │ │ Streaming SSE Engine   │
│  Hierarchical Vector │ │   In-Memory Vector DB  │ │ ReAct Tool-Based DB     │ │ Classifier & Contradict. │ │ Direct Paper Summarizer│
│ (PGVector + Gemini)  │ │ (LangChain + FAISS)    │ │ (LaTeX Agent & SQL)     │ │ (NetworkX + scikit-learn)│ │ (Gemini 2.5 Flash SSE) │
└──────────────────────┘ └────────────────────────┘ └─────────────────────────┘ └──────────────────────────┘ └────────────────────────┘
```

---

## 1. RAPTOR RAG Engine (Hierarchical Tree Retrieval)

**Source File**: [`rag/raptor.py`](file:///c:/code-2025/Research-Management/rag/raptor.py)  
**Reference Paper**: *RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval* (Parthan et al.)

Standard RAG systems retrieve isolated text chunks based solely on cosine similarity, failing to capture overarching themes or synthesize cross-section insights across long academic papers. ResearchMate implements **RAPTOR**, which constructs a hierarchical tree of text chunks and cluster summaries, allowing retrieval across arbitrary levels of abstraction.

```
       Level 3 Node (Root Summary)           ◄── High-Level Synthesized Theme
               /         \
    Level 2 Summary     Level 2 Summary      ◄── Mid-Level Cluster Summaries
       /       \           /       \
  Leaf 1     Leaf 2     Leaf 3     Leaf 4    ◄── Low-Level Raw Text Chunks (Original Paper)
```

### 1.1 Text Splitting & Tokenization
- **Splitter**: `langchain.text_splitter.RecursiveCharacterTextSplitter`
- **Fast Mode Configuration**: `chunk_size = 3500`, `chunk_overlap = 0`, `n_levels = 2`
- **Standard Mode Configuration**: `chunk_size = 2000`, `chunk_overlap = 0`, `n_levels = 3`
- **Tokenizer**: `tiktoken` with `cl100k_base` encoding (`num_tokens_from_string`).

### 1.2 Embedding Model
- **Model**: `GoogleGenerativeAIEmbeddings`
- **Target Endpoint**: `models/gemini-embedding-2-preview`
- **Vector Dimensionality**: Dense floating-point vector representations generated for all raw text chunks as well as intermediate and root summary nodes.

### 1.3 Dimensionality Reduction (UMAP)
High-dimensional dense embeddings are projected into lower-dimensional space using **Uniform Manifold Approximation and Projection (UMAP)** (`umap.UMAP`) with a **Cosine Metric**:

$$\text{Cosine Distance: } d(u, v) = 1 - \frac{u \cdot v}{\|u\|_2 \|v\|_2}$$

1. **Global Clustering Reduction** ([`global_cluster_embeddings`](file:///c:/code-2025/Research-Management/rag/raptor.py#L64-L69)):
   - Evaluates the square root of dataset cardinality: $k = \lfloor \sqrt{N - 1} \rfloor$
   - Hyperparameters: `n_neighbors = k`, `n_components = dim` (default `dim = 10`), `metric = "cosine"`
2. **Local Clustering Reduction** ([`local_cluster_embeddings`](file:///c:/code-2025/Research-Management/rag/raptor.py#L72-L77)):
   - Hyperparameters: `n_neighbors = 10`, `n_components = dim`, `metric = "cosine"`

### 1.4 Soft Clustering via Gaussian Mixture Models (GMM)
To permit text chunks to belong to multiple semantic context groups (e.g., a methodology chunk discussing both computer vision and transformers), soft assignment clustering is executed using `sklearn.mixture.GaussianMixture`.

1. **Optimal Cluster Selection via Bayesian Information Criterion (BIC)** ([`get_optimal_clusters`](file:///c:/code-2025/Research-Management/rag/raptor.py#L82-L103)):
   The optimal number of components $n^* \in [1, \min(50, N)]$ is chosen by minimizing the BIC score:

   $$\text{BIC} = k \ln(N) - 2 \ln(\hat{L})$$

   where $k$ is the number of estimated parameters, $N$ is the number of sample embeddings, and $\hat{L}$ is the maximized log-likelihood of the model.

2. **Soft Cluster Assignment** ([`GMM_cluster`](file:///c:/code-2025/Research-Management/rag/raptor.py#L105-L122)):
   Vectors are assigned to every cluster $c$ whose posterior probability exceeds threshold $\tau = 0.1$:

   $$\text{Assign } x_i \text{ to cluster } c \iff P(c \mid x_i) > 0.1$$

### 1.5 Recursive Abstractive Summarization Pipeline
- **Chain Architecture**: `ChatPromptTemplate` $\rightarrow$ `ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)` $\rightarrow$ `StrOutputParser`
- **Summarization Algorithm** ([`recursive_embed_cluster_summarize`](file:///c:/code-2025/Research-Management/rag/raptor.py#L329-L359)):
  - **Level 1**: Original raw text chunks are clustered and summarized per cluster.
  - **Level 2**: Level 1 summaries are aggregated, embedded, re-clustered, and summarized.
  - **Level 3+**: Process recurses until maximum levels (`n_levels`) or single cluster convergence is reached.

### 1.6 Vector Database Engine & Persistence (PGVector)
- **Database**: PostgreSQL with `pgvector` extension.
- **ORM / Vector Store Wrapper**: `langchain_postgres.vectorstores.PGVector`
- **Collection Strategy**: Project-isolated collections named `raptor_{project_id}`.
- **Index Contents**: Stores **both** original leaf text chunks and all generated cluster summaries across all tree levels into PostgreSQL, enabling single-index hybrid macro/micro vector search.

### 1.7 QA Chain Execution
- **Prompt**: LangChain Hub template (`rlm/rag-prompt`).
- **Chain Flow** ([`asking_llm`](file:///c:/code-2025/Research-Management/rag/raptor.py#L574-L607)):
  $$\text{Query} \longrightarrow \text{PGVector Retriever} \longrightarrow \text{Formatted Context} \longrightarrow \text{Gemini 2.5 Flash} \longrightarrow \text{Grounded Answer}$$

---

## 2. Ephemeral In-Memory Retrieval Engine (FAISS)

**Source Function**: [`temporary_query_pipeline`](file:///c:/code-2025/Research-Management/rag/raptor.py#L525-L570)

For one-off, stateless text queries where database persistence is unnecessary, ResearchMate routes requests to an in-memory **FAISS (Facebook AI Similarity Search)** pipeline.

### 2.1 Technical Specifications
- **Vector Store**: `langchain_community.vectorstores.FAISS`
- **Embedding Model**: `GoogleGenerativeAIEmbeddings(model="gemini-embedding-2-preview")`
- **Index Type**: In-memory dense matrix index (`IndexFlatL2` / `IndexFlatIP`).
- **Lifespan**: Stateless. The index is instantiated during the execution of `temporary_query_pipeline()`, searched via similarity retrieval, and immediately garbage-collected without writing to PostgreSQL.

---

## 3. ReAct Agentic Retrieval & Tool Search Engine (LaTeX Agent)

**Source Files**: [`app/codeagent/agent.py`](file:///c:/code-2025/Research-Management/app/codeagent/agent.py), [`app/codeagent/routes.py`](file:///c:/code-2025/Research-Management/app/codeagent/routes.py), [`app/codeagent/llm.py`](file:///c:/code-2025/Research-Management/app/codeagent/llm.py)

The **LaTeX Agent** handles iterative research drafting, paper editing, and context retrieval using a **Reasoning + Acting (ReAct)** agentic loop running over WebSockets.

```
       ┌────────────────────────────────────────────────────────┐
       │                 User Goal / Edit Request               │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
                      ┌────────────────────────┐
                      │ Agent Reasoning Loop   │
                      │  (Thought Generation)  │
                      └────────────┬───────────┘
                                   │
             ┌─────────────────────┴─────────────────────┐
             ▼                                           ▼
   [Tool Call Required]                          [Tool Call: 'none']
             │                                           │
  ┌──────────┴──────────┐                      ┌─────────┴─────────┐
  │  Execute Agent Tool │                      │ Output Final      │
  │ - search_docs()     │                      │ LaTeX Document    │
  │ - read_doc()        │                      └───────────────────┘
  │ - read_paper()      │
  └──────────┬──────────┘
             │
             └────────► Observation Feedback ─┘
```

### 3.1 LLM Driver & Structured Output Parsing
- **LLM Backbone**: `GeminiLLM` wrapping `google.generativeai.GenerativeModel` (default: `gemini-1.5-flash` / `gemini-2.5-flash`).
- **Execution**: Asynchronous execution via `loop.run_in_executor` to prevent blocking the main asyncio event loop during API calls.
- **Pydantic Schema Validation**:
  - `ToolCall`: Enforces schema `{ "tool": str, "args": Dict[str, Any] }`.
  - `AgentThought`: Enforces schema `{ "thought": str, "tool_call": Optional[ToolCall], "final_latex": Optional[str] }`.

### 3.2 Agent Tool Implementations ([`ContextFetcher`](file:///c:/code-2025/Research-Management/app/codeagent/routes.py#L85-L144))
1. **`search_docs(query: str)`**:
   - **Search Mechanic**: Executes SQL wildcard pattern matching via SQLAlchemy `ilike`:
     ```sql
     SELECT * FROM document 
     WHERE doc_id IN (<project_paper_bucket>) 
       AND (title ILIKE '%query%' OR content ILIKE '%query%') 
     LIMIT 5;
     ```
2. **`read_doc(doc_id: str)`**:
   - **Search Mechanic**: Direct primary-key SQL lookup on `Document.doc_id`.
   - **Context Bounds**: Truncates content payload to 5,000 characters to optimize prompt token usage.
3. **`read_current_paper()`**:
   - **Search Mechanic**: Retrieves current LaTeX buffer from `Paper.content` for the active `project_id`.
4. **`none()`**:
   - **Mechanic**: Termination signal indicating the agent has gathered sufficient context to generate the complete updated LaTeX paper.

### 3.3 State Machine & Anti-Loop Safeguards
- **Maximum Reasoning Steps**: Enforces $N_{\text{max}} = 20$ (`AgentConfig.MAX_STEPS`).
- **Consecutive Repeat Detection**: Compares $T_t$ signature against $T_{t-1}$ signature (`tool_name:args`).
- **Historical Loop Detection**: If a tool call signature repeats after step 5, the agent triggers a forced completion workflow using a fallback prompt (`force_completion_prompt`) to prevent infinite reasoning loops.

---

## 4. Academic NLP, Relation Extraction & Citation Graph Engine

**Source Files**: [`service/analsys_control.py`](file:///c:/code-2025/Research-Management/service/analsys_control.py)

For granular linguistic analysis of research papers, the project includes an offline/batch NLP pipeline providing semantic search, sentence classification, relation extraction, contradiction detection, and citation graph topology modeling.

### 4.1 Intent-Based Semantic Search
- **Function**: `semantic_search(sentences, queries, top_k=10, threshold=0.6)`
- **Target Intents**:
  - *Limitations*: `"a limitation of this study is"`, `"we were unable to"`, `"a weakness of our approach"`
  - *Future Work*: `"future research should focus on"`, `"the next step is to"`, `"further investigation is needed"`
- **Filtering**: Filters sentence-query embedding similarities with a similarity threshold of $\ge 0.6$.

### 4.2 Weakly Supervised Sentence Classifier
- **Functions**: `train_sentence_classifier(sentences)` and `predict_sentence_labels(sentences, clf_obj)`
- **Class Labels**: `LIMITATION`, `METHOD`, `RESULT`, `FUTURE WORK`, `OBJECTIVE`.
- **Feature Extraction**: TF-IDF / N-gram vectorization combined with supervised classification models (`scikit-learn`).

### 4.3 Relation Extraction & Contradiction Detection
- **Function**: `detect_contradictions(relations, min_support=1)`
- **Algorithm**: Extracts Subject-Predicate-Object triplets and polarity flags from paper claims. Identifies opposing polarities across supporting evidence pairs to flag potential scientific contradictions in literature.

### 4.4 Citation Graph Analysis (NetworkX)
- **Functions**: `build_citation_graph(metadata_list)` and `analyze_graph(G)`
- **Graph Library**: `networkx`
- **Topological Metrics**:
  - **Directed Citation Graph**: Nodes represent papers/authors; directed edges represent citation references.
  - **Metrics Computed**: Degree Centrality, In-Degree/Out-Degree distribution, Connected Components, and Co-authorship clusters.

---

## 5. Streaming LLM Document Analysis Engine (SSE)

**Source File**: [`app/analyse/routes.py`](file:///c:/code-2025/Research-Management/app/analyse/routes.py)

For real-time visual progress monitoring during paper reading and summarization, ResearchMate uses a Server-Sent Events (SSE) streaming engine.

### 5.1 Protocol & Pipeline
- **Protocol**: HTTP Server-Sent Events (`mimetype='text/event-stream'`).
- **Chain**: `ChatPromptTemplate` $\rightarrow$ `ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.7)` $\rightarrow$ `StrOutputParser`.
- **Structured 5-Part Summarization Prompt**:
  1. *Problem Statement*
  2. *Proposed Approach*
  3. *Key Results*
  4. *Contributions*
  5. *Limitations & Future Work*
- **Progress Event Lifecycle**:
  - `10%`: Initialization & session registration (`/analyse/nlp`).
  - `30%`: Database fetch (`Document.query.filter_by(doc_id)`).
  - `60%`: Prompt execution & LLM invocation (`chain.invoke`).
  - `90%`: Finalizing summary payload.
  - `100%`: SSE completion packet delivery (`event_data` with predicted labels and confidence scores).

---

## 6. Comprehensive Technology Matrix

| System Component | Primary Model / Algorithm | Embedding / Vector Store | Index / Storage Strategy | Latency & Lifespan | Primary Use Case |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RAPTOR Engine** | `gemini-2.5-flash` + GMM + UMAP | `gemini-embedding-2-preview` | `PGVector` (`raptor_{project_id}`) | Persistent (PostgreSQL) | Multi-level deep research document QA |
| **Ephemeral RAG** | `gemini-2.5-flash` | `gemini-embedding-2-preview` | `FAISS` (In-Memory) | Transient / Instant (In-Memory) | Single-shot stateless document questions |
| **LaTeX ReAct Agent** | `gemini-1.5-flash` / `gemini-2.5-flash` | N/A (Relational SQL) | PostgreSQL (`ILIKE` search) | Real-time WebSocket | Interactive paper drafting & editing |
| **NLP Classifier** | TF-IDF + Weak Supervision | N/A (Feature Matrices) | In-Memory Model Object | Batch / Offline | Section tagging (Method, Result, Limitation) |
| **Citation Graph** | NetworkX Graph Models | N/A (Metadata Dicts) | NetworkX `DiGraph` | Memory-bound Graph | Citation centrality & co-authorship analysis |
| **SSE Summarizer** | `gemini-2.5-flash` | N/A (Direct Prompt) | Streaming SSE Generator | Live Streamed (HTTP SSE) | Real-time structured paper summary |

---

## 7. Source Code File Reference Map

- **RAPTOR RAG Implementation**: [`rag/raptor.py`](file:///c:/code-2025/Research-Management/rag/raptor.py)
  - `get_embeddings()`: [Line 35](file:///c:/code-2025/Research-Management/rag/raptor.py#L35)
  - `global_cluster_embeddings()`: [Line 64](file:///c:/code-2025/Research-Management/rag/raptor.py#L64)
  - `GMM_cluster()`: [Line 105](file:///c:/code-2025/Research-Management/rag/raptor.py#L105)
  - `recursive_embed_cluster_summarize()`: [Line 329](file:///c:/code-2025/Research-Management/rag/raptor.py#L329)
  - `RaptorPipeline()`: [Line 365](file:///c:/code-2025/Research-Management/rag/raptor.py#L365)
  - `temporary_query_pipeline()`: [Line 525](file:///c:/code-2025/Research-Management/rag/raptor.py#L525)
- **RAPTOR QA Runner**: [`rag/raptor_middleman.py`](file:///c:/code-2025/Research-Management/rag/raptor_middleman.py)
- **LaTeX Agent ReAct Loop**: [`app/codeagent/agent.py`](file:///c:/code-2025/Research-Management/app/codeagent/agent.py)
  - `LaTeXAgent.run()`: [Line 88](file:///c:/code-2025/Research-Management/app/codeagent/agent.py#L88)
- **LaTeX Agent Tools & WebSockets**: [`app/codeagent/routes.py`](file:///c:/code-2025/Research-Management/app/codeagent/routes.py)
  - `ContextFetcher`: [Line 85](file:///c:/code-2025/Research-Management/app/codeagent/routes.py#L85)
- **NLP Analysis Control**: [`service/analsys_control.py`](file:///c:/code-2025/Research-Management/service/analsys_control.py)
- **SSE Stream Handler**: [`app/analyse/routes.py`](file:///c:/code-2025/Research-Management/app/analyse/routes.py)
