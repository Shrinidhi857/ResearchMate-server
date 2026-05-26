import os
import numpy as np
import pandas as pd
import umap
from typing import List, Optional, Dict
from sklearn.mixture import GaussianMixture
from dotenv import load_dotenv
import tiktoken
import hashlib
import json
from pathlib import Path
import time
 
# LangChain Imports
from langchain_postgres.vectorstores import PGVector
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.output_parsers import StrOutputParser
from langchain import hub
from langchain_core.runnables import RunnablePassthrough
 
load_dotenv()
 
RANDOM_SEED = 224
 
# ═══════════════════════════════════════════════════════════════════════════
# DB CONNECTION & MODEL INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════
def get_connection_string():
    """Get PostgreSQL connection string for PGVector storage"""
    return os.getenv("DATABASE_URL")
 
 
def get_embeddings():
    """Initialize Google Generative AI embeddings model"""
    return GoogleGenerativeAIEmbeddings(
        model="gemini-embedding-2-preview",
        google_api_key=os.getenv("GEMINI_API_KEY")
    )
 
 
def get_llm():
    """Initialize Google Generative AI LLM for summarization and answering"""
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",       # free tier model
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0
    )
 
 
# ═══════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════
def num_tokens_from_string(string: str, encoding_name: str = "cl100k_base") -> int:
    """Count tokens in a string using tiktoken"""
    encoding = tiktoken.get_encoding(encoding_name)
    return len(encoding.encode(string))
 
 
# ═══════════════════════════════════════════════════════════════════════════
# UMAP DIMENSION REDUCTION
# ═══════════════════════════════════════════════════════════════════════════
def global_cluster_embeddings(embeddings: np.ndarray, dim: int) -> np.ndarray:
    """Reduce dimensionality globally across all embeddings"""
    n_neighbors = int((len(embeddings) - 1) ** 0.5)
    return umap.UMAP(
        n_neighbors=n_neighbors, n_components=dim, metric="cosine"
    ).fit_transform(embeddings)
 
 
def local_cluster_embeddings(embeddings: np.ndarray, dim: int) -> np.ndarray:
    """Reduce dimensionality within local clusters"""
    return umap.UMAP(
        n_neighbors=10, n_components=dim, metric="cosine"
    ).fit_transform(embeddings)
 
 
# ═══════════════════════════════════════════════════════════════════════════
# GAUSSIAN MIXTURE MODEL CLUSTERING
# ═══════════════════════════════════════════════════════════════════════════
def get_optimal_clusters(embeddings: np.ndarray, max_clusters: int = 50) -> int:
    """
    Determine optimal number of clusters using BIC criterion
    
    Args:
        embeddings: Embedding matrix (n_samples, n_features)
        max_clusters: Maximum clusters to evaluate
        
    Returns:
        Optimal number of clusters
    """
    max_clusters = min(max_clusters, len(embeddings))
    n_clusters = np.arange(1, max_clusters)
    bics = []
    
    for n in n_clusters:
        gm = GaussianMixture(n_components=n, random_state=RANDOM_SEED)
        gm.fit(embeddings)
        bics.append(gm.bic(embeddings))
    
    return n_clusters[np.argmin(bics)]
 
 
def GMM_cluster(embeddings: np.ndarray, threshold: float):
    """
    Cluster embeddings using Gaussian Mixture Model
    
    Args:
        embeddings: Embedding matrix
        threshold: Probability threshold for cluster assignment
        
    Returns:
        (labels, n_clusters): Cluster labels and count
    """
    n_clusters = get_optimal_clusters(embeddings)
    gm = GaussianMixture(n_components=n_clusters, random_state=0)
    gm.fit(embeddings)
    probs = gm.predict_proba(embeddings)
    labels = [np.where(prob > threshold)[0] for prob in probs]
    return labels, n_clusters
 
 
