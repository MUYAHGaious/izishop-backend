"""
Universal Batch System for IziShop
Provides a unified interface for batch operations across all entities
"""

import asyncio
import logging
from typing import List, Dict, Any, Callable, Optional, Union, TypeVar, Generic
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

T = TypeVar('T')

class BatchStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_COMPLETED = "partially_completed"

class BatchOperationType(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    BULK_UPDATE = "bulk_update"
    CUSTOM = "custom"

@dataclass
class BatchItem:
    """Individual item in a batch operation"""
    id: str
    data: Dict[str, Any]
    status: BatchStatus = BatchStatus.PENDING
    error: Optional[str] = None
    result: Optional[Any] = None
    retry_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None

@dataclass
class BatchConfig:
    """Configuration for batch operations"""
    batch_size: int = 100
    max_retries: int = 3
    retry_delay: float = 1.0  # seconds
    timeout: float = 300.0  # 5 minutes
    parallel_workers: int = 5
    fail_fast: bool = False  # Stop on first error
    validate_before_process: bool = True
    auto_cleanup: bool = True
    cleanup_after_hours: int = 24

@dataclass
class BatchResult:
    """Result of a batch operation"""
    batch_id: str
    total_items: int
    successful: int
    failed: int
    skipped: int
    status: BatchStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration: Optional[float] = None
    errors: List[Dict[str, Any]] = field(default_factory=list)
    results: List[Any] = field(default_factory=list)

class BatchProcessor(ABC, Generic[T]):
    """Abstract base class for batch processors"""
    
    @abstractmethod
    async def validate_item(self, item: BatchItem) -> bool:
        """Validate a single batch item"""
        pass
    
    @abstractmethod
    async def process_item(self, item: BatchItem) -> Any:
        """Process a single batch item"""
        pass
    
    async def pre_process_hook(self, batch_items: List[BatchItem]) -> None:
        """Hook called before processing batch"""
        pass
    
    async def post_process_hook(self, batch_result: BatchResult) -> None:
        """Hook called after processing batch"""
        pass
    
    async def error_handler(self, item: BatchItem, error: Exception) -> bool:
        """Handle errors during processing. Return True to retry, False to skip"""
        logger.error(f"Error processing batch item {item.id}: {str(error)}")
        return item.retry_count < 3  # Default retry logic

class UniversalBatchSystem:
    """Universal batch processing system"""
    
    def __init__(self, db: Session, config: Optional[BatchConfig] = None):
        self.db = db
        self.config = config or BatchConfig()
        self.active_batches: Dict[str, BatchResult] = {}
        self._batch_storage: Dict[str, List[BatchItem]] = {}
        
    async def create_batch(
        self, 
        items: List[Dict[str, Any]], 
        processor: BatchProcessor,
        operation_type: BatchOperationType = BatchOperationType.CUSTOM,
        batch_id: Optional[str] = None
    ) -> str:
        """Create a new batch for processing"""
        
        if not batch_id:
            batch_id = f"batch_{operation_type.value}_{datetime.utcnow().timestamp()}"
        
        # Convert items to BatchItem objects
        batch_items = []
        for i, item_data in enumerate(items):
            batch_item = BatchItem(
                id=f"{batch_id}_item_{i}",
                data=item_data
            )
            batch_items.append(batch_item)
        
        # Store batch items
        self._batch_storage[batch_id] = batch_items
        
        # Initialize batch result
        batch_result = BatchResult(
            batch_id=batch_id,
            total_items=len(batch_items),
            successful=0,
            failed=0,
            skipped=0,
            status=BatchStatus.PENDING,
            started_at=datetime.utcnow()
        )
        
        self.active_batches[batch_id] = batch_result
        
        logger.info(f"Created batch {batch_id} with {len(batch_items)} items")
        return batch_id
    
    async def process_batch(
        self, 
        batch_id: str, 
        processor: BatchProcessor
    ) -> BatchResult:
        """Process a batch using the provided processor"""
        
        if batch_id not in self._batch_storage:
            raise ValueError(f"Batch {batch_id} not found")
        
        batch_items = self._batch_storage[batch_id]
        batch_result = self.active_batches[batch_id]
        
        batch_result.status = BatchStatus.PROCESSING
        
        try:
            # Pre-process hook
            await processor.pre_process_hook(batch_items)
            
            # Validate items if required
            if self.config.validate_before_process:
                await self._validate_batch_items(batch_items, processor)
            
            # Process items in chunks
            await self._process_batch_chunks(batch_items, processor, batch_result)
            
            # Update final status
            if batch_result.failed > 0 and batch_result.successful == 0:
                batch_result.status = BatchStatus.FAILED
            elif batch_result.failed > 0:
                batch_result.status = BatchStatus.PARTIALLY_COMPLETED
            else:
                batch_result.status = BatchStatus.COMPLETED
            
            batch_result.completed_at = datetime.utcnow()
            batch_result.duration = (batch_result.completed_at - batch_result.started_at).total_seconds()
            
            # Post-process hook
            await processor.post_process_hook(batch_result)
            
            logger.info(f"Batch {batch_id} completed: {batch_result.successful} successful, {batch_result.failed} failed")
            
        except Exception as e:
            batch_result.status = BatchStatus.FAILED
            batch_result.errors.append({
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
            logger.error(f"Batch {batch_id} failed: {str(e)}")
        
        finally:
            # Auto cleanup if enabled
            if self.config.auto_cleanup:
                asyncio.create_task(self._schedule_cleanup(batch_id))
        
        return batch_result
    
    async def _validate_batch_items(self, items: List[BatchItem], processor: BatchProcessor):
        """Validate all batch items"""
        for item in items:
            try:
                is_valid = await processor.validate_item(item)
                if not is_valid:
                    item.status = BatchStatus.FAILED
                    item.error = "Validation failed"
            except Exception as e:
                item.status = BatchStatus.FAILED
                item.error = f"Validation error: {str(e)}"
    
    async def _process_batch_chunks(
        self, 
        items: List[BatchItem], 
        processor: BatchProcessor, 
        batch_result: BatchResult
    ):
        """Process batch items in chunks with parallel workers"""
        
        # Filter out already failed items
        valid_items = [item for item in items if item.status != BatchStatus.FAILED]
        
        # Process in chunks
        for i in range(0, len(valid_items), self.config.batch_size):
            chunk = valid_items[i:i + self.config.batch_size]
            
            # Create semaphore to limit concurrent workers
            semaphore = asyncio.Semaphore(self.config.parallel_workers)
            
            # Process chunk with parallel workers
            tasks = [
                self._process_single_item(item, processor, semaphore, batch_result)
                for item in chunk
            ]
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check fail_fast condition
            if self.config.fail_fast and batch_result.failed > 0:
                break
    
    async def _process_single_item(
        self, 
        item: BatchItem, 
        processor: BatchProcessor, 
        semaphore: asyncio.Semaphore,
        batch_result: BatchResult
    ):
        """Process a single batch item with retry logic"""
        async with semaphore:
            max_retries = self.config.max_retries
            
            while item.retry_count <= max_retries:
                try:
                    # Add timeout
                    result = await asyncio.wait_for(
                        processor.process_item(item), 
                        timeout=self.config.timeout
                    )
                    
                    item.result = result
                    item.status = BatchStatus.COMPLETED
                    item.processed_at = datetime.utcnow()
                    
                    batch_result.successful += 1
                    batch_result.results.append(result)
                    
                    logger.debug(f"Successfully processed item {item.id}")
                    break
                    
                except Exception as e:
                    item.retry_count += 1
                    
                    # Let processor handle the error
                    should_retry = await processor.error_handler(item, e)
                    
                    if should_retry and item.retry_count <= max_retries:
                        logger.warning(f"Retrying item {item.id} (attempt {item.retry_count})")
                        await asyncio.sleep(self.config.retry_delay * item.retry_count)  # Exponential backoff
                        continue
                    else:
                        item.status = BatchStatus.FAILED
                        item.error = str(e)
                        item.processed_at = datetime.utcnow()
                        
                        batch_result.failed += 1
                        batch_result.errors.append({
                            "item_id": item.id,
                            "error": str(e),
                            "retry_count": item.retry_count,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        
                        logger.error(f"Failed to process item {item.id}: {str(e)}")
                        break
    
    async def get_batch_status(self, batch_id: str) -> Optional[BatchResult]:
        """Get the status of a batch"""
        return self.active_batches.get(batch_id)
    
    async def cancel_batch(self, batch_id: str) -> bool:
        """Cancel a pending or processing batch"""
        if batch_id in self.active_batches:
            batch_result = self.active_batches[batch_id]
            if batch_result.status in [BatchStatus.PENDING, BatchStatus.PROCESSING]:
                batch_result.status = BatchStatus.FAILED
                batch_result.completed_at = datetime.utcnow()
                return True
        return False
    
    async def _schedule_cleanup(self, batch_id: str):
        """Schedule cleanup of batch data"""
        cleanup_delay = self.config.cleanup_after_hours * 3600  # Convert to seconds
        await asyncio.sleep(cleanup_delay)
        
        # Remove from storage
        if batch_id in self._batch_storage:
            del self._batch_storage[batch_id]
        if batch_id in self.active_batches:
            del self.active_batches[batch_id]
        
        logger.info(f"Cleaned up batch {batch_id}")
    
    async def cleanup_old_batches(self, older_than_hours: int = 24):
        """Manually cleanup old batches"""
        cutoff_time = datetime.utcnow() - timedelta(hours=older_than_hours)
        
        batches_to_remove = []
        for batch_id, batch_result in self.active_batches.items():
            if batch_result.completed_at and batch_result.completed_at < cutoff_time:
                batches_to_remove.append(batch_id)
        
        for batch_id in batches_to_remove:
            if batch_id in self._batch_storage:
                del self._batch_storage[batch_id]
            if batch_id in self.active_batches:
                del self.active_batches[batch_id]
        
        logger.info(f"Cleaned up {len(batches_to_remove)} old batches")
        return len(batches_to_remove)

# Utility function to create batch system instance
def create_batch_system(db: Session, **config_kwargs) -> UniversalBatchSystem:
    """Create a batch system with optional configuration overrides"""
    config = BatchConfig(**config_kwargs)
    return UniversalBatchSystem(db, config)