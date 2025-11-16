import requests
import json
from PyPDF2 import PdfReader

# 🧠 Function to extract text from PDF
def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

# 📥 Ask user for PDF file path
pdf_path = input("Enter the path of your research paper PDF: ").strip()

# 📄 Extract text
print("\nExtracting text from PDF...")
try:
    pdf_text = extract_text_from_pdf(pdf_path)
except Exception as e:
    print(f"Error reading PDF: {e}")
    exit()

# ✂️ If PDF is long, truncate to fit Ollama context limit
pdf_text = pdf_text[:8000]  # You can adjust this if needed

# 🧩 Ollama API endpoint
url = "http://localhost:11434/api/generate"

# 💬 Prompt for Llama 3
prompt = f"""
You are an academic summarizer.
Analyze the following research paper and return the response strictly in JSON format with these keys:
{{
  "Title": "",
  "Methodology": "",
  "Results": "",
  "Conclusion": ""
}}

Here is the research paper text:
{pdf_text}
"""

# 📨 Request payload
data = {
    "model": "llama3",
    "prompt": prompt
}

# 🚀 Send request to Ollama
print("\nSending to Llama 3... Please wait.\n")
response = requests.post(url, json=data, stream=True)

# 📡 Read streamed response
output = ""
for line in response.iter_lines():
    if line:
        msg = json.loads(line)
        output += msg.get("response", "")

# 🧩 Try parsing as JSON
print("\n\n📊 Parsed Output:\n")
try:
    result_json = json.loads(output)
    print(json.dumps(result_json, indent=2))
except json.JSONDecodeError:
    print("⚠️ Model output is not perfect JSON. Showing raw text:\n")
    print(output)