# ═══════════════════════════════════════════════════════════════════════════
# CLUSTERING PIPELINE
# ═══════════════════════════════════════════════════════════════════════════
def perform_clustering(embeddings: np.ndarray, dim: int, threshold: float):
    """
    Perform hierarchical clustering on embeddings
    
    SAFETY CHECKS:
    - Handles very small datasets (< 3 embeddings)
    - Gracefully falls back to single cluster if clustering fails
    - Ensures output length always matches input length
    
    Args:
        embeddings: Embedding matrix (n_embeddings, embedding_dim)
        dim: Target dimensionality for UMAP reduction
        threshold: GMM probability threshold
        
    Returns:
        List of cluster assignments per embedding
    """
    # Safety check 1: Too few embeddings for meaningful clustering
    if len(embeddings) <= dim + 1:
        print(f"DEBUG: Only {len(embeddings)} embeddings, skipping clustering")
        return [np.array([0]) for _ in range(len(embeddings))]
 
    # Safety check 2: Reduce dim if necessary
    actual_dim = min(dim, len(embeddings) - 2)
    if actual_dim < 2:
        return [np.array([0]) for _ in range(len(embeddings))]
 
    try:
        # Global clustering
        reduced_global = global_cluster_embeddings(embeddings, actual_dim)
        global_clusters, n_global = GMM_cluster(reduced_global, threshold)
 
        all_local_clusters = [np.array([0]) for _ in range(len(embeddings))]
        total_clusters = 0
 
        # Local clustering within each global cluster
        for i in range(n_global):
            mask = np.array([i in gc for gc in global_clusters])
            cluster_emb = embeddings[mask]
            cluster_indices = np.where(mask)[0]
 
            if len(cluster_emb) <= actual_dim + 1:
                # Too few points for local clustering
                for idx in cluster_indices:
                    all_local_clusters[idx] = np.array([total_clusters])
                n_local = 1
            else:
                # Perform local clustering
                reduced_local = local_cluster_embeddings(cluster_emb, actual_dim)
                local_clusters, n_local = GMM_cluster(reduced_local, threshold)
 
                if len(local_clusters) != len(cluster_emb):
                    # Fallback if clustering fails
                    for idx in cluster_indices:
                        all_local_clusters[idx] = np.array([total_clusters])
                else:
                    # Assign local cluster IDs
                    for j in range(n_local):
                        local_mask = np.array([j in lc for lc in local_clusters])
                        if len(local_mask) != len(cluster_indices):
                            continue
                        selected_idxs = cluster_indices[local_mask]
                        for idx in selected_idxs:
                            all_local_clusters[idx] = np.array([j + total_clusters])
 
            total_clusters += n_local
 
        # Final safety check
        if len(all_local_clusters) != len(embeddings):
            print(f"DEBUG: Clustering length mismatch, falling back to single cluster")
            return [np.array([0]) for _ in range(len(embeddings))]
 
        return all_local_clusters
 
    except Exception as e:
        print(f"DEBUG: Clustering failed: {e} — falling back to single cluster")
        return [np.array([0]) for _ in range(len(embeddings))]
 
 
# ═══════════════════════════════════════════════════════════════════════════
# EMBEDDING & CLUSTERING WRAPPER
# ═══════════════════════════════════════════════════════════════════════════
def embed_texts(texts: List[str], embd) -> np.ndarray:
    """
    Embed a list of texts using the embedding model
    
    Args:
        texts: List of text strings to embed
        embd: Embedding model instance
        
    Returns:
        NumPy array of embeddings
    """
    if not texts:
        raise ValueError("Cannot embed empty text list")
    
    embeddings_list = embd.embed_documents(texts)
    return np.array(embeddings_list)
 
 
