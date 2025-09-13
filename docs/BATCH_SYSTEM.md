# Universal Batch System Documentation

## Overview

The Universal Batch System provides a unified interface for batch processing operations across all entities in IziShop. It supports parallel processing, retry logic, validation, error handling, and monitoring.

## Architecture

### Core Components

1. **UniversalBatchSystem**: Main batch processing engine
2. **BatchProcessor**: Abstract base class for entity-specific processors
3. **BatchItem**: Individual item in a batch operation  
4. **BatchConfig**: Configuration options for batch processing
5. **BatchResult**: Result of a batch operation

### File Structure

```
backend/
├── core/
│   ├── batch_system.py              # Core batch processing engine
│   └── batch_processors/            # Entity-specific processors
│       ├── __init__.py
│       ├── notification_batch.py    # Notification operations
│       └── product_batch.py         # Product operations
├── routers/
│   └── batch_operations.py         # API endpoints
├── examples/
│   └── batch_system_usage.py       # Usage examples
└── docs/
    └── BATCH_SYSTEM.md             # This documentation
```

## Features

### ✅ Parallel Processing
- Configurable number of parallel workers
- Automatic load balancing
- Semaphore-based concurrency control

### ✅ Error Handling & Retries
- Configurable retry logic with exponential backoff
- Custom error handlers per processor
- Detailed error reporting

### ✅ Validation
- Pre-processing validation
- Entity-specific validation rules
- Fail-fast or continue-on-error modes

### ✅ Monitoring & Logging
- Real-time progress tracking
- Comprehensive logging
- Batch status monitoring

### ✅ Configuration
- Flexible configuration options
- Per-operation customization
- Default settings with overrides

## Basic Usage

### 1. Import the System

```python
from core.batch_system import create_batch_system, BatchConfig
from core.batch_processors.notification_batch import batch_create_notifications
```

### 2. Simple Batch Operation

```python
# Create notifications in batch
notifications_data = [
    {
        "user_id": "user_123",
        "title": "Welcome!",
        "message": "Thanks for joining",
        "type": "system"
    },
    # ... more notifications
]

result = await batch_create_notifications(db, notifications_data)
print(f"Created {result.successful} notifications")
```

### 3. Custom Configuration

```python
# Custom batch configuration
config = {
    "batch_size": 50,        # Process 50 items at once
    "max_retries": 5,        # Retry up to 5 times
    "parallel_workers": 10,  # Use 10 parallel workers
    "timeout": 60.0         # 60 second timeout per item
}

result = await batch_create_notifications(db, data, config)
```

## Creating Custom Processors

### 1. Inherit from BatchProcessor

```python
from core.batch_system import BatchProcessor, BatchItem

class UserBatchProcessor(BatchProcessor):
    def __init__(self, db: Session):
        self.db = db
    
    async def validate_item(self, item: BatchItem) -> bool:
        # Validate user data
        data = item.data
        if not data.get('email') or '@' not in data['email']:
            item.error = "Invalid email"
            return False
        return True
    
    async def process_item(self, item: BatchItem) -> Any:
        # Process user creation
        user = User(**item.data)
        self.db.add(user)
        self.db.commit()
        return user
```

### 2. Use the Processor

```python
# Create batch system
batch_system = create_batch_system(db)
processor = UserBatchProcessor(db)

# Create and process batch
batch_id = await batch_system.create_batch(users_data, processor)
result = await batch_system.process_batch(batch_id, processor)
```

## API Endpoints

### Authentication Required
All batch endpoints require admin authentication.

### Available Endpoints

#### 1. Create Notifications
```http
POST /api/batch/notifications/create
```

**Request Body:**
```json
{
    "notifications": [
        {
            "user_id": "user_123",
            "title": "Welcome",
            "message": "Thanks for joining",
            "type": "system",
            "priority": "medium"
        }
    ],
    "config": {
        "batch_size": 100,
        "max_retries": 3,
        "parallel_workers": 5
    }
}
```

#### 2. Cleanup Old Notifications
```http
POST /api/batch/notifications/cleanup
```

**Request Body:**
```json
{
    "older_than_days": 30,
    "config": {
        "batch_size": 50
    }
}
```

#### 3. Create Products
```http
POST /api/batch/products/create
```

#### 4. Update Prices
```http
POST /api/batch/products/update-prices
```

#### 5. Get Supported Operations
```http
GET /api/batch/operations/supported
```

## Configuration Options

