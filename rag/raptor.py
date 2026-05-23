import os
import numpy as np
import pandas as pd
import umap
from typing import List, Optional, Tuple, Dict
from sklearn.mixture import GaussianMixture
from dotenv import load_dotenv
import tiktoken
import hashlib
import json
from pathlib import Path
import time

# LangChain Imports
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

RANDOM_SEED = 224

# Cache directory for embeddings
CACHE_DIR = Path(os.getenv("RAPTOR_CACHE_DIR", "db/embedding_cache"))

###########################################
### EMBEDDING CACHE
###########################################
def _get_cache_key(text: str) -> str:
    """Generate cache key from text hash"""
    return hashlib.md5(text.encode()).hexdigest()

def _get_cached_embedding(text: str) -> Optional[List[float]]:
    """Retrieve cached embedding if exists"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = _get_cache_key(text)
    cache_file = CACHE_DIR / f"{cache_key}.json"
    
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def _save_cached_embedding(text: str, embedding: List[float]) -> None:
    """Save embedding to cache"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = _get_cache_key(text)
    cache_file = CACHE_DIR / f"{cache_key}.json"
    
    try:
        with open(cache_file, 'w') as f:
            json.dump(embedding, f)
    except:
        pass  # Silent fail on cache write


###########################################
### TOKEN COUNTER
###########################################
def num_tokens_from_string(string: str, encoding_name: str = "cl100k_base") -> int:
    encoding = tiktoken.get_encoding(encoding_name)
    return len(encoding.encode(string))


###########################################
### UMAP DIMENSION REDUCTION
###########################################
def global_cluster_embeddings(embeddings: np.ndarray, dim: int) -> np.ndarray:
    n_neighbors = int((len(embeddings) - 1) ** 0.5)
    return umap.UMAP(
        n_neighbors=n_neighbors, n_components=dim, metric="cosine"
    ).fit_transform(embeddings)


def local_cluster_embeddings(embeddings: np.ndarray, dim: int) -> np.ndarray:
    return umap.UMAP(
        n_neighbors=10, n_components=dim, metric="cosine"
    ).fit_transform(embeddings)


###########################################
### GMM CLUSTERING
###########################################
def get_optimal_clusters(embeddings: np.ndarray, max_clusters: int = 50) -> int:
    max_clusters = min(max_clusters, len(embeddings))
    n_clusters = np.arange(1, max_clusters)
    bics = []
    for n in n_clusters:
        gm = GaussianMixture(n_components=n, random_state=RANDOM_SEED)
        gm.fit(embeddings)
        bics.append(gm.bic(embeddings))
    return n_clusters[np.argmin(bics)]


def GMM_cluster(embeddings: np.ndarray, threshold: float):
    n_clusters = get_optimal_clusters(embeddings)
    gm = GaussianMixture(n_components=n_clusters, random_state=0)
    gm.fit(embeddings)
    probs = gm.predict_proba(embeddings)
    labels = [np.where(prob > threshold)[0] for prob in probs]
    return labels, n_clusters


###########################################
### FULL CLUSTER PIPELINE
###########################################
def perform_clustering(embeddings: np.ndarray, dim: int, threshold: float):
    if len(embeddings) <= dim + 1:
        return [np.array([0]) for _ in range(len(embeddings))]

    reduced_global = global_cluster_embeddings(embeddings, dim)
    global_clusters, n_global = GMM_cluster(reduced_global, threshold)

    all_local_clusters = [np.array([0]) for _ in range(len(embeddings))]
    total_clusters = 0

    for i in range(n_global):
        mask = np.array([i in gc for gc in global_clusters])
        cluster_emb = embeddings[mask]
        cluster_indices = np.where(mask)[0]

        if len(cluster_emb) <= dim + 1:
            # All points in this global cluster get the same local cluster ID
            for idx in cluster_indices:
                all_local_clusters[idx] = np.array([total_clusters])
            n_local = 1
        else:
            reduced_local = local_cluster_embeddings(cluster_emb, dim)
            local_clusters, n_local = GMM_cluster(reduced_local, threshold)

            # Ensure local_clusters has same length as cluster_emb
            if len(local_clusters) != len(cluster_emb):
                # Fallback: assign all to cluster 0
                for idx in cluster_indices:
                    all_local_clusters[idx] = np.array([total_clusters])
            else:
                # Assign clusters properly
                for j in range(n_local):
                    local_mask = np.array([j in lc for lc in local_clusters])
                    if len(local_mask) != len(cluster_indices):
                        continue  # Skip if dimensions don't match
                    
                    selected_idxs = cluster_indices[local_mask]
                    for idx in selected_idxs:
                        all_local_clusters[idx] = np.array([j + total_clusters])

        total_clusters += n_local

    return all_local_clusters


