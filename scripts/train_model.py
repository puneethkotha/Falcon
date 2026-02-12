"""Train a simple sentiment classifier for demo purposes."""
import joblib
import numpy as np
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score


def generate_training_data():
    """Generate synthetic training data."""
    np.random.seed(42)
    
    # Positive examples
    positive_words = [
        "great", "excellent", "amazing", "wonderful", "fantastic",
        "awesome", "love", "best", "perfect", "outstanding",
        "brilliant", "superb", "terrific", "exceptional", "impressive",
    ]
    
    # Negative examples
    negative_words = [
        "terrible", "awful", "horrible", "worst", "bad",
        "disappointing", "poor", "useless", "hate", "disgusting",
        "pathetic", "garbage", "rubbish", "dreadful", "appalling",
    ]
    
    # Neutral examples
    neutral_words = [
        "okay", "fine", "average", "normal", "standard",
        "typical", "regular", "ordinary", "moderate", "fair",
        "acceptable", "adequate", "reasonable", "decent", "passable",
    ]
    
    texts = []
    labels = []
    
    # Generate positive examples
    for _ in range(200):
        words = np.random.choice(positive_words, size=np.random.randint(3, 8))
        text = " ".join(words) + " product service experience"
        texts.append(text)
        labels.append(2)  # positive
    
    # Generate negative examples
    for _ in range(200):
        words = np.random.choice(negative_words, size=np.random.randint(3, 8))
        text = " ".join(words) + " product service experience"
        texts.append(text)
        labels.append(0)  # negative
    
    # Generate neutral examples
    for _ in range(200):
        words = np.random.choice(neutral_words, size=np.random.randint(3, 8))
        text = " ".join(words) + " product service experience"
        texts.append(text)
        labels.append(1)  # neutral
    
    return texts, labels


def main():
    """Train and save the model."""
    print("Generating training data...")
    texts, labels = generate_training_data()
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )
    
    print(f"Training set: {len(X_train)} samples")
    print(f"Test set: {len(X_test)} samples")
    
    # Create vectorizer
    print("\nTraining TF-IDF vectorizer...")
    vectorizer = TfidfVectorizer(
        max_features=500,
        ngram_range=(1, 2),
        min_df=2,
    )
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)
    
    # Train classifier
    print("Training logistic regression classifier...")
    model = LogisticRegression(
        random_state=42,
        max_iter=1000,
        C=1.0,
        solver='lbfgs',
    )
    model.fit(X_train_vec, y_train)
    
    # Evaluate
    y_pred = model.predict(X_test_vec)
    accuracy = accuracy_score(y_test, y_pred)
    
    print(f"\n{'='*60}")
    print(f"Model Accuracy: {accuracy:.4f}")
    print(f"{'='*60}")
    
    label_names = ["negative", "neutral", "positive"]
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=label_names))
    
    # Save model
    output_dir = Path(__file__).parent.parent / "models"
    output_dir.mkdir(exist_ok=True)
    
    model_path = output_dir / "classifier.pkl"
    
    model_data = {
        "model": model,
        "vectorizer": vectorizer,
        "label_names": label_names,
    }
    
    print(f"\nSaving model to {model_path}...")
    joblib.dump(model_data, model_path)
    
    # Test a few examples
    print("\n" + "="*60)
    print("Test Predictions:")
    print("="*60)
    
    test_examples = [
        "This is an amazing product! I love it!",
        "Terrible quality, very disappointed",
        "It's okay, nothing special",
        "Absolutely fantastic experience",
        "Worst purchase ever, complete garbage",
    ]
    
    for text in test_examples:
        X_example = vectorizer.transform([text])
        pred_idx = model.predict(X_example)[0]
        proba = model.predict_proba(X_example)[0]
        
        print(f"\nText: {text}")
        print(f"Prediction: {label_names[pred_idx]}")
        print(f"Confidence: {proba[pred_idx]:.4f}")
        print(f"Probabilities: {dict(zip(label_names, proba))}")
    
    print("\n" + "="*60)
    print("Model training complete!")
    print("="*60)


if __name__ == "__main__":
    main()
