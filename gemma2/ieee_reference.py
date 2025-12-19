import re
from flask import jsonify
from ollama import chat  # using Ollama’s Llama 3

def generate_ieee_reference_for_doc(current_user, doc_id):
    """
    Fetch a single document by ID, extract metadata portion,
    and generate IEEE-style reference using Llama 3.
    """
    from app.models import Document  # Import inside function to avoid circular import

    # Fetch specific document
    doc = Document.query.filter_by(user_id=current_user.id, doc_id=doc_id).first()

    if not doc:
        return jsonify({"message": "Document not found"}), 404

    # Take the first 200 words assuming title/author are here
    text = doc.content or ""
    first_part = " ".join(text.split()[:200])

    # LLM prompt for IEEE formatting
    prompt = f"""
    You are a reference formatting assistant.
    Extract bibliographic details and create an IEEE-style citation.
    The citation must follow IEEE format like:
    [1] A. Author, B. Author, “Paper Title,” Journal/Conference Name, vol., no., pages, year.

    Text snippet:
    {first_part}

    Output strictly as JSON:
    {{
        "reference": "formatted_reference_here"
    }}
    """

    try:
        response = chat(
            model="llama3",
            messages=[
                {"role": "system", "content": "You are a research paper reference formatter."},
                {"role": "user", "content": prompt}
            ],
            format="json"
        )

        ieee_ref = response["message"]["content"]
        return jsonify({
            "message": "Success",
            "doc_id": str(doc_id),
            "reference": ieee_ref
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"message": f"Error generating reference: {str(e)}"}), 500
