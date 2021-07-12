# coding: utf-8

import argparse
import asyncio
import io
import os
import socket
import sys
import urllib.request

import httpx
import requests
import tornado.ioloop
import tornado.web
from tornado.log import enable_pretty_logging
from tornado.websocket import WebSocketHandler
from tornado.iostream import IOStream


class MjpegReader():
    """
    MJPEG format

    Content-Type: multipart/x-mixed-replace; boundary=--BoundaryString
    --BoundaryString
    Content-type: image/jpg
    Content-Length: 12390

    ... image-data here ...


    --BoundaryString
    Content-type: image/jpg
    Content-Length: 12390

    ... image-data here ...
    """
    def __init__(self, url: str):
        self._url = url

    async def aiter_content(self):
        """
        Ref:
        - https://stackoverflow.com/questions/32310951/how-to-get-the-underlying-socket-when-using-python-requests
        - https://www.tornadoweb.org/en/stable/iostream.html
        - https://realpython.com/async-io-python/#other-features-async-for-and-async-generators-comprehensions
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        stream = IOStream(s)
        try:
            url = urllib.request.urlparse(self._url)
            host, port = url.netloc.split(":")
            port = int(port)
            path = url.path or "/"
            await stream.connect((host, port))
            await stream.write(
                "GET {path} HTTP/1.0\r\nHost: {netloc}\r\n\r\n".format(
                    path=path, netloc=url.netloc).encode('utf-8'))
            header_data = await stream.read_until(b"\r\n\r\n")

            while True:
                line = await stream.read_until(b'\r\n')
                if not line.startswith(b"Content-Length"):
                    continue
                length = int(line.decode('utf-8').split(": ")[1])
                await stream.read_until(b"\r\n")
                yield await stream.read_bytes(length)
        finally:
            stream.close()


class CorsMixin:
    def initialize(self):
        self.set_header('Connection', 'close')
        self.request.connection.no_keep_alive = True

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with")
        self.set_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')

    def options(self):
        # no body
        self.set_status(204)
        self.finish()


class ScreenWSHandler(CorsMixin, WebSocketHandler):
    MJPEG_READER = None

    def check_origin(self, origin):
        return True

    async def open(self):
        # print("connection created")
        assert self.MJPEG_READER

        async for content in self.MJPEG_READER.aiter_content():
            await self.write_message(content, binary=True)

    def on_message(self, message):
        # return super().on_message(message)
        pass

    def on_close(self):
        return super().on_close()


# Ref: https://github.com/colevscode/quickproxy/blob/master/quickproxy/proxy.py
class ReverseProxyHandler(CorsMixin, tornado.web.RequestHandler):
    _default_http_client = httpx.AsyncClient(timeout=60)
    TARGET_URL = None

    async def handle_request(self, request):
        assert self.TARGET_URL
        url = self.TARGET_URL.lstrip("/") + request.uri
        async with self._default_http_client.stream(request.method,
                                                    url,
                                                    headers=request.headers.get_all(),
                                                    data=request.body) as resp:
            self.set_status(resp.status_code)
            for k, v in resp.headers.items():
                self.set_header(k, v)
            async for chunk in resp.aiter_bytes():
                self.write(chunk)

    async def get(self):
        await self.handle_request(self.request)

    async def post(self):
        await self.handle_request(self.request)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p",
                        "--port",
                        type=int,
                        default=8200,
                        help="listen port")
    parser.add_argument("--wda-url",
                        default="http://localhost:8100",
                        help="wda server url")
    parser.add_argument("--mjpeg-url",
                        default="http://localhost:9100",
                        help="mjpeg server url")
    args = parser.parse_args()

    ScreenWSHandler.MJPEG_READER = MjpegReader(args.mjpeg_url)
    ReverseProxyHandler.TARGET_URL = args.wda_url

    app = tornado.web.Application([
        (r"/screen", ScreenWSHandler),
        (r"/.*", ReverseProxyHandler),
    ])
    app.listen(args.port)

    enable_pretty_logging()
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()

# program
#     .version("0.1.0")
#     .option("-p, --port <port>", "listen port", parseInt)
#     .option("--wda-url <wdaUrl>", "wda server url")
#     .option("--mjpeg-url <mjpegUrl>", "mjpeg server url")
#     .parse(process.argv)

# console.log(program.port)

# const app = makeApp(program.wdaUrl, program.mjpegUrl)
# app.listen(program.port, () => {
#     console.log("Listen on port", program.port)
# })
