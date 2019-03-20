from __future__ import print_function

import argparse
import os
from collections import defaultdict
from functools import partial

import tornado.web
from logzero import logger
from tornado import gen, httpclient
from tornado.httpclient import AsyncHTTPClient
from tornado.ioloop import IOLoop
from tornado.log import enable_pretty_logging

import heartbeat
import idb
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


class ColdingHandler(tornado.web.RequestHandler):
    async def post(self, udid):
        d = idevices.get(udid)
        try:
            if not d:
                raise Exception("Device not found")

            d.restart_wda_proxy()
            wda_url = "http://{}:{}".format(current_ip(), d.public_port)
            await d.wda_healthcheck()
            await hbc.device_update({
                "udid": udid,
                "colding": False,
                "provider": {
                    "wdaUrl": wda_url,
                }
            })
            self.write({
                "success": True,
                "description": "Device successfully colded"
            })
        except Exception as e:
            logger.warning("colding procedure got error: %s", e)
            self.set_status(400)  # bad request
            self.write({
                "success": False,
                "description": "udid: %s not found" % udid
            })


class AppInstallHandler(tornado.web.RequestHandler):
    def post(self):
        raise NotImplementedError()


def make_app(**settings):
    settings['template_path'] = 'templates'
    settings['static_path'] = 'static'
    settings['cookie_secret'] = os.environ.get("SECRET", "SECRET:_")
    settings['login_url'] = '/login'
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/testerhome", ProxyTesterhomeHandler),
        (r"/devices/([^/]+)/cold", ColdingHandler),
        (r"/devices/([^/]+)/app/install", AppInstallHandler),
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
            async def callback(d: idb.IDevice, status: str, info=None):
                if status == "run":
                    await hbc.device_update({
                        "udid": d.udid,
                        "provider": None,  # no provider indicate not present
                        "colding": False,
                        "properties": {
                            "name": d.name,
                            "product": d.product,
                            "brand": "Apple",
                        }
                    })
                    print(d, "run")
                elif status == "ready":
                    logger.debug("%s %s", d, "healthcheck passed")

                    assert isinstance(info, dict)
                    info = defaultdict(dict, info)

                    await hbc.device_update({
                        "udid": d.udid,
                        "colding": False,
                        "provider": {
                            "wdaUrl": "http://{}:{}".format(current_ip(), d.public_port)
                        },
                        "properties": {
                            "ip": info['value']['ios']['ip'],
                            "version": info['value']['os']['version'],
                            "sdkVersion": info['value']['os']['sdkVersion'],
                        }
                    }) # yapf: disable
                elif status == "offline":
                    await hbc.device_update({
                        "udid": d.udid,
                        "provider": None,
                    })

            IOLoop.current().spawn_callback(d.run_wda_forever,
                                            partial(callback, d))
        else:  # offline
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
    self_url = "http://{}:{}".format(current_ip(), args.port)
    server_addr = args.server.replace("http://", "").replace("/", "")
    hbc = await heartbeat.heartbeat_connect(
        server_addr, platform='apple', self_url=self_url)

    await device_watch()


if __name__ == "__main__":
    try:
        IOLoop.current().run_sync(async_main)
        # IOLoop.instance().start()
    except KeyboardInterrupt:
        IOLoop.instance().stop()
        for d in idevices.values():
            d.destroy()
