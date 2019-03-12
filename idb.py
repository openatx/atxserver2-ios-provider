# coding: utf-8
#

import subprocess
from concurrent.futures import ThreadPoolExecutor

import tornado.ioloop
from logzero import logger
from tornado import gen
from tornado.concurrent import run_on_executor
from collections import namedtuple

DeviceEvent = namedtuple('DeviceEvent', ['present', 'udid'])


def runcommand(*args) -> str:
    try:
        output = subprocess.check_output(args)
        return output.strip().decode('utf-8')
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    except Exception as e:
        logger.warning("unknown error: %s", e)
        return ""


def list_devices():
    udids = runcommand('idevice_id', '-l').splitlines()
    return udids


def udid2name(udid: str) -> str:
    return runcommand("idevicename", "-u", udid)


def udid2product(udid):
    pt = runcommand("ideviceinfo", "--udid", udid, "--key", "ProductType")
    models = {
        "iPhone8,1": "iPhone 6s",
        "iPhone8,2": "iPhone 6s Plus",
        "iPhone8,4": "iPhone SE",
        "iPhone9,1": "iPhone 7",
        "iPhone9,3": "iPhone 7",
        "iPhone9,2": "iPhone 7 Plus",
        "iPhone9,4": "iPhone 7 Plus",
        "iPhone10,1": "iPhone 8",
        "iPhone10,4": "iPhone 8",
        "iPhone10,2": "iPhone 8 Plus",
        "iPhone10,5": "iPhone 8 Plus",
        "iPhone10,3": "iPhone X",
        "iPhone10,6": "iPhone X",
        "iPhone11,8": "iPhone XR",
        "iPhone11,2": "iPhone XS",
        "iPhone11,6": "iPhone XS Max",
    }
    return models.get(pt, "Unknown")


def trace_devices():
    lasts = []
    while True:
        currs = list_devices()
        gones = set(lasts).difference(currs)  # 離線
        backs = set(currs).difference(lasts)  # 在線
        lasts = currs

        for udid in backs:
            logger.info("Back online: %s", udid)

        for udid in gones:
            logger.info("Went offline: %s", udid)


class Tracker():
    executor = ThreadPoolExecutor(4)

    def __init__(self):
        self._lasts = []

    @run_on_executor(executor='executor')
    def list_devices(self):
        return list_devices()

    @gen.coroutine
    def update(self):
        """ Wired, can not use async here """
        # await gen.sleep(1)
        lasts = self._lasts
        currs = yield self.list_devices()
        gones = set(lasts).difference(currs)  # 離線
        backs = set(currs).difference(lasts)  # 在線
        self._lasts = currs
        raise gen.Return((backs, gones))

    async def track_device(self):
        while True:
            backs, gones = await self.update()
            for udid in backs:
                logger.info("Back online: %s", udid)
                yield DeviceEvent(True, udid)

            for udid in gones:
                logger.info("Went offline: %s", udid)
                yield DeviceEvent(False, udid)
            await gen.sleep(1)


class IDevice(object):
    def __init__(self, udid):
        self.udid = udid
        self.name = udid2name(udid)
        self.product = udid2product(udid)

    def run_webdriveragent(self):
        """
        xcodebuild -project WebDriverAgent.xcodeproj \
            -scheme WebDriverAgentRunner WebDriverAgentRunner id=UDID test
        """


def main():
    async def test():
        t = Tracker()
        async for event in t.track_device():
            logger.debug("Event: %s", event)

    tornado.ioloop.IOLoop.current().run_sync(test)


if __name__ == "__main__":
    main()
