"""
Distributed tracing framework with OpenTelemetry support.

Provides request tracing, span management, and context propagation.
"""

import asyncio
import json
import time
import uuid
from contextlib import contextmanager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import threading
from collections import defaultdict


class SpanKind(Enum):
    """Span kinds as per OpenTelemetry specification."""
    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class StatusCode(Enum):
    """Span status codes."""
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class SpanStatus:
    """Status of a span."""
    code: StatusCode
    message: Optional[str] = None


@dataclass
class SpanContext:
    """Context for distributed tracing."""
    trace_id: str
    span_id: str
    trace_flags: int = 0
    trace_state: Optional[str] = None
    is_remote: bool = False

    def is_valid(self) -> bool:
        """Check if context is valid."""
        return bool(self.trace_id and self.span_id)


@dataclass
class Link:
    """Link to another span."""
    context: SpanContext
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    """Event within a span."""
    name: str
    timestamp: float = field(default_factory=time.time)
    attributes: Dict[str, Any] = field(default_factory=dict)


class Span:
    """Represents a unit of work in a trace."""

    def __init__(
        self,
        name: str,
        context: SpanContext,
        kind: SpanKind = SpanKind.INTERNAL,
        parent: Optional['Span'] = None,
        attributes: Optional[Dict[str, Any]] = None,
        links: Optional[List[Link]] = None,
        start_time: Optional[float] = None
    ):
        self.name = name
        self.context = context
        self.kind = kind
        self.parent = parent
        self.attributes = attributes or {}
        self.links = links or []
        self.events: List[Event] = []
        self.status = SpanStatus(StatusCode.UNSET)
        self.start_time = start_time or time.time()
        self.end_time: Optional[float] = None
        self._lock = threading.RLock()  # Use RLock for reentrant locking

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span."""
        with self._lock:
            self.attributes[key] = value

    def set_attributes(self, attributes: Dict[str, Any]) -> None:
        """Set multiple attributes."""
        with self._lock:
            self.attributes.update(attributes)

    def add_event(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add an event to the span."""
        with self._lock:
            event = Event(name, attributes=attributes or {})
            self.events.append(event)

    def set_status(self, code: StatusCode, message: Optional[str] = None) -> None:
        """Set the span status."""
        with self._lock:
            self.status = SpanStatus(code, message)

    def record_exception(
        self,
        exception: Exception,
        attributes: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record an exception in the span."""
        with self._lock:
            exc_attributes = {
                "exception.type": type(exception).__name__,
                "exception.message": str(exception),
                **(attributes or {})
            }
            self.add_event("exception", exc_attributes)
            self.set_status(StatusCode.ERROR, str(exception))

    def end(self, end_time: Optional[float] = None) -> None:
        """End the span."""
        with self._lock:
            if self.end_time is None:
                self.end_time = end_time or time.time()

    def is_recording(self) -> bool:
        """Check if span is still recording."""
        return self.end_time is None

    def get_duration(self) -> float:
        """Get span duration in seconds."""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    def to_dict(self) -> Dict[str, Any]:
        """Convert span to dictionary."""
        return {
            "name": self.name,
            "trace_id": self.context.trace_id,
            "span_id": self.context.span_id,
            "parent_span_id": self.parent.context.span_id if self.parent else None,
            "kind": self.kind.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.get_duration() if self.end_time else None,
            "attributes": self.attributes,
            "events": [
                {
                    "name": e.name,
                    "timestamp": e.timestamp,
                    "attributes": e.attributes
                }
                for e in self.events
            ],
            "links": [
                {
                    "trace_id": l.context.trace_id,
                    "span_id": l.context.span_id,
                    "attributes": l.attributes
                }
                for l in self.links
            ],
            "status": {
                "code": self.status.code.value,
                "message": self.status.message
            }
        }


class Tracer:
    """Creates and manages spans."""

    def __init__(self, name: str, resource: Optional[Dict[str, Any]] = None):
        self.name = name
        self.resource = resource or {}
        self._current_span: threading.local = threading.local()
        self._spans: List[Span] = []
        self._lock = threading.RLock()

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent: Optional[Union[Span, SpanContext]] = None,
        attributes: Optional[Dict[str, Any]] = None,
        links: Optional[List[Link]] = None
    ) -> Span:
        """Start a new span."""
        # Generate IDs
        trace_id = self._get_trace_id(parent)
        span_id = self._generate_span_id()

        # Create context
        context = SpanContext(trace_id=trace_id, span_id=span_id)

        # Handle parent
        parent_span = None
        if isinstance(parent, Span):
            parent_span = parent
        elif isinstance(parent, SpanContext):
            # Create a non-recording span as parent
            parent_span = Span("parent", parent)

        # Create span
        span = Span(
            name=name,
            context=context,
            kind=kind,
            parent=parent_span,
            attributes=attributes,
            links=links
        )

        # Store span
        with self._lock:
            self._spans.append(span)

        return span

    @contextmanager
    def start_as_current_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None,
        links: Optional[List[Link]] = None
    ):
        """Start a span and set it as current."""
        parent = self.get_current_span()
        span = self.start_span(name, kind, parent, attributes, links)
        token = self._set_current_span(span)
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            raise
        finally:
            span.end()
            self._reset_current_span(token)

    @asynccontextmanager
    async def start_as_current_span_async(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None,
        links: Optional[List[Link]] = None
    ):
        """Async version of start_as_current_span."""
        parent = self.get_current_span()
        span = self.start_span(name, kind, parent, attributes, links)
        token = self._set_current_span(span)
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            raise
        finally:
            span.end()
            self._reset_current_span(token)

    def get_current_span(self) -> Optional[Span]:
        """Get the current active span."""
        return getattr(self._current_span, 'span', None)

    def _set_current_span(self, span: Span) -> Any:
        """Set current span and return token for restoration."""
        old_span = self.get_current_span()
        self._current_span.span = span
        return old_span

    def _reset_current_span(self, token: Any) -> None:
        """Reset current span to previous value."""
        self._current_span.span = token

    def _get_trace_id(self, parent: Optional[Union[Span, SpanContext]]) -> str:
        """Get or generate trace ID."""
        if isinstance(parent, Span):
            return parent.context.trace_id
        elif isinstance(parent, SpanContext):
            return parent.trace_id
        elif self.get_current_span():
            return self.get_current_span().context.trace_id
        else:
            return self._generate_trace_id()

    def _generate_trace_id(self) -> str:
        """Generate a new trace ID."""
        return uuid.uuid4().hex

    def _generate_span_id(self) -> str:
        """Generate a new span ID."""
        return uuid.uuid4().hex[:16]

    def get_finished_spans(self) -> List[Span]:
        """Get all finished spans."""
        with self._lock:
            return [s for s in self._spans if s.end_time is not None]

    def clear_finished_spans(self) -> None:
        """Clear finished spans from memory."""
        with self._lock:
            self._spans = [s for s in self._spans if s.end_time is None]


class TracerProvider:
    """Manages tracers and span processors."""

    def __init__(self, resource: Optional[Dict[str, Any]] = None):
        self.resource = resource or self._default_resource()
        self._tracers: Dict[str, Tracer] = {}
        self._processors: List['SpanProcessor'] = []
        self._lock = threading.RLock()

    def get_tracer(
        self,
        name: str,
        version: Optional[str] = None
    ) -> Tracer:
        """Get or create a tracer."""
        key = f"{name}:{version or ''}"
        with self._lock:
            if key not in self._tracers:
                self._tracers[key] = Tracer(name, self.resource)
            return self._tracers[key]

    def add_span_processor(self, processor: 'SpanProcessor') -> None:
        """Add a span processor."""
        with self._lock:
            self._processors.append(processor)

    def _default_resource(self) -> Dict[str, Any]:
        """Get default resource attributes."""
        return {
            "service.name": "event-bus",
            "service.version": "1.0.0",
            "telemetry.sdk.name": "custom",
            "telemetry.sdk.version": "1.0.0"
        }


class SpanProcessor:
    """Base class for span processors."""

    def on_start(self, span: Span) -> None:
        """Called when a span starts."""
        pass

    def on_end(self, span: Span) -> None:
        """Called when a span ends."""
        pass

    def shutdown(self) -> None:
        """Shutdown the processor."""
        pass


class ConsoleSpanExporter(SpanProcessor):
    """Exports spans to console for debugging."""

    def __init__(self, pretty_print: bool = True):
        self.pretty_print = pretty_print

    def on_end(self, span: Span) -> None:
        """Print span when it ends."""
        span_dict = span.to_dict()
        if self.pretty_print:
            print(json.dumps(span_dict, indent=2, default=str))
        else:
            print(json.dumps(span_dict, default=str))


class BatchSpanProcessor(SpanProcessor):
    """Batches spans for export."""

    def __init__(
        self,
        exporter: SpanProcessor,
        max_batch_size: int = 512,
        schedule_delay_millis: int = 5000
    ):
        self.exporter = exporter
        self.max_batch_size = max_batch_size
        self.schedule_delay_millis = schedule_delay_millis
        self._spans: List[Span] = []
        self._lock = threading.RLock()
        self._shutdown = False
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def on_end(self, span: Span) -> None:
        """Add span to batch."""
        if self._shutdown:
            return

        with self._lock:
            self._spans.append(span)
            if len(self._spans) >= self.max_batch_size:
                self._export_batch()

    def _worker(self) -> None:
        """Worker thread for periodic export."""
        while not self._shutdown:
            time.sleep(self.schedule_delay_millis / 1000.0)
            if not self._shutdown:
                with self._lock:
                    self._export_batch()

    def _export_batch(self) -> None:
        """Export current batch of spans."""
        if not self._spans:
            return

        batch = self._spans[:]
        self._spans.clear()

        for span in batch:
            self.exporter.on_end(span)

    def shutdown(self) -> None:
        """Shutdown the processor."""
        self._shutdown = True
        with self._lock:
            self._export_batch()
        self._worker_thread.join(timeout=1)


class W3CTraceContextPropagator:
    """W3C Trace Context propagator for distributed tracing."""

    TRACEPARENT_HEADER = "traceparent"
    TRACESTATE_HEADER = "tracestate"

    def inject(self, span: Span, carrier: Dict[str, str]) -> None:
        """Inject span context into carrier."""
        if not span or not span.context.is_valid():
            return

        # Format: version-trace_id-span_id-trace_flags
        traceparent = f"00-{span.context.trace_id}-{span.context.span_id}-{span.context.trace_flags:02x}"
        carrier[self.TRACEPARENT_HEADER] = traceparent

        if span.context.trace_state:
            carrier[self.TRACESTATE_HEADER] = span.context.trace_state

    def extract(self, carrier: Dict[str, str]) -> Optional[SpanContext]:
        """Extract span context from carrier."""
        traceparent = carrier.get(self.TRACEPARENT_HEADER)
        if not traceparent:
            return None

        try:
            parts = traceparent.split("-")
            if len(parts) != 4:
                return None

            version, trace_id, span_id, trace_flags = parts

            return SpanContext(
                trace_id=trace_id,
                span_id=span_id,
                trace_flags=int(trace_flags, 16),
                trace_state=carrier.get(self.TRACESTATE_HEADER),
                is_remote=True
            )
        except (ValueError, IndexError):
            return None


# Global tracer provider
_tracer_provider = TracerProvider()


def get_tracer_provider() -> TracerProvider:
    """Get global tracer provider."""
    return _tracer_provider


def set_tracer_provider(provider: TracerProvider) -> None:
    """Set global tracer provider."""
    global _tracer_provider
    _tracer_provider = provider


def get_tracer(name: str, version: Optional[str] = None) -> Tracer:
    """Get a tracer from global provider."""
    return _tracer_provider.get_tracer(name, version)


# Convenience decorators
def trace(name: Optional[str] = None, kind: SpanKind = SpanKind.INTERNAL):
    """Decorator to trace a function."""
    def decorator(func):
        span_name = name or f"{func.__module__}.{func.__name__}"

        if asyncio.iscoroutinefunction(func):
            async def wrapper(*args, **kwargs):
                tracer = get_tracer(func.__module__)
                async with tracer.start_as_current_span_async(span_name, kind=kind) as span:
                    span.set_attribute("function", func.__name__)
                    return await func(*args, **kwargs)
        else:
            def wrapper(*args, **kwargs):
                tracer = get_tracer(func.__module__)
                with tracer.start_as_current_span(span_name, kind=kind) as span:
                    span.set_attribute("function", func.__name__)
                    return func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator