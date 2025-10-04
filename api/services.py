# api/services.py

import os
import json
import chromadb
import numpy as np
import datetime
import google.generativeai as genai
from dotenv import load_dotenv
from sklearn.cluster import DBSCAN
import collections
import hashlib
from typing import Iterable

from .models import NewsArticle, AnalysisResult

# Load environment variables from .env file
load_dotenv()

# Configure the Gemini API client
GOOGLE_API_KEY = os.getenv('GEMINI_API_KEY')
if not GOOGLE_API_KEY:
    raise ValueError("GEMINI_API_KEY not found. Please set it in your .env file.")
genai.configure(api_key=GOOGLE_API_KEY)

chroma_client = chromadb.PersistentClient(path="./chroma_db")

gemini_ef = chromadb.utils.embedding_functions.GoogleGenerativeAiEmbeddingFunction(
    api_key=GOOGLE_API_KEY,
    model_name='models/text-embedding-004'
)

def get_news_date(date_format="%Y-%m-%d"):
    # Get the current date and time
    now = datetime.datetime.now()

    # The cutoff hour is 10 PM, which is 22 in 24-hour format
    cutoff_hour = 22

    # Check if the current hour is past the cutoff time
    if now.hour >= cutoff_hour:
        # It's 10 PM or later, so the news day is today
        target_date = datetime.date.today()
    else:
        # It's before 10 PM, so we should be looking at yesterday's news
        target_date = datetime.date.today() - datetime.timedelta(days=1)

    # Format the determined date into the desired string format
    return target_date.strftime(date_format)


def fetch_article(date_str: str) -> Iterable[NewsArticle]:
    res = (
        NewsArticle.objects
        .filter(article_date=date_)
    )

def create_cluster(collection_date: str):
    name = f"broadcasts_{collection_date.replace('-', '_')}"

    return chroma_client.get_or_create_collection(
        name=name,
        embedding_function=gemini_ef,
        metadata={"hnsw:space": "cosine"}  # cosine is best for sentence embeddings
    )

def _stable_id(article, collection_date: str) -> str:
    """
    Create a deterministic ID so re-ingesting the same item won’t duplicate.
    Use whatever fields best identify uniqueness (url is great if present).
    """
    company = str(getattr(article, "article_company", ""))
    order   = str(getattr(article, "article_order", ""))
    url     = str(getattr(article, "article_url", "")) 
    title   = str(getattr(article, "title", ""))

    key = f"{company}|{order}|{url}|{title}|{collection_date}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()

def ingest(articles: Iterable, collection, collection_date: str, batch_size: int = 128):
    docs, metas, ids = [], [], []

    for a in articles:
        ids.append(_stable_id(a, collection_date))
        docs.append(str(getattr(a, "article_script", "")))
        meta = {
            "company": str(getattr(a, "article_company", "")),
            "date": str(getattr(a, 'article_date', '')),
            "order": str(getattr(a, "article_order", None)),
            "title": getattr(a, "title", None),
        }
        metas.append(meta)

    collection.add(
        documents=docs,
        metadatas=metas,
        ids=ids
    )


def cluster_collection(collection, eps: float = 0.12, min_samples: int = 1):
    """
    Pull embeddings back out of Chroma and cluster with DBSCAN.
    eps is cosine distance if metric='cosine'.
    """
    data = collection.get(include=["embeddings", "documents", "metadatas"])
    if not data.get("embeddings"):
        raise RuntimeError("No embeddings returned; ensure include=['embeddings'] and embeddings exist.")

    X = np.array(data["embeddings"], dtype=np.float32)
    # DBSCAN can use cosine directly; normalization is optional here
    db = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine").fit(X)
    labels = db.labels_

    clusters = collections.defaultdict(list)
    for idx, label in enumerate(labels):
        if label == -1:
            continue  # noise
        clusters[int(label)].append({
            "id": data["ids"][idx],
            "text": data["documents"][idx],
            "meta": data["metadatas"][idx],
        })

    # Return list of clusters (each cluster is a list of items)
    return list(clusters.values())
    


# ==============================================================================
#  STEP 1B: LABELING (using LLM)
#  This function is also a pure data processor.
# ==============================================================================
def label_topic_clusters(clusters: list[list[dict]]) -> list[dict]:
    """
    Generates a topic label for each cluster and summarizes which companies contributed.
    """
    print(f"Starting labeling for {len(clusters)} topic clusters...")
    if not clusters:
        return []

    model = genai.GenerativeModel('gemini-1.5-flash')
    labeled_topics = []

    for i, cluster in enumerate(clusters):
        # Extract content for the prompt and sources for analysis
        cluster_contents = [item['content'] for item in cluster]
        cluster_sources = [item['source'] for item in cluster]
        
        items_str = "\n- ".join(cluster_contents)
        prompt = f"""
        Analyze the following news items, which have been clustered by topic.
        Provide a concise, descriptive topic label (5-7 words maximum) for this group.

        NEWS ITEMS:
        - {items_str}

        CONCISE TOPIC LABEL:
        """
        try:
            response = model.generate_content(prompt)
            label = response.text.strip().replace("*", "")
            
            # Count contributions from each source for this topic
            source_counts = dict(Counter(cluster_sources))

            labeled_topics.append({
                "topic_label": label,
                "total_items": len(cluster),
                "source_contribution": source_counts, # e.g., {'Company A': 3, 'Company B': 2}
                "items": cluster 
            })
            print(f"  - Labeled Cluster {i+1}: '{label}' (Sources: {source_counts})")
        except Exception as e:
            print(f"An error occurred during labeling cluster {i+1}: {e}")
            
    return labeled_topics

