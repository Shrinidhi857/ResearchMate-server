import os
import numpy as np
import pandas as pd
import umap
from typing import List, Optional, Tuple, Dict
from sklearn.mixture import GaussianMixture
from dotenv import load_dotenv
import tiktoken

# LangChain Imports
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

RANDOM_SEED = 224

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

    all_local_clusters = [np.array([]) for _ in embeddings]
    total_clusters = 0

    for i in range(n_global):
        mask = np.array([i in gc for gc in global_clusters])
        cluster_emb = embeddings[mask]

        if len(cluster_emb) <= dim + 1:
            local_clusters = [np.array([0])]
            n_local = 1
        else:
            reduced_local = local_cluster_embeddings(cluster_emb, dim)
            local_clusters, n_local = GMM_cluster(reduced_local, threshold)

        # Assign clusters
        for j in range(n_local):
            local_mask = np.array([j in lc for lc in local_clusters])
            idxs = np.where(mask)[0][local_mask]
            for idx in idxs:
                all_local_clusters[idx] = np.append(
                    all_local_clusters[idx], j + total_clusters
                )

        total_clusters += n_local

    return all_local_clusters


###########################################
### EMBEDDING + CLUSTER WRAPPER
###########################################
def embed_texts(texts: List[str], embd) -> np.ndarray:
    # embd.embed_documents returns list-like; convert to numpy array
    return np.array(embd.embed_documents(texts))


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


# FINAL RAPTOR PIPELINE (Ollama + LLaMA3)
###########################################
def RaptorPipeline(current_user, data, project_id: str):

    docs = get_documents(current_user)

    selected_ids = {d["doc_id"] for d in data}
    docs = [d for d in docs if d["doc_id"] in selected_ids]

    if not docs:
        raise ValueError("No matching documents found.")

    docs = sorted(docs, key=lambda d: d["created_at"], reverse=True)

    doc_texts = [d["content"] for d in docs]

    # Create splitter (use portable constructor)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=2000,
        chunk_overlap=0
    )
    # Correcting logic: split_text returns list of strings
    # But we want to split each document separately or join them with a separator
    # The original code joined them with "---"
    all_chunks = splitter.split_text("\n---\n".join(doc_texts))

    # Initialize OLLAMA
    # Use llama3 for summarization + nomic-embed-text for embeddings (must be pulled)
    llm = ChatOllama(model="gemma2:2b", temperature=0)
    embd = OllamaEmbeddings(model="nomic-embed-text")

    # Run raptor
    raptor_results = recursive_embed_cluster_summarize(
        doc_texts, level=1, n_levels=3, llm=llm, embd=embd
    )

    # Gather all summaries
    final_texts = doc_texts[:]
    for lvl in sorted(raptor_results.keys()):
        summaries = raptor_results[lvl][1]["summaries"].tolist()
        final_texts.extend(summaries)

    # Build vector store with persistence
    persist_directory = os.path.join("db", "vectorstore", project_id)
    
    # Ensure directory exists
    os.makedirs(persist_directory, exist_ok=True)
    
    vectordb = Chroma.from_texts(
        texts=final_texts, 
        embedding=embd, 
        persist_directory=persist_directory
    )
    
    retriever = vectordb.as_retriever()
    print(f"Retrieving success for project {project_id}\n")

    return retriever

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
