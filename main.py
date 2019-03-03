from __future__ import print_function

import os
import argparse

import tornado.ioloop
import tornado.web
from tornado import gen
from tornado.httpclient import AsyncHTTPClient
from tornado.log import enable_pretty_logging


class MainHandler(tornado.web.RequestHandler):
    @gen.coroutine
    def get(self):
        yield gen.sleep(.5)
        self.write("Hello, world")


class ProxyTesterhomeHandler(tornado.web.RequestHandler):
    @gen.coroutine
    def get(self):
        body = yield self.get_testerhome()
        self.write(body)

    @gen.coroutine
    def get_testerhome(self):
        http_client = AsyncHTTPClient()
        response = yield http_client.fetch("https://testerhome.com/")
        raise gen.Return(response.body)


def make_app(**settings):
    settings['template_path'] = 'templates'
    settings['static_path'] = 'static'
    settings['cookie_secret'] = os.environ.get("SECRET", "SECRET:_")
    settings['login_url'] = '/login'
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/testerhome", ProxyTesterhomeHandler),
    ], **settings)


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-d', '--debug', action="store_true",
                        help="enable debug mode")
    parser.add_argument('-p', '--port', type=int, help='listen port')
    args = parser.parse_args()

    enable_pretty_logging()

    app = make_app(debug=True)
    app.listen(args.port)
    try:
        tornado.ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        tornado.ioloop.IOLoop.instance().stop()


if __name__ == "__main__":
    main()
