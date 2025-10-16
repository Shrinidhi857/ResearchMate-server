# full_pipeline.py
import os
import re
import json
import math
import glob
import nltk
import networkx as nx
import numpy as np
from lxml import etree
from collections import defaultdict, Counter

# Transformers / Embeddings
import torch
from transformers import AutoTokenizer, AutoModel

# scispaCy / spaCy
import spacy
import scispacy

# sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, accuracy_score
from sklearn.decomposition import PCA
import sklearn.metrics.pairwise as skpw

# nltk resources
nltk.download('wordnet')
from nltk.corpus import wordnet as wn

SCIBERT_MODEL = "allenai/scibert_scivocab_uncased"  # change if you prefer another
_device = "cuda" if torch.cuda.is_available() else "cpu"

print("Using device:", _device)

tokenizer = AutoTokenizer.from_pretrained(SCIBERT_MODEL)
model = AutoModel.from_pretrained(SCIBERT_MODEL).to(_device)
model.eval()  

def embed_texts(sentences, batch_size=16, pool="mean"):
    """
    Embed list of sentences with SciBERT.
    pool: "mean" or "cls"
    Returns numpy array (n_sentences, hidden_size)
    """
    embeddings = []
    with torch.no_grad():
        for i in range(0, len(sentences), batch_size):
            batch = sentences[i:i+batch_size]
            encoded = tokenizer(batch, padding=True, truncation=True, return_tensors="pt", max_length=256)
            input_ids = encoded["input_ids"].to(_device)
            attention_mask = encoded["attention_mask"].to(_device)
            out = model(input_ids=input_ids, attention_mask=attention_mask)
            last_hidden = out.last_hidden_state  # (B, T, D)
            if pool == "mean":
                mask = attention_mask.unsqueeze(-1)
                summed = (last_hidden * mask).sum(dim=1)
                denom = mask.sum(dim=1).clamp(min=1e-9)
                vecs = (summed / denom).cpu().numpy()
            else:  # CLS token
                vecs = last_hidden[:,0,:].cpu().numpy()
            embeddings.append(vecs)
    return np.vstack(embeddings)


# -------------------------
# 2) Semantic search: query embeddings + thresholding
# -------------------------
def build_query_embeddings(queries):
    return embed_texts(queries)

def semantic_search(sentences, query_phrases, top_k=5, threshold=0.75):
    """
    For each query phrase, return candidate sentences above threshold.
    Returns dict: {query_phrase: [(sentence, score), ...]}
    """
    q_embs = build_query_embeddings(query_phrases)
    s_embs = embed_texts(sentences)
    results = {}
    for qi, q in enumerate(query_phrases):
        scores = skpw.cosine_similarity(s_embs, q_embs[qi:qi+1]).ravel()
        idxs = np.where(scores >= threshold)[0]
        ranked = sorted([(sentences[i], float(scores[i])) for i in idxs], key=lambda x: -x[1])
        results[q] = ranked[:top_k]
    return results



def build_query_embeddings(queries):
    return embed_texts(queries)

def semantic_search(sentences, query_phrases, top_k=5, threshold=0.75):
    """
    For each query phrase, return candidate sentences above threshold.
    Returns dict: {query_phrase: [(sentence, score), ...]}
    """
    q_embs = build_query_embeddings(query_phrases)
    s_embs = embed_texts(sentences)
    results = {}
    for qi, q in enumerate(query_phrases):
        scores = skpw.cosine_similarity(s_embs, q_embs[qi:qi+1]).ravel()
        idxs = np.where(scores >= threshold)[0]
        ranked = sorted([(sentences[i], float(scores[i])) for i in idxs], key=lambda x: -x[1])
        results[q] = ranked[:top_k]
    return results


import en_core_web_sm
nlp = en_core_web_sm.load()

def extract_entities(sentences):
    """
    Returns list of entities per sentence:
    [ [(ent_text, ent_label), ...], ... ]
    """
    doclist = list(nlp.pipe(sentences, disable=["parser"]))
    all_ents = []
    for doc in doclist:
        ents = [(ent.text, ent.label_) for ent in doc.ents]
        all_ents.append(ents)
    return all_ents