def embed_cluster_texts(texts: List[str], embd) -> pd.DataFrame:
    """
    Embed texts and perform clustering
    
    Args:
        texts: List of text strings
        embd: Embedding model
        
    Returns:
        DataFrame with columns: [text, embd, cluster]
    """
    if not texts:
        raise ValueError("Cannot cluster empty text list")
    
    embd_np = embed_texts(texts, embd)
    clusters = perform_clustering(embd_np, 10, 0.1)
 
    print(f"DEBUG: texts={len(texts)}, embeddings={len(embd_np)}, clusters={len(clusters)}")
 
    # Safety fix — ensure all lists have same length
    min_len = min(len(texts), len(embd_np), len(clusters))
    texts = texts[:min_len]
    embd_np = embd_np[:min_len]
    clusters = clusters[:min_len]
 
    df = pd.DataFrame({
        "text": texts,
        "embd": list(embd_np),
        "cluster": clusters
    })
    return df
 
 
# ═══════════════════════════════════════════════════════════════════════════
# TEXT FORMATTING FOR LLM
# ═══════════════════════════════════════════════════════════════════════════
def fmt_txt(df: pd.DataFrame) -> str:
    """Format dataframe texts for LLM input"""
    return "\n---\n".join(df["text"].tolist())
 
 
# ═══════════════════════════════════════════════════════════════════════════
# RAPTOR: EMBED + CLUSTER + SUMMARIZE
# ═══════════════════════════════════════════════════════════════════════════
def embed_cluster_summarize_texts(texts: List[str], level: int, llm, embd) -> tuple:
    """
    Embed texts, cluster them, and generate summaries for each cluster
    
    Args:
        texts: List of text chunks to process
        level: Current hierarchical level (for tracking)
        llm: Language model instance
        embd: Embedding model instance
        
    Returns:
        (df_clusters, df_summary): Clustering results and summaries
    """
    df_clusters = embed_cluster_texts(texts, embd)
 
    # Expand clusters into individual rows (one row per cluster assignment)
    expanded = []
    for _, row in df_clusters.iterrows():
        for c in row["cluster"]:
            expanded.append({
                "text": row["text"],
                "embd": row["embd"],
                "cluster": c
            })
 
    expanded_df = pd.DataFrame(expanded)
    cluster_ids = expanded_df["cluster"].unique()
 
    # Setup LLM prompt for summarization
    prompt = ChatPromptTemplate.from_template("""
    You are a documentation summarizer.
    Provide a comprehensive summary of the following content.
    
    Content:
    {context}
    """)
 
    chain = prompt | llm | StrOutputParser()
 
    # Generate summary for each cluster
    summaries = []
    for cid in cluster_ids:
        texts_block = fmt_txt(expanded_df[expanded_df["cluster"] == cid])
        summary = chain.invoke({"context": texts_block})
        summaries.append(summary)
 
    df_summary = pd.DataFrame({
        "summaries": summaries,
        "level": [level] * len(summaries),
        "cluster": cluster_ids
    })
 
    return df_clusters, df_summary
 
 
# ═══════════════════════════════════════════════════════════════════════════
# RECURSIVE RAPTOR PIPELINE
# ═══════════════════════════════════════════════════════════════════════════
def recursive_embed_cluster_summarize(texts, level, n_levels, llm, embd) -> dict:
    """
    Recursively apply embed-cluster-summarize at multiple hierarchy levels
    
    This creates a hierarchical summary structure:
    Level 1: Original text chunks
    Level 2: Summaries of Level 1 clusters
    Level 3: Summaries of Level 2 clusters
    etc.
    
    Args:
        texts: Text chunks to process
        level: Current level (starts at 1)
        n_levels: Maximum number of levels
        llm: Language model
        embd: Embedding model
        
    Returns:
        Dictionary: {level: (df_clusters, df_summary), ...}
    """
    df_clusters, df_summary = embed_cluster_summarize_texts(texts, level, llm, embd)
    results = {level: (df_clusters, df_summary)}
 
    # Recurse if not at max level and have multiple clusters to summarize
    if level < n_levels and df_summary["cluster"].nunique() > 1:
        next_texts = df_summary["summaries"].tolist()
        results.update(
            recursive_embed_cluster_summarize(next_texts, level + 1, n_levels, llm, embd)
        )
 
    return results
 
 
