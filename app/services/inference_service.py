"""ML inference service."""
import time
import logging
import joblib
from typing import Dict, Tuple, Optional
import asyncio
from pathlib import Path

from app.core.config import settings
from app.core.metrics import model_load_duration_seconds, model_inference_batch_size
from app.utils.hashing import normalize_text

logger = logging.getLogger(__name__)


class InferenceService:
    """ML inference service with model loading and prediction."""

    def __init__(self):
        """Initialize inference service."""
        self.model = None
        self.vectorizer = None
        self.label_names = ["negative", "neutral", "positive"]
        self.model_loaded = False

    async def load_model(self) -> None:
        """Load ML model from disk."""
        start_time = time.time()
        
        try:
            model_path = Path(settings.model_path)
            
            if not model_path.exists():
                logger.warning(
                    f"Model file not found at {model_path}, will create dummy model"
                )
                await self._create_dummy_model()
            else:
                # Load the model
                model_data = await asyncio.to_thread(joblib.load, str(model_path))
                self.model = model_data["model"]
                self.vectorizer = model_data["vectorizer"]
                self.label_names = model_data.get("label_names", self.label_names)
                
                logger.info(
                    f"Model loaded successfully from {model_path}",
                    extra={
                        "model_path": str(model_path),
                        "label_names": self.label_names,
                    },
                )
            
            self.model_loaded = True
            
            load_duration = time.time() - start_time
            model_load_duration_seconds.labels(
                worker_id=settings.worker_id
            ).set(load_duration)
            
            logger.info(
                f"Model loading completed in {load_duration:.2f}s",
                extra={"load_duration_seconds": load_duration},
            )
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            # Create dummy model as fallback
            await self._create_dummy_model()
            self.model_loaded = True

    async def _create_dummy_model(self) -> None:
        """Create a dummy model for demonstration."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        import numpy as np
        
        logger.info("Creating dummy model for demonstration")
        
        # Create simple training data
        texts = [
            "this is great awesome amazing",
            "terrible bad worst horrible",
            "okay fine average normal",
        ]
        labels = [2, 0, 1]  # positive, negative, neutral
        
        # Create vectorizer and model
        self.vectorizer = TfidfVectorizer(max_features=100)
        X = await asyncio.to_thread(self.vectorizer.fit_transform, texts)
        
        self.model = LogisticRegression(random_state=42)
        await asyncio.to_thread(self.model.fit, X, labels)
        
        logger.info("Dummy model created successfully")

    async def predict(
        self,
        text: str,
        batch_size: int = 1,
    ) -> Tuple[str, float, Dict[str, float]]:
        """
        Make prediction on input text.
        
        Args:
            text: Input text to classify
            batch_size: Batch size for inference (for metrics)
            
        Returns:
            Tuple of (prediction, confidence, probabilities_dict)
        """
        if not self.model_loaded:
            raise RuntimeError("Model not loaded")
        
        try:
            # Normalize text
            normalized_text = normalize_text(text)
            
            # Vectorize
            start_time = time.time()
            X = await asyncio.to_thread(
                self.vectorizer.transform,
                [normalized_text],
            )
            
            # Predict
            prediction_idx = await asyncio.to_thread(self.model.predict, X)
            probabilities = await asyncio.to_thread(self.model.predict_proba, X)
            
            inference_time = time.time() - start_time
            
            # Extract results
            pred_label = self.label_names[prediction_idx[0]]
            pred_confidence = float(probabilities[0][prediction_idx[0]])
            
            # Build probabilities dict
            prob_dict = {
                label: float(prob)
                for label, prob in zip(self.label_names, probabilities[0])
            }
            
            # Update metrics
            model_inference_batch_size.labels(
                worker_id=settings.worker_id
            ).observe(batch_size)
            
            logger.debug(
                f"Inference completed in {inference_time*1000:.2f}ms",
                extra={
                    "inference_time_ms": inference_time * 1000,
                    "prediction": pred_label,
                    "confidence": pred_confidence,
                },
            )
            
            return pred_label, pred_confidence, prob_dict
            
        except Exception as e:
            logger.error(f"Inference failed: {e}", extra={"text_length": len(text)})
            raise

    async def health_check(self) -> bool:
        """Check if model is loaded and ready."""
        return self.model_loaded


# Global instance
inference_service = InferenceService()
