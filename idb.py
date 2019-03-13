# coding: utf-8
#
# require: python >= 3.6

import subprocess
import time
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor

import requests
from tornado.ioloop import IOLoop
from logzero import logger
from tornado import gen, httpclient
from tornado.concurrent import run_on_executor

from freeport import freeport

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

    async def track_devices(self):
        while True:
            backs, gones = await self.update()
            for udid in backs:
                logger.info("Back online: %s", udid)
                yield DeviceEvent(True, udid)

            for udid in gones:
                logger.info("Went offline: %s", udid)
                yield DeviceEvent(False, udid)
            await gen.sleep(1)


def track_devices():
    t = Tracker()
    return t.track_devices()


class IDevice(object):
    def __init__(self, udid):
        self.udid = udid
        self.name = udid2name(udid)
        self.product = udid2product(udid)
        self._stopped = False
        self._procs = []

    def stop(self):
        self._stopped = True

    def __repr__(self):
        return "{udid}: {name} {product}".format(
            udid=self.udid, name=self.name, product=self.product)

    async def run_wda_forever(self, callback=None):
        """
        Args:
            callback
        """
        # wda_fail_cnt = 0
        callback = callback or (lambda event: None)
        while not self._stopped:
            callback("run")
            ok = await self.run_webdriveragent()
            if not ok:
                logger.warning("wda started failed, retry after 10s")
                self.destroy()
                await gen.sleep(10)
                continue

            # check /status every 30s
            fail_cnt = 0
            while not self._stopped:
                callback("ready")
                if await self.ping_wda():
                    if fail_cnt != 0:
                        logger.info("wda ping recovered")
                        fail_cnt = 0
                    await gen.sleep(30)
                else:
                    fail_cnt += 1
                    logger.warning("wda ping error: %d", fail_cnt)
                    if fail_cnt > 3:
                        logger.warning(
                            "ping wda fail too many times, restart wda")
                        break
                    await gen.sleep(10)
            self.destroy()
        self.destroy()  # destroy twice to make sure no process left

    async def run_webdriveragent(self):
        """
        UDID=$(idevice_id -l)
        UDID=${UDID:?}
        xcodebuild -project WebDriverAgent.xcodeproj \
            -scheme WebDriverAgentRunner WebDriverAgentRunner id=$(idevice_id -l) test
        
        Raises:
            RuntimeError
        """
        if self._procs:
            raise RuntimeError("should call destroy before run_webdriveragent")

        self.run_background([
            'xcodebuild', '-project', 'WebDriverAgent.xcodeproj', '-scheme',
            'WebDriverAgentRunner', 'WebDriverAgentRunner', 'id=' + self.udid,
            'test'
        ],
                            cwd='Appium-WebDriverAgent')
        self._wda_port = freeport.get()
        self._mjpeg_port = freeport.get()
        self.run_background(["iproxy", "8100", str(self._wda_port)])
        self.run_background(["iproxy", "9100", str(self._mjpeg_port)])

        return self.wait_until_ready()

    def run_background(self, *args, **kwargs):
        p = subprocess.Popen(*args, **kwargs)
        self._procs.append(p)

    async def wait_until_ready(self, timeout: float = 60.0):
        """
        Returns:
            bool
        """
        deadline = time.time() + timeout
        while time.time() < deadline and not self._stopped:
            quited = any([p.poll() is None for p in self._procs])
            if quited:
                return False
            if await self.ping_wda():
                return True
            await gen.sleep(1)
        return False

    async def restart_wda(self):
        self.destroy()
        return await self.run_webdriveragent()

    async def ping_wda(self):
        """
        Returns:
            bool
        """
        try:
            url = "http://localhost:{}/status".format(self._wda_port)
            request = httpclient.HTTPRequest(
                url, connect_timeout=3, request_timeout=15)
            client = httpclient.AsyncHTTPClient()
            resp = await client.fetch(request)
            logger.debug("wda status: %s", resp.response.body)
            return True
        except httpclient.HTTPError as e:
            logger.debug("request wda/status error: %s", e)
            return False

    def destroy(self):
        for p in self._procs:
            p.terminate()
        self._procs = []


def main():
    idevices = {}

    async def test():
        print("test")
        async for event in track_devices():
            logger.debug("Event: %s", event)
            if event.present:
                idevices[event.udid] = d = IDevice(event.udid)

                # start webdriveragent
                def callback(status: str):
                    if status == "run":
                        print(event.udid, "run")
                    elif status == "ready":
                        print(event.udid, "ready")

                IOLoop.current().spawn_callback(d.run_wda_forever, callback)
            else:
                idevices[event.udid].stop()
                idevices.pop(event.udid)

    try:
        IOLoop.current().run_sync(test)
    except KeyboardInterrupt:
        IOLoop.current().stop()
        for d in idevices.values():
            d.destroy()


if __name__ == "__main__":
    main()