# ═══════════════════════════════════════════════════════════════════════════
# MAIN RAPTOR PIPELINE - CORRECTED
# ═══════════════════════════════════════════════════════════════════════════
def RaptorPipeline(
    documents_content: List[Dict[str, str]],
    project_id: Optional[str] = None,
    fast_mode: bool = True,
    replace_collection: bool = True
) -> object:
    """
    RAPTOR (Recursive Abstractive Processing for Tree-Organized Retrieval)
    Main pipeline for creating hierarchical embeddings and storage.
    
    ✅ CORRECTED VERSION:
    - Takes document content directly (not just IDs)
    - No internal DB lookups
    - Explicit control over collection replacement
    - Better error handling
    
    Args:
        documents_content: List of dicts with keys "doc_id" and "content"
            Example: [{"doc_id": "uuid-1", "content": "..."}, ...]
        project_id: Project identifier for collection naming (optional)
        fast_mode: If True, 2 levels; if False, 3 levels
        replace_collection: If True, delete old collection; if False, keep and add
        
    Returns:
        Retriever object for querying the vectorstore
        
    Raises:
        ValueError: If no documents or content provided
    """
    
    # ─────────────────────────────────────────
    # VALIDATION
    # ─────────────────────────────────────────
    if not isinstance(documents_content, list):
        documents_content = [documents_content]
    
    if not documents_content:
        raise ValueError("No documents provided for RAPTOR pipeline")
    
    # Extract content from document dicts
    doc_texts = [
        d.get("content", "")
        for d in documents_content
        if d.get("content")
    ]
    
    if not doc_texts:
        raise ValueError("No document content found in provided documents")
    
    print(f"DEBUG: Processing {len(doc_texts)} documents for RAPTOR\n")
    
    # ─────────────────────────────────────────
    # CONFIGURATION
    # ─────────────────────────────────────────
    if fast_mode:
        chunk_size = 3500
        n_levels = 2
        print(f"DEBUG: Fast mode enabled (2 levels, chunk_size={chunk_size})\n")
    else:
        chunk_size = 2000
        n_levels = 3
        print(f"DEBUG: Slow mode enabled (3 levels, chunk_size={chunk_size})\n")
    
    # ─────────────────────────────────────────
    # TEXT CHUNKING
    # ─────────────────────────────────────────
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=0
    )
    all_chunks = splitter.split_text("\n---\n".join(doc_texts))
    print(f"DEBUG: Created {len(all_chunks)} text chunks\n")
    
    if not all_chunks:
        raise ValueError("Text splitting resulted in no chunks")
    
    # ─────────────────────────────────────────
    # INITIALIZE MODELS
    # ─────────────────────────────────────────
    llm = get_llm()
    embd = get_embeddings()
    
    # ─────────────────────────────────────────
    # RUN RAPTOR
    # ─────────────────────────────────────────
    start_time = time.time()
    raptor_results = recursive_embed_cluster_summarize(
        all_chunks,
        level=1,
        n_levels=n_levels,
        llm=llm,
        embd=embd
    )
    elapsed = time.time() - start_time
    print(f"DEBUG: RAPTOR processing completed in {elapsed:.2f}s\n")
    
    # ─────────────────────────────────────────
    # COLLECT ALL TEXTS FOR STORAGE
    # ─────────────────────────────────────────
    final_texts = all_chunks[:]
    for lvl in sorted(raptor_results.keys()):
        level_summaries = raptor_results[lvl][1]["summaries"].tolist()
        final_texts.extend(level_summaries)
    
    print(f"DEBUG: Total texts to embed: {len(final_texts)}")
    print(f"  - Original chunks: {len(all_chunks)}")
    print(f"  - Summaries from all levels: {len(final_texts) - len(all_chunks)}\n")
    
    # ─────────────────────────────────────────
    # STORE IN PGVECTOR (PERMANENT STORAGE)
    # ─────────────────────────────────────────
    collection_name = f"raptor_{project_id}" if project_id else "raptor_temp"
    
    vectordb = PGVector.from_texts(
        texts=final_texts,
        embedding=embd,
        collection_name=collection_name,
        connection=get_connection_string(),
        pre_delete_collection=replace_collection,  # ✅ EXPLICIT CONTROL
    )
    
    print(f"DEBUG: Stored {len(final_texts)} vectors in PGVector")
    print(f"DEBUG: Collection: '{collection_name}'")
    print(f"DEBUG: Replace mode: {replace_collection}\n")
    
    return vectordb.as_retriever()
 
 
