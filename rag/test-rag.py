import json
from datetime import datetime

# ============================================
# IMPORT YOUR FUNCTIONS
# ============================================
from langchain import hub
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_ollama import ChatOllama, OllamaEmbeddings

from rag.raptor import (
    RaptorPipeline,
    recursive_embed_cluster_summarize,
)
from rag.raptor import get_documents as original_get_documents


# ============================================
# MOCK USER + MOCK DOCUMENTS
# ============================================
class FakeUser:
    id = "user123"


MOCK_DOCS = [
    {
        "doc_id": "1",
        "content": "Python is a high-level programming language used for AI and backend systems.",
        "created_at": datetime.now().isoformat(),
    },
    {
        "doc_id": "2",
        "content": "Machine learning models can be trained using datasets and optimized with gradient descent.",
        "created_at": datetime.now().isoformat(),
    },
]


# Monkeypatch get_documents()
def fake_get_documents(user):
    return MOCK_DOCS


# Override the original function
import rag.raptor as raptor
raptor.get_documents = fake_get_documents


# ============================================
# IMPORT asking_llm() HERE
# ============================================
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)


def asking_llm(retriever, userQuestion):
    prompt = hub.pull("rlm/rag-prompt")

    model = ChatOllama(
        model="gemma2:2b",
        temperature=0
    )

    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | model
        | StrOutputParser()
    )

    return rag_chain.invoke(userQuestion)


# ============================================
# FULL TEST PIPELINE
# ============================================
if __name__ == "__main__":
    print("\n=== STEP 1: Running RAPTOR Analysis ===")
    user = FakeUser()

    # Select document IDs
    selected_docs = [{"doc_id": "1"}, {"doc_id": "2"}]

    retriever = RaptorPipeline(user, selected_docs)
    print("RAPTOR retriever created successfully!\n")

    print("=== STEP 2: Asking RAG question ===")
    question = "What do these documents say about machine learning?"
    answer = asking_llm(retriever, question)

    print("\n=== FINAL ANSWER ===")
    print(answer)
