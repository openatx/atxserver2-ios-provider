from __future__ import print_function

import os
import argparse

from tornado.ioloop import IOLoop
import tornado.web
from tornado import gen
from tornado.httpclient import AsyncHTTPClient
from tornado.log import enable_pretty_logging
from logzero import logger

import idb
import heartbeat

from utils import current_ip

idevices = {}
hbc = None


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


async def device_watch():
    """
    When iOS device plugin, launch WDA
    """

    async for event in idb.track_devices():
        logger.debug("Event: %s", event)
        if event.present:
            idevices[event.udid] = d = idb.IDevice(event.udid)

            # start webdriveragent
            async def callback(status: str):
                if status == "run":
                    await hbc.device_update({
                        "udid": d.udid,
                        "provider": None, # no provider indicate not present
                        "colding": False,
                        "properties": {
                            "name": d.name,
                            "product": d.product,
                        }
                    })
                    print(d, "run")
                elif status == "ready":
                    logger.debug("%s %s", d, "healthcheck passed")
                    await hbc.device_update({
                        "udid": d.udid,
                        "colding": False,
                        "provider": {
                            "wdaUrl": "http://{}:{}".format(current_ip(), d.public_port)
                        }
                    })
                elif status == "offline":
                    await hbc.device_update({
                        "udid": d.udid,
                        "provider": None,
                    })
        
            IOLoop.current().spawn_callback(d.run_wda_forever, callback)
        else: # offline
            idevices[event.udid].stop()
            idevices.pop(event.udid)


async def async_main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-d', '--debug', action="store_true", help="enable debug mode")
    parser.add_argument(
        '-p', '--port', type=int, default=3600, help='listen port')
    parser.add_argument(
        "-s", "--server", type=str, required=True, help="server address")

    args = parser.parse_args()

    # start server
    enable_pretty_logging()
    app = make_app(debug=args.debug)
    app.listen(args.port)

    global hbc
    server_addr = args.server.replace("http://", "").replace("/", "")
    hbc = await heartbeat.heartbeat_connect(
        "ws://" + server_addr + "/websocket/heartbeat", platform='apple')

    await device_watch()
    # IOLoop.current().spawn_callback(device_watch)


if __name__ == "__main__":
    try:
        IOLoop.current().run_sync(async_main)
        # IOLoop.instance().start()
    except KeyboardInterrupt:
        IOLoop.instance().stop()
        for d in idevices.values():
            d.destroy()
