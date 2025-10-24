import torch
import pandas as pd
from transformers import AutoTokenizer, AutoModelForSequenceClassification

class BERTAnalyzer:
    def __init__(self, model_path: str):
        """Initialize and load fine-tuned BERT model and tokenizer"""
        print("📦 Loading model and tokenizer...")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self.model.to(self.device)
        self.model.eval()

        print(f"✅ Model loaded successfully on {self.device}")
        print(f"📊 Number of classes: {self.model.config.num_labels}")

        # Label mapping (same as training order)
        self.label_mapping = {
            'future_work': 0,
            'limitation': 1,
            'method': 2,
            'normal': 3,
            'result': 4
        }
        self.id_to_label = {v: k for k, v in self.label_mapping.items()}

    def predict_batch(self, sentences: list):
        """Predict labels for a list of sentences"""
        if not sentences:
            return []

        # Tokenize input sentences
        encoded = self.tokenizer(
            sentences,
            truncation=True,
            padding=True,
            max_length=256,
            return_tensors="pt"
        ).to(self.device)

        # Run model inference
        with torch.no_grad():
            outputs = self.model(**encoded)
            logits = outputs.logits
            predictions = logits.argmax(-1).cpu().numpy()
            probabilities = torch.softmax(logits, dim=-1).cpu().numpy()

        # Format predictions
        results = []
        for sentence, pred, probs in zip(sentences, predictions, probabilities):
            pred_label = self.id_to_label[pred]
            confidence = probs[pred]
            label_probs = {self.id_to_label[i]: float(probs[i]) for i in range(len(probs))}

            results.append({
                "text": sentence,
                "predicted_label": pred_label,
                "confidence": round(confidence, 4),
                "probabilities": label_probs
            })

        return results

# ✅ Example usage (run only when file is executed directly)
if __name__ == "__main__":
    model_path = r"bert-finetuned-model\bert-finetuned-model"
    analyzer = BERTAnalyzer(model_path)

    test_sentences = [
        "We used a convolutional neural network to classify the MRI images.",
        "Our experiments achieved a 92% accuracy on the benchmark dataset.",
        "One limitation of our approach is the small sample size used in training.",
        "In future work, we plan to extend our model to multimodal datasets.",
        "The proposed algorithm outperformed baseline methods by 15%.",
        "However, the model struggles with out-of-distribution examples."
    ]

    results = analyzer.predict_batch(test_sentences)
    df = pd.DataFrame(results)
    print("\n📊 Prediction Results:\n", df[["text", "predicted_label", "confidence"]])
