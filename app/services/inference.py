from __future__ import annotations

import asyncio
import hashlib
import shutil
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.core.circuit_breaker import (
    CircuitBreakerOpenError,
    get_circuit_breaker_registry,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.ticket import TicketCategory, TicketClassification, TicketPriority

logger = get_logger(__name__)

CATEGORY_LABELS = [
    "technical",
    "billing",
    "account",
    "general",
    "security",
    "feature_request",
    "bug_report",
]

PRIORITY_MAP = {
    "security": TicketPriority.CRITICAL,
    "bug_report": TicketPriority.HIGH,
    "technical": TicketPriority.HIGH,
    "billing": TicketPriority.HIGH,
    "account": TicketPriority.MEDIUM,
    "feature_request": TicketPriority.LOW,
    "general": TicketPriority.LOW,
}

SUBCATEGORY_MAP = {
    "technical": ["api", "integration", "performance", "configuration", "other"],
    "billing": ["invoice", "refund", "subscription", "payment_method", "other"],
    "account": ["login", "profile", "permissions", "deletion", "other"],
    "security": ["breach", "vulnerability", "access", "compliance", "other"],
    "bug_report": ["ui", "backend", "mobile", "api", "other"],
    "feature_request": ["ui", "backend", "api", "integration", "other"],
    "general": ["question", "feedback", "complaint", "other"],
}


class ModelDownloadError(Exception):
    pass


class InferenceService:
    def __init__(
        self,
        model_path: str,
        device: str = "cpu",
        max_batch_size: int = 32,
        timeout: float = 30.0,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.max_batch_size = max_batch_size
        self.timeout = timeout
        self.model: Any = None
        self.tokenizer: Any = None
        self.model_version: str = "unknown"
        self._initialized = False
        self._degraded_mode = False
        self._queue: asyncio.Queue[tuple[list[tuple[str, str]], asyncio.Future]] | None = None
        self._worker_task: asyncio.Task | None = None

        # Circuit breaker for model inference
        self._circuit_breaker = get_circuit_breaker_registry().get_or_create(
            "inference",
            failure_threshold=5,
            recovery_timeout=30.0,
            expected_exception=Exception,
        )

    @property
    def is_degraded(self) -> bool:
        return self._degraded_mode or self._circuit_breaker.state.name == "OPEN"

    async def initialize(self) -> None:
        if self._initialized:
            return

        settings = get_settings()
        path = Path(self.model_path)

        # Try to download model if configured and not present
        if not path.exists():
            await self._maybe_download_model(settings, path)

        if not path.exists():
            logger.warning(
                "model_path_not_found",
                path=str(path),
                fallback="using_dummy_classifier",
            )
            self._initialized = True
            self._degraded_mode = True
            self.model_version = "dummy-v1"
            return

        # Verify checksum if provided
        if settings.model_checksum:
            if not await self._verify_checksum(path, settings.model_checksum):
                logger.error("model_checksum_mismatch", path=str(path))
                self._initialized = True
                self._degraded_mode = True
                self.model_version = "dummy-v1"
                return

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(str(path))
            self.model = AutoModelForSequenceClassification.from_pretrained(
                str(path),
                torch_dtype=torch.float32,
            )
            self.model.to(self.device)
            self.model.eval()

            self.model_version = getattr(self.model.config, "_name_or_path", "distilbert-v1")

            self._queue = asyncio.Queue(maxsize=100)
            self._worker_task = asyncio.create_task(self._batch_worker())

            self._initialized = True
            logger.info(
                "model_loaded",
                model_path=str(path),
                device=self.device,
                version=self.model_version,
            )
        except Exception as e:
            logger.exception("model_load_failed", error=str(e))
            self._initialized = True
            self._degraded_mode = True
            self.model_version = "dummy-v1"

    async def _maybe_download_model(self, settings, path: Path) -> None:
        """Download model from S3 or GCS if configured."""
        if settings.model_s3_bucket and settings.model_s3_key:
            await self._download_from_s3(settings, path)
        elif settings.model_gcs_bucket and settings.model_gcs_path:
            await self._download_from_gcs(settings, path)
        else:
            logger.info("no_model_download_configured", path=str(path))

    async def _download_from_s3(self, settings, path: Path) -> None:
        """Download model from S3 using boto3."""
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            logger.warning("boto3_not_installed_skipping_s3_download")
            return

        logger.info(
            "downloading_model_from_s3",
            bucket=settings.model_s3_bucket,
            key=settings.model_s3_key,
        )

        s3 = boto3.client("s3", config=Config(retries={"max_attempts": 3}))
        path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "model.tar.gz"
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        s3.download_file,
                        settings.model_s3_bucket,
                        settings.model_s3_key,
                        str(tmp_path),
                    ),
                    timeout=settings.model_download_timeout,
                )
                await self._extract_model(tmp_path, path)
                logger.info("model_downloaded_from_s3", path=str(path))
            except TimeoutError:
                raise ModelDownloadError("S3 download timeout") from None
            except Exception as e:
                raise ModelDownloadError(f"S3 download failed: {e}") from e

    async def _download_from_gcs(self, settings, path: Path) -> None:
        """Download model from GCS using google-cloud-storage."""
        try:
            from google.cloud import storage
        except ImportError:
            logger.warning("google-cloud-storage_not_installed_skipping_gcs_download")
            return

        logger.info(
            "downloading_model_from_gcs",
            bucket=settings.model_gcs_bucket,
            path=settings.model_gcs_path,
        )

        client = storage.Client()
        bucket = client.bucket(settings.model_gcs_bucket)
        blob = bucket.blob(settings.model_gcs_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "model.tar.gz"
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(blob.download_to_filename, str(tmp_path)),
                    timeout=settings.model_download_timeout,
                )
                await self._extract_model(tmp_path, path)
                logger.info("model_downloaded_from_gcs", path=str(path))
            except TimeoutError:
                raise ModelDownloadError("GCS download timeout") from None
            except Exception as e:
                raise ModelDownloadError(f"GCS download failed: {e}") from e

    async def _extract_model(self, archive_path: Path, dest_path: Path) -> None:
        """Extract model archive (tar.gz or zip)."""
        import tarfile
        import zipfile

        if tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(dest_path)
        elif zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zipf:
                zipf.extractall(dest_path)
        else:
            # Assume it's a directory copy
            shutil.copytree(archive_path, dest_path, dirs_exist_ok=True)

    async def _verify_checksum(self, path: Path, expected_checksum: str) -> bool:
        """Verify SHA256 checksum of model directory."""
        sha256 = hashlib.sha256()
        for file_path in sorted(path.rglob("*")):
            if file_path.is_file():
                content = file_path.read_bytes()
                sha256.update(content)
        actual = sha256.hexdigest()
        if actual != expected_checksum:
            logger.error("checksum_mismatch", expected=expected_checksum, actual=actual)
            return False
        logger.info("checksum_verified", checksum=actual)
        return True

    async def _batch_worker(self) -> None:
        while True:
            try:
                batch, future = await self._queue.get()
                if not batch:
                    break

                try:
                    results = await self._predict_batch(batch)
                    future.set_result(results)
                except Exception as e:
                    future.set_exception(e)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("batch_worker_error", error=str(e))

    async def _predict_batch(self, items: list[tuple[str, str]]) -> list[TicketClassification]:
        if self.model is None or self.tokenizer is None:
            return [self._dummy_classify(subject, body) for subject, body in items]

        texts = [f"{subject} {body}" for subject, body in items]

        inputs = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
            predictions = torch.argmax(probs, dim=-1)
            confidences = torch.max(probs, dim=-1).values

        results = []
        for pred, conf in zip(predictions.cpu().tolist(), confidences.cpu().tolist(), strict=True):
            category = TicketCategory(CATEGORY_LABELS[pred])
            priority = PRIORITY_MAP.get(category.value, TicketPriority.MEDIUM)
            subcategories = SUBCATEGORY_MAP.get(category.value, ["other"])

            results.append(
                TicketClassification(
                    category=category,
                    confidence=conf,
                    subcategory=subcategories[0],
                    priority=priority,
                    suggested_team="",
                    tags=[category.value],
                )
            )

        return results

    def _dummy_classify(self, subject: str, body: str) -> TicketClassification:
        text = (subject + " " + body).lower()

        if any(kw in text for kw in ["security", "breach", "hack", "vulnerability", "exploit"]):
            category = TicketCategory.SECURITY
        elif any(kw in text for kw in ["bug", "error", "crash", "broken", "not working", "fail"]):
            category = TicketCategory.BUG_REPORT
        elif any(kw in text for kw in ["bill", "invoice", "charge", "refund", "payment", "subscription"]):
            category = TicketCategory.BILLING
        elif any(kw in text for kw in ["account", "login", "password", "profile", "access"]):
            category = TicketCategory.ACCOUNT
        elif any(kw in text for kw in ["feature", "request", "suggestion", "enhancement", "add"]):
            category = TicketCategory.FEATURE_REQUEST
        elif any(kw in text for kw in ["api", "integration", "sdk", "webhook", "endpoint"]):
            category = TicketCategory.TECHNICAL
        else:
            category = TicketCategory.GENERAL

        priority = PRIORITY_MAP.get(category.value, TicketPriority.MEDIUM)
        subcategories = SUBCATEGORY_MAP.get(category.value, ["other"])

        return TicketClassification(
            category=category,
            confidence=0.85,
            subcategory=subcategories[0],
            priority=priority,
            suggested_team="",
            tags=[category.value],
        )

    async def _classify_with_circuit_breaker(self, subject: str, body: str) -> TicketClassification:
        async def _do_classify() -> TicketClassification:
            if self._queue is None:
                return self._dummy_classify(subject, body)

            future: asyncio.Future = asyncio.get_event_loop().create_future()
            await self._queue.put(([(subject, body)], future))

            try:
                results = await asyncio.wait_for(future, timeout=self.timeout)
                return results[0]
            except TimeoutError:
                future.cancel()
                raise TimeoutError("Inference timeout")

        try:
            return await self._circuit_breaker.call(_do_classify)
        except CircuitBreakerOpenError:
            logger.warning("circuit_breaker_open_fallback", subject=subject[:50])
            return self._dummy_classify(subject, body)

    async def classify(self, subject: str, body: str) -> TicketClassification:
        if not self._initialized:
            await self.initialize()

        return await self._classify_with_circuit_breaker(subject, body)

    async def _classify_batch_with_circuit_breaker(self, items: list[tuple[str, str]]) -> list[TicketClassification]:
        async def _do_classify_batch() -> list[TicketClassification]:
            if self._queue is None:
                return [self._dummy_classify(s, b) for s, b in items]

            batches = [items[i : i + self.max_batch_size] for i in range(0, len(items), self.max_batch_size)]
            all_results = []

            for batch in batches:
                future: asyncio.Future = asyncio.get_event_loop().create_future()
                await self._queue.put((batch, future))
                try:
                    results = await asyncio.wait_for(future, timeout=self.timeout)
                    all_results.extend(results)
                except TimeoutError:
                    future.cancel()
                    raise TimeoutError("Batch inference timeout")

            return all_results

        try:
            return await self._circuit_breaker.call(_do_classify_batch)
        except CircuitBreakerOpenError:
            logger.warning("circuit_breaker_open_fallback_batch", batch_size=len(items))
            return [self._dummy_classify(s, b) for s, b in items]

    async def classify_batch(self, items: list[tuple[str, str]]) -> list[TicketClassification]:
        if not self._initialized:
            await self.initialize()

        return await self._classify_batch_with_circuit_breaker(items)

    async def health_check(self) -> bool:
        if not self._initialized:
            return False
        if self.model is None:
            return True
        try:
            _ = await self.classify("test", "health check")
            return True
        except Exception:
            return False

    async def shutdown(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker_task
        if self._queue:
            await self._queue.put(([], None))