WEAK_RULES = {
    "FUTURE_WORK": [
        "future work", "we plan to", "we will", "future research", "next step", "further investigation"
    ],
    "LIMITATION": [
        "limitat", "we were unable", "we could not", "shortcoming", "drawback", "restricted to", "small sample"
    ],
    "METHOD": [
        "we propose", "we present", "we introduce", "method", "approach", "algorithm", "model"
    ],
    "RESULT": [
        "we show", "we find", "results show", "our results", "demonstrate", "we observe"
    ],
    "OBJECTIVE": [
        "in this paper we", "the aim of this", "we aim to", "we seek to", "objective"
    ],
}

def weak_label_sentence(sentence):
    s = sentence.lower()
    for label, triggers in WEAK_RULES.items():
        for t in triggers:
            if t in s:
                return label
    return "NONE"

def weak_label_dataset(sentences):
    return [weak_label_sentence(s) for s in sentences]


def train_sentence_classifier(sentences, labels=None, test_size=0.2, random_state=42):
    """
    If labels not provided, uses weak supervision to generate noisy labels.
    Returns (clf, le, score_report, vectorizer (here: nothing), X_test, y_test)
    """
    # we are taking the labels frm weak label dataset that we created
    # in the above cell
    if labels is None:
        labels = weak_label_dataset(sentences)
    print(labels)
    le = LabelEncoder()
    y = le.fit_transform(labels)
    X = embed_texts(sentences)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=None )
    clf = LogisticRegression(max_iter=1000, multi_class="multinomial")
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)
    report = classification_report(y_test,y_pred,labels=np.unique(y_test),target_names=le.inverse_transform(np.unique(y_test)),zero_division=0)

    acc = accuracy_score(y_test, y_pred)
    return dict(classifier=clf, label_encoder=le, report=report, accuracy=acc, X_test=X_test, y_test=y_test, y_pred=y_pred)

def predict_sentence_labels(sentences, clf_obj):
    X = embed_texts(sentences)
    le = clf_obj["label_encoder"]
    ypred = clf_obj["classifier"].predict(X)
    return le.inverse_transform(ypred)


nlp_parser = spacy.load("en_core_web_sm")  # parser for SVO (you can use scispacy's parser if installed)

def extract_svo(sentence):
    """
    Return list of (subject, verb, object) tuples for a sentence
    Heuristic approach: find nsubj, dobj, or nsubjpass patterns.
    """
    doc = nlp_parser(sentence)
    svos = []
    for token in doc:
        if token.dep_ in ("ROOT","advcl","ccomp","xcomp"):
            verb = token
            subj = None
            obj = None
            for child in verb.children:
                if child.dep_ in ("nsubj", "nsubjpass"):
                    subj = child
                if child.dep_ in ("dobj", "pobj", "dative"):
                    obj = child
            # fallback: search nearby tokens
            if subj is None:
                for tok in verb.lefts:
                    if tok.dep_.startswith("nsubj"):
                        subj = tok
            if obj is None:
                for tok in verb.rights:
                    if tok.dep_.startswith("dobj") or tok.dep_.startswith("pobj"):
                        obj = tok
            if subj is not None and obj is not None:
                svos.append((subj.text, verb.lemma_, obj.text))
    return svos

# relation normalization and polarity map (simple)
RELATION_POLARITY = {
    # verbs mapped to polarity sign: +1 (increase/positive effect), -1 (decrease/negative effect), 0 (no effect/neutral)
    "increase": +1, "decrease": -1, "raise": +1, "lower": -1, "reduce": -1, "improve": +1, "worsen": -1,
    "show": 0, "demonstrate": 0, "have": 0, "affect": 0, "inhibit": -1, "stimulate": +1, "prevent": -1,
    # add more as you discover them
}

def relation_polarity(verb):
    v = verb.lower()
    if v in RELATION_POLARITY:
        return RELATION_POLARITY[v]
    # try WordNet synonyms as fallback
    synsets = wn.synsets(v, pos=wn.VERB)
    if not synsets:
        return 0
    # use first synset lemmas to attempt polarity mapping
    for syn in synsets[:3]:
        for lemma in syn.lemmas()[:3]:
            name = lemma.name().lower()
            if name in RELATION_POLARITY:
                return RELATION_POLARITY[name]
    return 0

def extract_relations_from_sentences(sentences):
    pairs = []
    for s in sentences:
        svos = extract_svo(s)
        for subj, verb, obj in svos:
            pol = relation_polarity(verb)
            pairs.append({"sentence": s, "subject": subj, "verb": verb, "object": obj, "polarity": pol})
    return pairs


from collections import defaultdict

