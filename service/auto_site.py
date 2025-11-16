import re

def auto_cite_paragraph(paragraph: str, references: dict) -> str:
    """
    Automatically adds reference tags [id] in the paragraph
    where keywords from the reference list are found.

    Args:
        paragraph (str): Text paragraph.
        references (dict): {ref_id: [keywords, ...]}

    Returns:
        str: Paragraph with inserted [id] citations.
    """
    cited_text = paragraph
    for ref_id, keywords in references.items():
        for kw in keywords:
            pattern = re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
            cited_text = re.sub(pattern, f"{kw}[{ref_id}]", cited_text)
    return cited_text
