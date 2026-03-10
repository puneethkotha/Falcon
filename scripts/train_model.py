"""Train a high-precision sentiment classifier."""
import joblib
import numpy as np
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix


def get_curated_data():
    """Curated sentiment examples for high precision on problem cases."""
    positive = [
        "This is amazing", "Absolutely fantastic", "I love it", "Best product ever",
        "Excellent quality", "Wonderful experience", "Highly recommend", "Outstanding service",
        "Great product", "Perfect", "Awesome", "Brilliant", "Superb", "Terrific",
        "Exceeded my expectations", "Could not be happier", "Top notch", "Impeccable",
        "This product is great", "Quality is excellent", "Very satisfied", "Love this",
        "Amazing product", "Fantastic service", "Best purchase", "Highly satisfied",
        "Great value", "Wonderful product", "Excellent experience", "Outstanding quality",
        "I am very happy", "Really good", "So good", "Very good", "Pretty good",
        "This is a great product and I am very satisfied with the quality and service",
    ]

    negative = [
        "This is disgusting", "Absolutely terrible", "I hate it", "Worst product ever",
        "Poor quality", "Awful experience", "Do not recommend", "Dreadful service",
        "Terrible product", "Useless", "Garbage", "Rubbish", "Pathetic", "Appalling",
        "Complete waste of money", "Very disappointed", "Total junk", "Broken",
        "This product is bad", "Quality is poor", "Very unsatisfied", "Hate this",
        "Disgusting product", "Horrible service", "Worst purchase", "Completely disappointed",
        "Waste of money", "Terrible experience", "Awful quality", "Dreadful",
        "I am very unhappy", "Really bad", "So bad", "Very bad", "Pretty bad",
        "Disgusting", "Terrible", "Awful", "Horrible", "Worst", "Garbage", "Useless",
        "This is terrible and I want my money back", "Complete garbage do not buy",
    ]

    neutral = [
        "It is okay", "Nothing special", "Average product", "It is fine",
        "Normal quality", "Standard experience", "Nothing to write home about",
        "Meets expectations", "Decent", "Acceptable", "Adequate", "Reasonable",
        "So so", "Alright", "Fair", "Moderate", "Ordinary", "Typical",
        "This product is okay", "Quality is average", "Neither good nor bad",
        "Just okay product", "Average service", "Average purchase", "Neutral",
        "It does the job", "Gets the job done", "Nothing exceptional", "Run of the mill",
        "I have no strong feelings", "It is what it is", "Middle of the road",
        "Okay", "Fine", "Average", "Decent", "Alright", "Acceptable",
        "It is okay nothing special but does the job",
    ]

    # Negations and edge cases
    positive += [
        "Not bad at all", "Better than expected", "Surprisingly good",
        "Not terrible", "Could be worse but actually good",
    ]
    negative += [
        "Not good", "Not great", "Far from excellent", "Nothing to recommend",
        "Could be better but it is not", "Not worth it",
    ]
    neutral += [
        "Not good not bad", "Neither great nor terrible", "Mixed feelings",
        "Some good some bad", "It has its pros and cons",
    ]

    return positive, negative, neutral


def generate_training_data(n_per_class=400):
    """Generate training data with curated seeds and augmented examples."""
    pos_seeds, neg_seeds, neu_seeds = get_curated_data()

    np.random.seed(42)
    texts = []
    labels = []

    # Strong sentiment words for augmentation
    pos_words = ["great", "excellent", "amazing", "love", "best", "good", "fantastic", "wonderful", "perfect", "outstanding", "awesome", "brilliant", "recommend", "happy", "satisfied"]
    neg_words = ["terrible", "awful", "horrible", "worst", "bad", "hate", "poor", "disgusting", "useless", "garbage", "rubbish", "dreadful", "pathetic", "disappointing", "broken", "waste"]
    neu_words = ["okay", "fine", "average", "normal", "standard", "typical", "ordinary", "moderate", "fair", "acceptable", "adequate", "decent"]

    def augment(seeds, words, n, label):
        result = []
        for _ in range(n):
            if np.random.random() < 0.4 and seeds:
                text = np.random.choice(seeds)
            else:
                k = np.random.randint(2, 6)
                w = np.random.choice(words, size=k)
                suffix = np.random.choice([" product", " service", " experience", "", " purchase"])
                text = " ".join(w) + suffix
            result.append((text.strip(), label))
        return result

    for text, label in augment(pos_seeds, pos_words, n_per_class, 2):
        texts.append(text)
        labels.append(label)
    for text, label in augment(neg_seeds, neg_words, n_per_class, 0):
        texts.append(text)
        labels.append(label)
    for text, label in augment(neu_seeds, neu_words, n_per_class, 1):
        texts.append(text)
        labels.append(label)

    return texts, labels


def main():
    """Train and save the model."""
    print("Generating training data...")
    texts, labels = generate_training_data()

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    print(f"Training set: {len(X_train)} samples")
    print(f"Test set: {len(X_test)} samples")

    print("\nTraining TF-IDF vectorizer...")
    vectorizer = TfidfVectorizer(
        max_features=2000,
        ngram_range=(1, 3),
        min_df=1,
        sublinear_tf=True,
        strip_accents="unicode",
    )
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)

    print("Training logistic regression classifier...")
    model = LogisticRegression(
        random_state=42,
        max_iter=2000,
        C=2.0,
        solver="lbfgs",
        class_weight="balanced",
    )
    model.fit(X_train_vec, y_train)

    y_pred = model.predict(X_test_vec)
    accuracy = accuracy_score(y_test, y_pred)

    print(f"\n{'='*60}")
    print(f"Model Accuracy: {accuracy:.4f}")
    print(f"{'='*60}")

    label_names = ["negative", "neutral", "positive"]
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=label_names))

    print("\nConfusion Matrix:")
    print(confusion_matrix(y_test, y_pred, labels=[0, 1, 2]))

    scores = cross_val_score(model, X_train_vec, y_train, cv=3)
    print(f"\nCross-validation: {scores.mean():.4f} (+/- {scores.std()*2:.4f})")

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

    print("\n" + "="*60)
    print("Test Predictions (problem cases):")
    print("="*60)

    test_examples = [
        "disgusting",
        "This is disgusting",
        "amazing",
        "This is amazing",
        "terrible",
        "Terrible quality, very disappointed",
        "It's okay, nothing special",
        "Absolutely fantastic experience",
        "Worst purchase ever, complete garbage",
        "Not bad at all",
        "Not good",
        "Useless product",
        "Excellent service",
    ]

    for text in test_examples:
        X_example = vectorizer.transform([text.lower().strip()])
        pred_idx = model.predict(X_example)[0]
        proba = model.predict_proba(X_example)[0]

        print(f"\nText: {text}")
        print(f"Prediction: {label_names[pred_idx]} (conf: {proba[pred_idx]:.3f})")
        print(f"Probs: neg={proba[0]:.2f} neu={proba[1]:.2f} pos={proba[2]:.2f}")

    print("\n" + "="*60)
    print("Model training complete!")
    print("="*60)


if __name__ == "__main__":
    main()
