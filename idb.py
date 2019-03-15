# coding: utf-8
#
# require: python >= 3.6

import json
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
                yield DeviceEvent(True, udid)

            for udid in gones:
                yield DeviceEvent(False, udid)
            await gen.sleep(1)


def track_devices():
    t = Tracker()
    return t.track_devices()


async def nop_callback(*args, **kwargs):
    pass


class IDevice(object):
    def __init__(self, udid: str):
        self.__udid = udid
        self.name = udid2name(udid)
        self.product = udid2product(udid)
        self._stopped = False
        self._procs = []
        self._wda_proxy_port = None
        self._wda_proxy_proc = None

    @property
    def udid(self) -> str:
        return self.__udid

    @property
    def public_port(self):
        return self._wda_proxy_port

    def stop(self):
        self._stopped = True

    def __repr__(self):
        return "[{udid}:{name}-{product}]".format(
            udid=self.udid[:5] + ".." + self.udid[-2:],
            name=self.name,
            product=self.product)

    def __str__(self):
        return repr(self)

    async def run_wda_forever(self, callback=None):
        """
        Args:
            callback
        """
        # wda_fail_cnt = 0
        callback = callback or nop_callback
        while not self._stopped:
            await callback("run")
            start = time.time()
            ok = await self.run_webdriveragent()
            if not ok:
                self.destroy()
                if time.time() - start < 5:
                    logger.error("%s WDA unable to start", self)
                    break
                logger.warning("%s wda started failed, retry after 60s", self)
                await gen.sleep(60)
                continue

            logger.info("%s wda lanuched", self)
            # check /status every 30s
            await callback("ready")

            fail_cnt = 0
            while not self._stopped:
                if await self.wda_status():
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
        await callback("offline")
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

        cmd = [
            'xcodebuild', '-project',
            'ATX-WebDriverAgent/WebDriverAgent.xcodeproj', '-scheme',
            'WebDriverAgentRunner', "-destination", 'id=' + self.udid, 'test'
        ]
        self.run_background(
            cmd, stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT)  # cwd='Appium-WebDriverAgent')
        self._wda_port = freeport.get()
        self._mjpeg_port = freeport.get()
        self.run_background(
            ["iproxy", str(self._wda_port), "8100", self.udid], silent=True)
        self.run_background(
            ["iproxy", str(self._mjpeg_port), "9100", self.udid], silent=True)
        self.restart_wda_proxy()
        return await self.wait_until_ready()

    def run_background(self, *args, **kwargs):
        if kwargs.pop("silent", False):
            kwargs['stdout'] = subprocess.DEVNULL
            kwargs['stderr'] = subprocess.DEVNULL
        logger.debug("exec: %s", subprocess.list2cmdline(args[0]))
        p = subprocess.Popen(*args, **kwargs)
        self._procs.append(p)

    def restart_wda_proxy(self):
        if self._wda_proxy_proc:
            self._wda_proxy_proc.terminate()
        self._wda_proxy_port = freeport.get()
        self._wda_proxy_proc = subprocess.Popen([
            "node", "wdaproxy.js", "-p", str(self._wda_proxy_port),
            "--wda-url", "http://localhost:{}".format(self._wda_port),
            "--mjpeg-url", "http://localhost:{}".format(self._mjpeg_port)])  # yapf: disable

    async def wait_until_ready(self, timeout: float = 60.0):
        """
        Returns:
            bool
        """
        deadline = time.time() + timeout
        while time.time() < deadline and not self._stopped:
            quited = any([p.poll() is not None for p in self._procs])
            if quited:
                return False
            if await self.wda_status():
                return True
            await gen.sleep(1)
        return False

    async def restart_wda(self):
        self.destroy()
        return await self.run_webdriveragent()

    @property
    def wda_device_url(self):
        return "http://localhost:{}".format(self._wda_port)

    async def wda_status(self):
        """
        Returns:
            bool
        """
        try:
            request = httpclient.HTTPRequest(
                self.wda_device_url + "/status",
                connect_timeout=3,
                request_timeout=15)
            client = httpclient.AsyncHTTPClient()
            resp = await client.fetch(request)
            json.loads(resp.body)
            # logger.debug("wda status: %s", resp.body)
            return True
        except httpclient.HTTPError as e:
            logger.debug("request wda/status error: %s", e)
            return False
        except ConnectionResetError:
            logger.debug("%s waiting for wda", self)
            return False
        except Exception as e:
            logger.warning("ping wda unknown error: %s %s", type(e), e)
            return False

    async def wda_healthcheck(self):
        client = httpclient.AsyncHTTPClient()
        await client.fetch(self.wda_device_url + "/wda/healthcheck")

    def destroy(self):
        for p in self._procs:
            p.terminate()
        self._procs = []


if __name__ == "__main__":
    # main()
    pass