# ═══════════════════════════════════════════════════════════════════════════
# RETRIEVER FOR EXISTING PROJECT COLLECTIONS
# ═══════════════════════════════════════════════════════════════════════════
def get_retriever(project_id: str) -> object:
    """
    Load retriever for an existing project
    
    Args:
        project_id: Project identifier
        
    Returns:
        Retriever object or None if not found
    """
    embd = get_embeddings()
    collection_name = f"raptor_{project_id}"
 
    try:
        vectordb = PGVector(
            embeddings=embd,
            collection_name=collection_name,
            connection=get_connection_string(),
        )
        print(f"DEBUG: Loaded retriever for project '{project_id}'\n")
        return vectordb.as_retriever()
    except Exception as e:
        print(f"ERROR loading retriever for {project_id}: {e}")
        return None
 
 
# ═══════════════════════════════════════════════════════════════════════════
# TEMPORARY QUERY FEATURE (NO STORAGE)
# ═══════════════════════════════════════════════════════════════════════════
def temporary_query_pipeline(text: str, question: str) -> str:
    """
    Feature 1: Direct text query without permanent storage
    
    Use case: One-off questions where you don't want to save embeddings
    
    Args:
        text: Input text to query against
        question: Question to ask about the text
        
    Returns:
        Answer from LLM based on text
        
    Note:
        Embeddings are NOT stored in database.
        This is a stateless, ephemeral query.
    """
    try:
        from langchain_community.vectorstores import FAISS
        
        if not text or not question:
            raise ValueError("Both text and question are required")
        
        # Initialize models
        embd = get_embeddings()
        llm = get_llm()
        
        # Create in-memory vectorstore (NOT persisted to DB)
        print(f"DEBUG: Creating temporary in-memory vectorstore\n")
        vectorstore = FAISS.from_texts(
            texts=[text],
            embedding=embd
        )
        retriever = vectorstore.as_retriever()
        
        # Query without storage
        answer = asking_llm(retriever, question)
        
        print(f"DEBUG: Temporary query completed (no storage)\n")
        return answer
        
    except Exception as e:
        print(f"ERROR in temporary query: {e}")
        raise
 
 
# ═══════════════════════════════════════════════════════════════════════════
# HELPER: LLM ANSWERING (RAG-based approach)
# ═══════════════════════════════════════════════════════════════════════════
def asking_llm(retriever, question: str) -> str:
    """
    Query the retriever and get an LLM answer using RAG pattern
    
    Uses LangChain's standard RAG prompt from hub for better performance
    
    Args:
        retriever: LangChain retriever object
        question: User's question
        
    Returns:
        LLM's answer based on retrieved context
    """
    try:
        prompt = hub.pull("rlm/rag-prompt")
        model = get_llm()
        
        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)
        
        rag_chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | prompt
            | model
            | StrOutputParser()
        )
        
        answer = rag_chain.invoke(question)
        return answer
        
    except Exception as e:
        print(f"ERROR in asking_llm: {e}")
        raise

 
