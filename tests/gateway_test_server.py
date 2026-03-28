import aiohttp
import aiohttp.test_utils
import asyncio


class GatewayTestServer(aiohttp.test_utils.RawTestServer):
    ''' Test server that relies on test case to supply responses and control timing '''

    def __init__(self, *, ssl=None, **kwargs):
        super().__init__(self._handle_request, **kwargs)
        self._ssl = ssl
        self._requests = asyncio.Queue()
        self._responses = {}

    async def start_server(self, **kwargs):
        kwargs.setdefault('ssl', self._ssl)
        await super().start_server(**kwargs)

    async def close(self):
        for future in self._responses.values():
            future.cancel()
        await super().close()

    async def _handle_request(self, request):
        self._responses[id(request)] = response = asyncio.Future()
        self._requests.put_nowait(request)
        try:
            return await response
        finally:
            del self._responses[id(request)]

    @property
    def awaiting_request_count(self):
        return self._requests.qsize()

    async def receive_request(self, *, timeout=None):
        ''' Wait until the test server receives a request
        :param float timeout: Bail out after that many seconds.
        :return: received request, not yet serviced.
        :rtype: aiohttp.web.BaseRequest
        :see: :meth:`send_response`
        '''
        return await asyncio.wait_for(self._requests.get(), timeout=timeout)

    def send_response(self, request, *args, **kwargs):
        ''' Reply to a received request.
        :param request: the request to respond to.
        :param args: forwarded to :class:`aiohttp.web.Response`.
        :param kwargs: forwarded to :class:`aiohttp.web.Response`.
        '''
        self._responses[id(request)].set_result(aiohttp.web.Response(*args, **kwargs))