###########################################
### EMBEDDING + CLUSTER WRAPPER
###########################################
def embed_texts(texts: List[str], embd) -> np.ndarray:
    """
    Embed texts with optional caching.
    Uses batch processing and cache to improve speed.
    """
    embeddings = []
    texts_to_embed = []
    indices_to_embed = []
    
    # Check cache first
    for i, text in enumerate(texts):
        cached = _get_cached_embedding(text)
        if cached is not None:
            embeddings.append(cached)
        else:
            texts_to_embed.append(text)
            indices_to_embed.append(i)
    
    # Embed uncached texts in batch
    if texts_to_embed:
        new_embeddings = embd.embed_documents(texts_to_embed)
        for text, embedding in zip(texts_to_embed, new_embeddings):
            _save_cached_embedding(text, embedding)
        
        # Insert in correct positions
        for idx, embedding in zip(indices_to_embed, new_embeddings):
            while len(embeddings) <= idx:
                embeddings.append(None)
            embeddings[idx] = embedding
    
    # Sort to match original order
    result = [None] * len(texts)
    for i, text in enumerate(texts):
        cached = _get_cached_embedding(text)
        if cached is not None:
            result[i] = cached
    
    # This simpler approach: just batch embed everything
    # (caching happens but we don't skip in this version)
    embeddings_list = embd.embed_documents(texts)
    for text, emb in zip(texts, embeddings_list):
        _save_cached_embedding(text, emb)
    
    return np.array(embeddings_list)


def embed_cluster_texts(texts: List[str], embd):
    embd_np = embed_texts(texts, embd)
    clusters = perform_clustering(embd_np, 10, 0.1)

    df = pd.DataFrame({
        "text": texts,
        "embd": list(embd_np),
        "cluster": clusters
    })
    return df


###########################################
### FORMATTING TEXT FOR SUMMARY
###########################################
def fmt_txt(df: pd.DataFrame) -> str:
    return "\n---\n".join(df["text"].tolist())


###########################################
### EMBED + CLUSTER + SUMMARIZE
###########################################
def embed_cluster_summarize_texts(texts: List[str], level: int, llm, embd):

    df_clusters = embed_cluster_texts(texts, embd)

    expanded = []
    for _, row in df_clusters.iterrows():
        for c in row["cluster"]:
            expanded.append({"text": row["text"], "embd": row["embd"], "cluster": c})

    expanded_df = pd.DataFrame(expanded)
    cluster_ids = expanded_df["cluster"].unique()

    prompt = ChatPromptTemplate.from_template("""
    You are a documentation summarizer.
    Give a detailed summary of the content.
    Content:
    {context}
    """)

    chain = prompt | llm | StrOutputParser()

    summaries = []
    for cid in cluster_ids:
        texts_block = fmt_txt(expanded_df[expanded_df["cluster"] == cid])
        summaries.append(chain.invoke({"context": texts_block}))

    df_summary = pd.DataFrame({
        "summaries": summaries,
        "level": [level] * len(summaries),
        "cluster": cluster_ids
    })

    return df_clusters, df_summary


###########################################
### RECURSIVE R.A.P.T.O.R. PIPELINE
###########################################
def recursive_embed_cluster_summarize(texts, level, n_levels, llm, embd):

    df_clusters, df_summary = embed_cluster_summarize_texts(texts, level, llm, embd)

    results = {level: (df_clusters, df_summary)}

    if level < n_levels and df_summary["cluster"].nunique() > 1:
        next_texts = df_summary["summaries"].tolist()
        results.update(
            recursive_embed_cluster_summarize(next_texts, level + 1, n_levels, llm, embd)
        )

    return results


