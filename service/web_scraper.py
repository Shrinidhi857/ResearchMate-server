#This stage works with  scraping for the resources all over the 
# intenet using perplexity api , using the links sent by llm to download 
# pdf and articles extracting the data  analysing  data and generating 
#insights and creating the 

# Stage 2: Scraping + Downloading + Extracting + Cleaning

import google.generativeai as genai
from dotenv import load_dotenv
import os
import requests
import re
import ast
from PyPDF2 import PdfReader  # install with: pip install pypdf

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize model
model = genai.GenerativeModel("gemini-2.0-flash")

def getDownloadLinks(userPrompt):
    """Ask Gemini for research resource links (PDFs/articles)."""
    response = model.generate_content(f"You are a research assistant. Given the topic: {userPrompt}, "
                 f"provide ONLY a Python list of valid URLs (preferably PDFs or research articles). "
                 f"only valid download links"
                 f"Format: ['url1', 'url2', ...]"
    )

    raw_output = response.text.strip()
    print("Raw Gemini response:", raw_output)

    match = re.search(r"\[.*\]", raw_output, re.DOTALL)
    if not match:
        print("Could not find a list in the response.")
        return []

    try:
        links = ast.literal_eval(match.group(0))
    except Exception as e:
        print("Error parsing links:", e)
        return []

    return links


def download_pdf(url, filename="temp.pdf"):
    """Download a PDF file from a given URL."""
    try:
        response = requests.get(url, stream=True, timeout=15)
        if response.status_code == 200:
            with open(filename, "wb") as f:
                f.write(response.content)
            return filename
        else:
            print(f"Failed to download: {url}")
            return None
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return None


def extract_text_from_pdf(filename):
    """Extract all text from a PDF file."""
    text = ""
    try:
        reader = PdfReader(filename)
        for page in reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        print(f"Error reading {filename}: {e}")
    return text


def researchPipeline(userPrompt):
    links = getDownloadLinks(userPrompt)

    all_texts = []
    for i, link in enumerate(links, start=1):
        print(f"\n[{i}] Downloading: {link}")
        filename = f"doc_{i}.pdf"

        # Download
        file_path = download_pdf(link, filename)
        if not file_path:
            continue

        # Extract text
        text = extract_text_from_pdf(file_path)
        print(f"\nExtracted text from {filename}:\n{'-'*40}\n{text[:1000]}...\n")  # show first 1000 chars
        all_texts.append(text)

        # Cleanup
        os.remove(file_path)
        print(f"Deleted {filename}")

    return all_texts,links


"""     all_texts = researchPipeline(topic)
 """