def generate_comparative_analysis(labeled_topics: list[dict], analysis_date: str) -> dict:
    """
    Performs a high-level comparative analysis of the news day based on the
    labeled topics and their sources.
    """
    print("Generating final comparative media analysis...")
    if not labeled_topics:
        return {}

    # Use a model that supports schema-enforced JSON output
    model = genai.GenerativeModel(
        'gemini-1.5-flash',
        generation_config={"response_schema": comparative_analysis_schema, "response_mime_type": "application/json"}
    )

    # Format the input for the prompt to be clear and concise
    topics_summary = []
    for topic in labeled_topics:
        sources_str = ", ".join([f"{source} ({count})" for source, count in topic['source_contribution'].items()])
        topics_summary.append(f"- Topic: \"{topic['topic_label']}\" (Total Items: {topic['total_items']}) | Covered by: {sources_str}")
    
    prompt = f"""
    You are a senior media critic. Analyze the news coverage from multiple companies for {analysis_date}.
    Based on the following summary of topics, provide a comparative analysis of their editorial choices.

    TOPIC SUMMARY:
    {'\n'.join(topics_summary)}

    Your analysis must identify the primary narrative of the day, compare the focus of each company,
    point out any topics covered uniquely by a single company, and note any significant potential omissions.
    """
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"An error occurred during comparative analysis: {e}")
        return {}


def analyze_article_script(script_text):
    """
    Sends a script to the Gemini API for analysis and returns the structured result.
    """

    model = genai.GenerativeModel(
        'gemini-2.5-flash',
        generation_config={"response_mime_type": "application/json"}
    )

    # This is the most important part: The Prompt!
    prompt = f"""
    You are a senior media analyst and broadcast news critic.
    Perform a sophisticated analysis of the following news script, focusing on its editorial choices, framing, and potential biases in korean.
    

    Your analysis must include the following components:
    - headline_analysis: Analyze the main headline. What is the topic? How is it framed? What other major stories might have been downplayed?
    - key_agenda_items: Identify 2-4 major news blocks. For each, describe the topic, its placement in the broadcast, and a brief analytic comment on the coverage angle.
    - editorial_critique: Provide a 2-4 sentence paragraph assessing the overall editorial stance of the broadcast.
    - notable_elements: List any stories claimed as "exclusives" and identify any potential major events that are conspicuously omitted from the broadcast.

    Here is the news script:
    ---
    {script_text}
    ---
    """

    try:
        response = model.generate_content(prompt)
        # Clean up the response to extract only the JSON part
        json_response_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        analysis_data = json.loads(json_response_text)
        return analysis_data
    except Exception as e:
        print(f"An error occurred during LLM analysis: {e}")
        # Return None or a default error structure if analysis fails
        return None


# ==============================================================================
#  THE ORCHESTRATOR - This is the key function that connects everything!
# ==============================================================================
def run_full_analysis_pipeline(article_id: int):

    date_str = analysis_date.strftime('%Y-%m-%d')

    # 1. FETCH data from the database
    try:
        article = NewsArticle.objects.get(pk=article_id)
    except NewsArticle.DoesNotExist:
        print(f"Error: Article with ID {article_id} not found.")
        return

    # Prevent re-running an expensive analysis
    if hasattr(article, 'analysis'):
        print(f"Analysis for Article {article_id} already exists. Skipping.")
        return
        
    # 2. EXTRACT the list of items
    items_to_process = article.items_list
    if not items_to_process:
        print(f"Article {article_id} has no items to analyze. Skipping.")
        return

    # 3. PROCESS the data through the pipeline
    # Step 1A
    item_clusters = create_chroma_clusters(items_to_process, threshold=0.6)
    if not item_clusters:
        print("Clustering failed. Aborting pipeline.")
        return
        
    # Step 1B
    labeled_data = label_clusters(item_clusters)
    if not labeled_data:
        print("Labeling failed. Aborting pipeline.")
        return
        
    # Step 2
    final_analysis = analyze_broadcast_structure(labeled_data)
    if not final_analysis:
        print("Final analysis failed. Aborting pipeline.")
        return

    # 4. SAVE the results back to the database
    try:
        AnalysisResult.objects.create(
            article=article,
            clustered_topics=labeled_data, # Save result of step 1
            headline_analysis=final_analysis.get('headline_analysis', {}),
            editorial_critique=final_analysis.get('editorial_critique', 'Critique failed.')
        )
        print(f"Successfully saved analysis for Article ID: {article_id}")
    except Exception as e:
        print(f"Error saving analysis result for Article {article_id}: {e}")