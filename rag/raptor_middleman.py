from langchain import hub
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_ollama import ChatOllama


def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

def asking_llm(retriever, userQuestion):
    prompt = hub.pull("rlm/rag-prompt")

    model = ChatOllama(
        model="qwen2.5-coder:3b",
        temperature=2
    )

    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | model
        | StrOutputParser()
    )

    return rag_chain.invoke(userQuestion)