def detect_contradictions(relations, min_support=2):
    """
    Detects contradictions for entity pairs with a more efficient checking mechanism.

    Args:
        relations (list): A list of relation dictionaries.
        min_support (int): The minimum number of relations required for a pair to be considered.

    Returns:
        list: A list of groups where opposing polarities (+1 and -1) exist.
    """
    # This initial grouping step is efficient and remains unchanged.
    clusters = defaultdict(list)
    for r in relations:
        pair = (r["subject"].lower(), r["object"].lower())
        clusters[pair].append(r)

    contradictions = []
    # Iterate through the clustered pairs
    for pair, rels in clusters.items():
        # First, perform the cheap check for minimum support.
        # This allows us to skip pairs that don't have enough relations.
        if len(rels) < min_support:
            continue

        # Use boolean flags to track polarities instead of building a set.
        has_positive = False
        has_negative = False

        for r in rels:
            if r["polarity"] == 1:
                has_positive = True
            elif r["polarity"] == -1:
                has_negative = True

            # **Key Optimization**: If both opposing polarities are found,
            # we can confirm the contradiction and stop iterating through this group.
            if has_positive and has_negative:
                contradictions.append({"pair": pair, "relations": rels})
                break # Exit the inner loop early

    return contradictions


def parse_grobid_tei(tei_xml_str):
    """
    Parse a GROBID TEI XML string and return metadata dict:
    { 'title':..., 'authors':[{'name':..., 'affiliation':...},...], 'references': [{'raw':..., 'title':..., 'authors': [...]}, ...] }
    """
    root = etree.fromstring(tei_xml_str.encode("utf-8"))
    ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
    meta = {}
    # title
    title_elems = root.xpath("//tei:titleStmt/tei:title", namespaces=ns)
    meta['title'] = title_elems[0].text if title_elems else None
    # authors
    authors = []
    for auth in root.xpath("//tei:sourceDesc//tei:author | //tei:teiHeader//tei:fileDesc//tei:titleStmt//tei:author", namespaces=ns):
        name = "".join(auth.itertext()).strip()
        if name:
            authors.append({'name': name})
    meta['authors'] = authors
    # references: gather reference strings
    refs = []
    for ref in root.xpath("//tei:listBibl/tei:biblStruct", namespaces=ns):
        raw = "".join(ref.itertext()).strip()
        refs.append({'raw': raw})
    meta['references'] = refs
    return meta

def build_citation_graph(metadata_list):
    """
    metadata_list: list of dicts returned by parse_grobid_tei for multiple papers
    - Each metadata should ideally have a unique id (we will use index or title as id)
    returns NetworkX DiGraph with nodes for papers and authors
    """
    G = nx.DiGraph()
    # create paper nodes
    id_by_title = {}
    for i, meta in enumerate(metadata_list):
        pid = meta.get('title') or f"paper_{i}"
        id_by_title[pid] = pid
        G.add_node(pid, type='paper', title=meta.get('title'))
        # authors
        for a in meta.get('authors', []):
            aname = a.get('name')
            if aname:
                G.add_node(aname, type='author')
                G.add_edge(aname, pid, type='authored')  # author->paper
    # citations: if metadata references string contains titles of other papers in the dataset,
    # create directed edge from citing paper -> referenced paper
    # This is heuristic; better to normalize DOIs/IDs
    titles = [m.get('title','').lower() for m in metadata_list]
    for meta in metadata_list:
        src = meta.get('title') or "unknown"
        for ref in meta.get('references', []):
            raw = ref.get('raw','').lower()
            for tgt_title in titles:
                if not tgt_title:
                    continue
                if tgt_title in raw and tgt_title != (src or "").lower():
                    G.add_edge(src, tgt_title, type='cites')
    return G


def analyze_graph(G, topk=10):
    # compute in-degree for papers
    in_degrees = [(n, d) for n, d in G.in_degree() if G.nodes[n].get('type')=='paper']
    in_degrees_sorted = sorted(in_degrees, key=lambda x: -x[1])[:topk]
    # pageRank (whole graph)
    pr = nx.pagerank(G)
    # author centrality (degree)
    author_nodes = [n for n in G.nodes if G.nodes[n].get('type')=='author']
    author_deg = sorted([(n, G.degree(n)) for n in author_nodes], key=lambda x: -x[1])[:topk]
    return {
        "top_cited_papers": in_degrees_sorted,
        "page_rank_top": sorted(pr.items(), key=lambda x: -x[1])[:topk],
        "top_authors_by_degree": author_deg
    }


