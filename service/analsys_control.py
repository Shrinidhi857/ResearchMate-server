from analysis_tool import semantic_search
from analysis_tool import extract_entities
from analysis_tool import train_sentence_classifier
from analysis_tool import  predict_sentence_labels 
from analysis_tool import extract_relations_from_sentences
from analysis_tool import detect_contradictions
from analysis_tool import build_citation_graph
from analysis_tool import analyze_graph


def analysispipeline(sentences):    # Small toy example dataset (replace with real sentences from PDFs)
    """sentences = [
    # --- LIMITATION ---
    "Our study is limited by the small sample size.",
    "We were unable to obtain complete demographic information for all participants.",
    "A major limitation of this study is the lack of long-term follow-up data.",
    "The dataset used in this work was restricted to English-language publications.",
    "We could not include patients with comorbidities due to data unavailability.",
    "Our results may not generalize to other populations due to the small sample.",
    "One shortcoming of our approach is the reliance on self-reported data.",
    "The study was limited by technical constraints in the imaging process.",

    # --- METHOD ---
    "We propose a new CNN architecture for image classification.",
    "We present a transformer-based model for sequence prediction.",
    "We introduce an unsupervised clustering approach for gene expression analysis.",
    "Our method leverages reinforcement learning to improve dialogue systems.",
    "The proposed algorithm reduces computational complexity by 30%.",
    "This model uses an attention mechanism to focus on key temporal features.",
    "Our approach integrates statistical and deep learning methods for robustness.",
    "We designed a multi-step optimization framework for hyperparameter tuning.",

    # --- RESULT ---
    "We show that our model outperforms existing baselines on all datasets.",
    "The results demonstrate a significant improvement in accuracy and recall.",
    "Our results confirm the hypothesis that temperature influences conductivity.",
    "We observe consistent trends across all experimental runs.",
    "The findings indicate a strong correlation between dose and response.",
    "We find that increasing the training data size improves performance.",
    "Our results show that the proposed algorithm achieves state-of-the-art performance.",

    # --- FUTURE WORK ---
    "Further investigation is needed to validate these results in diverse populations.",
    "In future work, we plan to expand the dataset with real-world samples.",
    "We will explore integrating additional modalities in subsequent research.",
    "Future research should focus on improving interpretability of the model.",
    "The next step is to deploy the system in a clinical environment.",
    "We plan to apply the same framework to other biomedical datasets.",
    "Future studies will examine the scalability of the proposed approach.",

    # --- OBJECTIVE ---
    "In this paper, we aim to improve text summarization using neural attention.",
    "The objective of this study is to evaluate the impact of noise reduction techniques.",
    "We seek to bridge the gap between theoretical models and real-world performance.",
    "The aim of this research is to develop a cost-effective diagnostic tool."]"""


    # Semantic search: queries for limitation & future work
    limitation_queries = ["a limitation of this study is", "we were unable to", "a weakness of our approach"]
    future_queries = ["future research should focus on", "the next step is to", "further investigation is needed"]
    queries = limitation_queries + future_queries

    semres = semantic_search(sentences, queries, top_k=10, threshold=0.6)
    print("\n=== Semantic search candidates (threshold=0.6) ===")
    for q, items in semres.items():
        print(f"\nQuery: {q}")
        for s, score in items:
            print(f"  {score:.3f} | {s}")

    # Extract entities from candidate sentences
    # Flatten candidate sentences (unique)
    candidate_sents = set()
    for items in semres.values():
        for s, _ in items:
            candidate_sents.add(s)
    candidate_sents = list(candidate_sents)
    ents = extract_entities(candidate_sents)
    print("\n=== Entities in candidates ===")
    for s, e in zip(candidate_sents, ents):
        print(s, "->", e)

    # Train classifier using weak labels
    clf_obj = train_sentence_classifier(sentences)  # uses weak supervision
    print("\n=== Classifier report ===")
    print(clf_obj["report"])
    print("Accuracy:", clf_obj["accuracy"])

    # Predict labels on new set (same sentences)
    preds = predict_sentence_labels(sentences, clf_obj)
    print("\n=== Predicted labels ===")
    for s, p in zip(sentences, preds):
        print(p, "|", s)

    # Relation extraction
    relations = extract_relations_from_sentences(sentences)
    print("\n=== Extracted relations ===")
    for r in relations:
        print(r)

    # Contradiction detection
    contradictions = detect_contradictions(relations, min_support=1)
    print("\n=== Contradictions found ===")
    for c in contradictions:
        print("Pair:", c["pair"])
        for r in c["relations"]:
            print("  ", r["sentence"], "polarity:", r["polarity"])

    # Example GROBID TEI parsing (toy: if you have TEI xmls, call parse_grobid_tei)
    # For demonstration, create two simple metadata dicts:
    metadata_list = [
        {'title': 'Paper A', 'authors': [{'name':'Alice'}], 'references': [{'raw': 'Paper B by Bob'}]},
        {'title': 'Paper B', 'authors': [{'name':'Bob'}], 'references': [{'raw': 'nothing relevant'}]}
    ]
    G = build_citation_graph(metadata_list)
    analysis = analyze_graph(G)
    print("\n=== Graph analysis ===")
    print(json.dumps(analysis, indent=2))