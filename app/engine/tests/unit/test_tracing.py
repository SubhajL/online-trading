"""
Unit tests for tracing framework.
"""

import pytest
import asyncio
import time
import json
from unittest.mock import Mock, patch
from io import StringIO

from app.engine.core.tracing import (
    SpanKind,
    StatusCode,
    SpanStatus,
    SpanContext,
    Link,
    Event,
    Span,
    Tracer,
    TracerProvider,
    SpanProcessor,
    ConsoleSpanExporter,
    BatchSpanProcessor,
    W3CTraceContextPropagator,
    get_tracer_provider,
    set_tracer_provider,
    get_tracer,
    trace,
)


class TestSpanContext:
    def test_span_context_creation(self):
        context = SpanContext(trace_id="trace123", span_id="span456", trace_flags=1)

        assert context.trace_id == "trace123"
        assert context.span_id == "span456"
        assert context.trace_flags == 1
        assert context.is_remote is False

    def test_span_context_validity(self):
        valid_context = SpanContext("trace123", "span456")
        assert valid_context.is_valid() is True

        invalid_context = SpanContext("", "")
        assert invalid_context.is_valid() is False


class TestSpan:
    def test_span_creation(self):
        context = SpanContext("trace123", "span456")
        span = Span(name="test_span", context=context, kind=SpanKind.INTERNAL)

        assert span.name == "test_span"
        assert span.context == context
        assert span.kind == SpanKind.INTERNAL
        assert span.parent is None
        assert span.start_time > 0
        assert span.end_time is None

    def test_span_attributes(self):
        context = SpanContext("trace123", "span456")
        span = Span("test", context)

        span.set_attribute("key1", "value1")
        span.set_attributes({"key2": "value2", "key3": 123})

        assert span.attributes["key1"] == "value1"
        assert span.attributes["key2"] == "value2"
        assert span.attributes["key3"] == 123

    def test_span_events(self):
        context = SpanContext("trace123", "span456")
        span = Span("test", context)

        span.add_event("event1")
        span.add_event("event2", {"attr": "value"})

        assert len(span.events) == 2
        assert span.events[0].name == "event1"
        assert span.events[1].name == "event2"
        assert span.events[1].attributes["attr"] == "value"

    def test_span_status(self):
        context = SpanContext("trace123", "span456")
        span = Span("test", context)

        assert span.status.code == StatusCode.UNSET

        span.set_status(StatusCode.OK)
        assert span.status.code == StatusCode.OK

        span.set_status(StatusCode.ERROR, "Error message")
        assert span.status.code == StatusCode.ERROR
        assert span.status.message == "Error message"

    def test_span_exception_recording(self):
        context = SpanContext("trace123", "span456")
        span = Span("test", context)

        exception = ValueError("Test error")
        span.record_exception(exception)

        assert span.status.code == StatusCode.ERROR
        assert span.status.message == "Test error"
        assert len(span.events) == 1
        assert span.events[0].name == "exception"
        assert span.events[0].attributes["exception.type"] == "ValueError"

    def test_span_lifecycle(self):
        context = SpanContext("trace123", "span456")
        span = Span("test", context)

        assert span.is_recording() is True

        time.sleep(0.01)
        span.end()

        assert span.is_recording() is False
        assert span.end_time is not None
        assert span.get_duration() > 0

    def test_span_to_dict(self):
        context = SpanContext("trace123", "span456")
        span = Span(
            name="test",
            context=context,
            kind=SpanKind.SERVER,
            attributes={"key": "value"},
        )
        span.add_event("event1")
        span.end()

        span_dict = span.to_dict()

        assert span_dict["name"] == "test"
        assert span_dict["trace_id"] == "trace123"
        assert span_dict["span_id"] == "span456"
        assert span_dict["kind"] == "server"
        assert span_dict["attributes"]["key"] == "value"
        assert len(span_dict["events"]) == 1
        assert span_dict["duration"] is not None


class TestTracer:
    def test_tracer_creation(self):
        tracer = Tracer("test_tracer")

        assert tracer.name == "test_tracer"
        assert tracer.resource == {}
        assert tracer.get_current_span() is None

    def test_start_span(self):
        tracer = Tracer("test_tracer")

        span = tracer.start_span(
            "operation", kind=SpanKind.CLIENT, attributes={"key": "value"}
        )

        assert span.name == "operation"
        assert span.kind == SpanKind.CLIENT
        assert span.attributes["key"] == "value"
        assert span.context.trace_id
        assert span.context.span_id

    def test_span_parent_child_relationship(self):
        tracer = Tracer("test_tracer")

        parent = tracer.start_span("parent")
        child = tracer.start_span("child", parent=parent)

        assert child.parent == parent
        assert child.context.trace_id == parent.context.trace_id
        assert child.context.span_id != parent.context.span_id

    def test_start_as_current_span(self):
        tracer = Tracer("test_tracer")

        assert tracer.get_current_span() is None

        with tracer.start_as_current_span("operation") as span:
            assert tracer.get_current_span() == span
            assert span.name == "operation"

        assert tracer.get_current_span() is None
        assert span.end_time is not None

    def test_nested_spans(self):
        tracer = Tracer("test_tracer")

        with tracer.start_as_current_span("parent") as parent_span:
            assert tracer.get_current_span() == parent_span

            with tracer.start_as_current_span("child") as child_span:
                assert tracer.get_current_span() == child_span
                assert child_span.parent == parent_span

            assert tracer.get_current_span() == parent_span

    def test_exception_in_span(self):
        tracer = Tracer("test_tracer")

        with pytest.raises(ValueError):
            with tracer.start_as_current_span("operation") as span:
                raise ValueError("Test error")

        assert span.status.code == StatusCode.ERROR
        assert "ValueError" in span.events[0].attributes["exception.type"]

    @pytest.mark.asyncio
    async def test_async_span_context_manager(self):
        tracer = Tracer("test_tracer")

        async with tracer.start_as_current_span_async("async_op") as span:
            assert tracer.get_current_span() == span
            await asyncio.sleep(0.01)

        assert tracer.get_current_span() is None
        assert span.end_time is not None

    def test_finished_spans_tracking(self):
        tracer = Tracer("test_tracer")

        span1 = tracer.start_span("span1")
        span2 = tracer.start_span("span2")

        assert len(tracer.get_finished_spans()) == 0

        span1.end()
        assert len(tracer.get_finished_spans()) == 1

        span2.end()
        assert len(tracer.get_finished_spans()) == 2

        tracer.clear_finished_spans()
        assert len(tracer._spans) == 0