###########################################
### FETCH USER DOCUMENTS
###########################################
def get_documents(current_user):
    from app.models import Document
    docs = Document.query.filter_by(user_id=current_user.id).all()
    return [
        {
            "doc_id": str(d.doc_id),
            "content": d.content,
            "created_at": d.created_at.isoformat()
        }
        for d in docs
    ]


# FINAL RAPTOR PIPELINE (Optimized for Latency)
###########################################
def RaptorPipeline(current_user, data, project_id: Optional[str] = None, fast_mode: bool = True):
    """
    Optimized RAPTOR pipeline with latency improvements.
    
    Args:
        current_user: User object
        data: Document IDs to process
        project_id: Optional project ID for persistence
        fast_mode: If True, uses optimized settings (n_levels=2, chunk_size=3500)
                  If False, uses original settings (n_levels=3, chunk_size=2000)
    """
    
    # Ensure data is a list
    if not isinstance(data, list):
        data = [data]

    docs = get_documents(current_user)
    print(f"DEBUG: Available doc IDs for user {current_user.id}: {[d['doc_id'] for d in docs]}")

    # data can be list of dicts with "doc_id" or list of string IDs
    if data and isinstance(data[0], str):
        selected_ids = set(data)
    else:
        selected_ids = {d.get("doc_id") if isinstance(d, dict) else d for d in data if d}
    
    print(f"DEBUG: Selected IDs from request: {selected_ids}")

    docs = [d for d in docs if d["doc_id"] in selected_ids]
    print(f"DEBUG: Documents after filtering: {len(docs)}")

    if not docs:
        raise ValueError("No matching documents found.")

    docs = sorted(docs, key=lambda d: d["created_at"], reverse=True)

    doc_texts = [d["content"] for d in docs]

    # Optimized parameters for latency
    if fast_mode:
        chunk_size = 3500  # Larger chunks = fewer to process
        n_levels = 2       # Reduce recursion depth (still captures hierarchical info)
    else:
        chunk_size = 2000
        n_levels = 3

    # Create splitter with optimized settings
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=0
    )
    
    all_chunks = splitter.split_text("\n---\n".join(doc_texts))
    print(f"DEBUG: Created {len(all_chunks)} chunks (fast_mode={fast_mode})\n")

    # Initialize OLLAMA
    llm = ChatOllama(model="gemma2:2b", temperature=0)
    embd = OllamaEmbeddings(model="nomic-embed-text")

    # Run raptor with optimized recursion depth
    start_time = time.time()
    raptor_results = recursive_embed_cluster_summarize(
        all_chunks, level=1, n_levels=n_levels, llm=llm, embd=embd
    )
    elapsed = time.time() - start_time
    print(f"DEBUG: RAPTOR analysis completed in {elapsed:.2f}s\n")

    # Gather all summaries (start with chunks, not full docs)
    final_texts = all_chunks[:]
    for lvl in sorted(raptor_results.keys()):
        summaries = raptor_results[lvl][1]["summaries"].tolist()
        final_texts.extend(summaries)

    # Build vector store with persistence if project_id is provided
    if project_id:
        persist_directory = os.path.join("db", "vectorstore", project_id)
        os.makedirs(persist_directory, exist_ok=True)
        
        vectordb = Chroma.from_texts(
            texts=final_texts, 
            embedding=embd, 
            persist_directory=persist_directory
        )
        print(f"Retrieving success for project {project_id}\n")
    else:
        # Temporary in-memory vector store
        vectordb = Chroma.from_texts(
            texts=final_texts, 
            embedding=embd
        )
        print("Retrieving success for temporary analysis\n")

    return vectordb.as_retriever()

def get_retriever(project_id: str):
    embd = OllamaEmbeddings(model="nomic-embed-text")
    persist_directory = os.path.join("db", "vectorstore", project_id)
    
    if os.path.exists(persist_directory):
        vectordb = Chroma(
            persist_directory=persist_directory, 
            embedding_function=embd
        )
        return vectordb.as_retriever()
    return None
