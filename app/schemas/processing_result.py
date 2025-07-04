from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class ProcessingResult(BaseModel):
    success: bool
    context_id: Optional[str] = None
    error_message: Optional[str] = None
    processing_time: Optional[float] = None
    chunks_created: Optional[int] = None
    embeddings_created: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