### BatchConfig Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `batch_size` | int | 100 | Items to process in each chunk |
| `max_retries` | int | 3 | Maximum retry attempts |
| `retry_delay` | float | 1.0 | Delay between retries (seconds) |
| `timeout` | float | 300.0 | Timeout per item (seconds) |
| `parallel_workers` | int | 5 | Number of parallel workers |
| `fail_fast` | bool | false | Stop on first error |
| `validate_before_process` | bool | true | Pre-validate all items |
| `auto_cleanup` | bool | true | Auto cleanup old batches |
| `cleanup_after_hours` | int | 24 | Hours before cleanup |

## Error Handling

### Error Types

1. **Validation Errors**: Invalid data format or missing fields
2. **Processing Errors**: Failures during item processing
3. **System Errors**: Database connections, timeouts, etc.

### Retry Logic

- Validation errors: No retry (fail immediately)
- Resource not found: No retry
- Connection/timeout: Retry with exponential backoff
- Other errors: Configurable retry behavior

### Error Response Format

```json
{
    "batch_id": "batch_create_1234567890",
    "total_items": 100,
    "successful": 85,
    "failed": 15,
    "errors": [
        {
            "item_id": "batch_create_1234567890_item_5",
            "error": "Validation failed: missing email",
            "retry_count": 0,
            "timestamp": "2024-01-01T12:00:00Z"
        }
    ]
}
```

## Monitoring

### Batch Status

```python
# Get batch status
status = await batch_system.get_batch_status(batch_id)
print(f"Status: {status.status}")
print(f"Progress: {status.successful + status.failed}/{status.total_items}")
```

### Real-time Monitoring

```python
# Monitor progress
while not process_task.done():
    status = await batch_system.get_batch_status(batch_id)
    print(f"Progress: {status.successful + status.failed}/{status.total_items}")
    await asyncio.sleep(2)
```

## Performance Guidelines

### Optimal Settings

- **Small batches (< 1000 items)**: Default settings work well
- **Medium batches (1000-10000 items)**: Increase `batch_size` to 200-500
- **Large batches (> 10000 items)**: Use `batch_size` 500-1000, increase `parallel_workers` to 10-20

### Resource Considerations

- **Database connections**: Limit `parallel_workers` based on connection pool size
- **Memory usage**: Larger `batch_size` uses more memory
- **CPU usage**: More `parallel_workers` increases CPU usage

## Examples

See `examples/batch_system_usage.py` for comprehensive examples including:

1. Simple notification batch
2. Product batch with custom config
3. Custom batch processor
4. Bulk price updates
5. Progress monitoring
6. Error handling

## Extending the System

### Adding New Entity Processors

1. Create processor in `core/batch_processors/`
2. Inherit from `BatchProcessor`
3. Implement required methods
4. Add convenience functions
5. Create API endpoints if needed

### Custom Validation Rules

```python
async def validate_item(self, item: BatchItem) -> bool:
    # Add your validation logic
    if not self._validate_business_rules(item.data):
        item.error = "Business rule validation failed"
        return False
    return True
```

### Custom Error Handling

```python
async def error_handler(self, item: BatchItem, error: Exception) -> bool:
    # Custom retry logic
    if "temporary" in str(error).lower():
        return item.retry_count < 5  # Retry temporary errors
    return False  # Don't retry permanent errors
```

## Best Practices

1. **Validate Early**: Use pre-processing validation to catch errors before processing
2. **Batch Size**: Start with default settings, tune based on performance
3. **Error Handling**: Implement specific error handling for your use case
4. **Monitoring**: Always monitor batch progress for long-running operations
5. **Testing**: Test batch operations with various data sizes and error conditions
6. **Cleanup**: Enable auto-cleanup to prevent memory leaks
7. **Logging**: Use appropriate log levels for debugging and monitoring

## Integration Examples

### With Existing Services

```python
# Integrate with existing notification service
from services.notification_service import NotificationService

class NotificationBatchProcessor(BatchProcessor):
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)
    
    async def process_item(self, item: BatchItem) -> Any:
        return self.notification_service.create_notification(**item.data)
```

### With Background Tasks

```python
from fastapi import BackgroundTasks

async def process_batch_in_background(batch_data):
    result = await batch_create_notifications(db, batch_data)
    # Send completion notification
    await send_batch_completion_email(result)

@app.post("/batch/notifications")
async def create_batch_notifications(
    data: BatchRequest,
    background_tasks: BackgroundTasks
):
    background_tasks.add_task(process_batch_in_background, data.notifications)
    return {"message": "Batch processing started"}
```

---

**Note**: This batch system is designed to be flexible and extensible. You can adapt it for any entity or operation type by creating custom processors and configurations.