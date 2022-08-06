import asyncio
from contextlib import suppress

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from fastapi_events.dispatcher import dispatch
from fastapi_events.handlers.base import BaseEventHandler
from fastapi_events.middleware import EventHandlerASGIMiddleware
from fastapi_events.typing import Event


@pytest.mark.parametrize(
    "return_non_200,raise_error,add_global_exception_handler",
    ((True, False, None),
     (False, False, None),
     (False, True, True),
     (False, True, False))
)
def test_event_handling(
    return_non_200, raise_error, add_global_exception_handler
):
    """
    Making sure events are handled regardless of response status, and exceptions
    This is unlike how BackgroundTask works.
    """

    class DummyHandler(BaseEventHandler):
        def __init__(self):
            self.event_processed = []

        async def handle(self, event: Event) -> None:
            self.event_processed.append(event)

    dummy_handler_1 = DummyHandler()
    dummy_handler_2 = DummyHandler()

    app = Starlette(middleware=[
        Middleware(EventHandlerASGIMiddleware,
                   handlers=[dummy_handler_1, dummy_handler_2])])

    if add_global_exception_handler:
        @app.exception_handler(ValueError)
        def global_exception_handler(request, exc):
            return JSONResponse([], status_code=500)

    @app.route("/")
    async def root(request: Request) -> JSONResponse:
        for idx in range(5):
            dispatch(event_name="new event", payload={"id": idx + 1})

        if raise_error:
            raise ValueError

        return JSONResponse([], status_code=400 if return_non_200 else 200)

    client = TestClient(app)

    with suppress(ValueError):
        client.get("/")

    assert len(dummy_handler_1.event_processed) == len(dummy_handler_2.event_processed) == 5


@pytest.mark.parametrize(
    "middleware_id",
    ((None),
     (1234),
     (1337))
)
@pytest.mark.asyncio
async def test_event_handling_without_request(middleware_id):
    """
    Making sure events are handled when dispatched with an explicit middleware_id
    """

    class DummyHandler(BaseEventHandler):
        def __init__(self):
            self.event_processed = []

        async def handle(self, event: Event) -> None:
            self.event_processed.append(event)

    dummy_handler_1 = DummyHandler()
    dummy_handler_2 = DummyHandler()

    _ = Starlette(middleware=[
        Middleware(EventHandlerASGIMiddleware,
                   handlers=[dummy_handler_1, dummy_handler_2],
                   middleware_id=middleware_id)])

    if middleware_id is None:
        with pytest.raises(LookupError, match=r"^<ContextVar name='fastapi_middleware_identifier' at"):
            dispatch(event_name="new event", payload={"id": "fail"}, middleware_id=middleware_id)
    else:
        for idx in range(5):
            dispatch(event_name="new event", payload={"id": idx + 1}, middleware_id=middleware_id)

        # allow time for events to be dispatched
        await asyncio.sleep(0.1)

        assert len(dummy_handler_1.event_processed) == len(dummy_handler_2.event_processed) == 5