class TestTracerProvider:
    def test_tracer_provider_creation(self):
        provider = TracerProvider()

        assert provider.resource["service.name"] == "event-bus"
        assert len(provider._tracers) == 0

    def test_get_tracer(self):
        provider = TracerProvider()

        tracer1 = provider.get_tracer("tracer1")
        tracer2 = provider.get_tracer("tracer2")
        tracer1_again = provider.get_tracer("tracer1")

        assert tracer1.name == "tracer1"
        assert tracer2.name == "tracer2"
        assert tracer1 is tracer1_again

    def test_add_span_processor(self):
        provider = TracerProvider()
        processor = Mock(spec=SpanProcessor)

        provider.add_span_processor(processor)

        assert processor in provider._processors


class TestSpanExporters:
    def test_console_span_exporter(self):
        exporter = ConsoleSpanExporter(pretty_print=False)

        context = SpanContext("trace123", "span456")
        span = Span("test", context)
        span.end()

        with patch("sys.stdout", new=StringIO()) as fake_stdout:
            exporter.on_end(span)
            output = fake_stdout.getvalue()

        assert "trace123" in output
        assert "span456" in output
        assert "test" in output

    def test_batch_span_processor(self):
        mock_exporter = Mock(spec=SpanProcessor)
        processor = BatchSpanProcessor(
            exporter=mock_exporter, max_batch_size=2, schedule_delay_millis=100
        )

        context = SpanContext("trace123", "span456")
        span1 = Span("span1", context)
        span2 = Span("span2", context)
        span3 = Span("span3", context)

        span1.end()
        span2.end()
        span3.end()

        # Add spans
        processor.on_end(span1)
        processor.on_end(span2)  # Should trigger batch export

        time.sleep(0.01)
        assert mock_exporter.on_end.call_count >= 2

        processor.shutdown()


class TestW3CTraceContextPropagator:
    def test_inject_trace_context(self):
        propagator = W3CTraceContextPropagator()

        context = SpanContext(
            trace_id="0123456789abcdef0123456789abcdef",
            span_id="0123456789abcdef",
            trace_flags=1,
        )
        span = Span("test", context)

        carrier = {}
        propagator.inject(span, carrier)

        assert "traceparent" in carrier
        assert (
            carrier["traceparent"]
            == "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
        )

    def test_extract_trace_context(self):
        propagator = W3CTraceContextPropagator()

        carrier = {
            "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
            "tracestate": "vendor1=value1",
        }

        context = propagator.extract(carrier)

        assert context is not None
        assert context.trace_id == "0123456789abcdef0123456789abcdef"
        assert context.span_id == "0123456789abcdef"
        assert context.trace_flags == 1
        assert context.trace_state == "vendor1=value1"
        assert context.is_remote is True

    def test_extract_invalid_trace_context(self):
        propagator = W3CTraceContextPropagator()

        # Invalid format
        carrier = {"traceparent": "invalid"}
        assert propagator.extract(carrier) is None

        # Missing header
        carrier = {}
        assert propagator.extract(carrier) is None


class TestGlobalTracerProvider:
    def test_global_tracer_provider(self):
        provider = get_tracer_provider()
        assert isinstance(provider, TracerProvider)

        custom_provider = TracerProvider()
        set_tracer_provider(custom_provider)

        assert get_tracer_provider() is custom_provider

    def test_get_tracer_from_global(self):
        tracer = get_tracer("test_component")
        assert isinstance(tracer, Tracer)
        assert tracer.name == "test_component"


class TestTraceDecorator:
    def test_sync_function_tracing(self):
        @trace(name="custom_operation")
        def test_function(x, y):
            return x + y

        result = test_function(1, 2)
        assert result == 3

    @pytest.mark.asyncio
    async def test_async_function_tracing(self):
        @trace(kind=SpanKind.SERVER)
        async def async_function(x):
            await asyncio.sleep(0.01)
            return x * 2

        result = await async_function(5)
        assert result == 10

    def test_decorated_function_metadata(self):
        @trace()
        def documented_function():
            """This is a documented function."""
            pass

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a documented function."


class TestSpanWithLinks:
    def test_span_with_links(self):
        tracer = Tracer("test_tracer")

        # Create context for linked span
        linked_context = SpanContext("linked_trace", "linked_span")
        link = Link(linked_context, {"relationship": "caused_by"})

        span = tracer.start_span("operation", links=[link])

        assert len(span.links) == 1
        assert span.links[0].context.trace_id == "linked_trace"
        assert span.links[0].attributes["relationship"] == "caused_by"

        span_dict = span.to_dict()
        assert len(span_dict["links"]) == 1
