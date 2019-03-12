# coding: utf-8
#

import subprocess
from concurrent.futures import ThreadPoolExecutor

import requests
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
        self._procs = []

    def __repr__(self):
        return "{udid}: {name} {product}".format(udid=self.udid, name=self.name, product=self.product)

    def run_webdriveragent(self):
        """
        UDID=$(idevice_id -l)
        UDID=${UDID:?}
        xcodebuild -project WebDriverAgent.xcodeproj \
            -scheme WebDriverAgentRunner WebDriverAgentRunner id=$(idevice_id -l) test
        """
        self.run_background(['xcodebuild', '-project', 'WebDriverAgent.xcodeproj',
                             '-scheme', 'WebDriverAgentRunner', 'WebDriverAgentRunner',
                             'id='+self.udid, 'test'], cwd='Appium-WebDriverAgent')
        self._wda_port = 8100
        self._mjpeg_port = 9100
        self.run_background(["iproxy", "8100", str(self._wda_port)])
        self.run_background(["iproxy", "9100", str(self._mjpeg_port)])

        self.wait_until_ready()

    def run_background(self, *args, **kwargs):
        p = subprocess.Popen(*args, **kwargs)
        self._procs.append(p)

    def wait_until_ready(self, timeout: float = 60.0):
        for p in self._procs:
            print(p.poll())
        try:
            ret = requests.get(
                "http://localhost:{}/status".format(self._wda_port)).json()
            print(ret)
        except requests.ConnectionError:
            pass


def main():
    async def test():
        t = Tracker()
        idevices = {}
        async for event in t.track_device():
            logger.debug("Event: %s", event)
            if event.present:
                idevices[event.udid] = d = IDevice(event.udid)
                d.run_webdriveragent()
            else:
                idevices[event.udid].terminate()

    tornado.ioloop.IOLoop.current().run_sync(test)


if __name__ == "__main__":
    main()
