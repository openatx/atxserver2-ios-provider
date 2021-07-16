# coding: utf-8
#
# require: python >= 3.6

import base64
import json
import os
import re
import sys
import subprocess
import time
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Callable

import tornado
import requests
from logzero import logger
from tornado import gen, httpclient, locks
from tornado.concurrent import run_on_executor
from tornado.ioloop import IOLoop

from freeport import freeport
from tidevice import Device
from tidevice._usbmux import Usbmux

DeviceEvent = namedtuple('DeviceEvent', ['present', 'udid'])
um = Usbmux()


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
    devices = um.device_list()
    udids = [device.udid for device in devices]
    udid_sim = runcommand('xcrun', 'simctl', 'list', 'devices').splitlines()
    p = re.compile(r'[(](.*?)[)]', re.S)
    udids.extend([re.findall(p, i)[-2] for i in udid_sim if 'Booted' in i])
    return udids


def udid2name(udid: str) -> str:
    devices = um.device_list()
    for device in devices:
        if device.udid == udid:
            d = Device(device.udid)
            return d.get_value(no_session=True).get('DeviceName')
    if not devices:  # 模拟器
        udid_sim = runcommand('xcrun', 'simctl', 'list', 'devices').splitlines()
        for i in udid_sim:
            if udid in i:
                return i[:i.index('(')].strip()                
    return "Unknown"    


def udid2product(udid):
    """
    See also: https://www.theiphonewiki.com/wiki/Models
    """
    pt = ""
    devices = um.device_list()
    for device in devices:
        if device.udid == udid:
            d = Device(device.udid)
            pt = d.get_value(no_session=True).get('ProductType')
    models = {
        "iPhone5,1": "iPhone 5",
        "iPhone5,2": "iPhone 5",
        "iPhone5,3": "iPhone 5c",
        "iPhone5,4": "iPhone 5c",
        "iPhone6,1": "iPhone 5s",
        "iPhone6,2": "iPhone 5s",
        "iPhone7,1": "iPhone 6 Plus",
        "iPhone7,2": "iPhone 6",
        "iPhone8,1": "iPhone 6s",
        "iPhone8,2": "iPhone 6s Plus",
        "iPhone8,4": "iPhone SE",
        "iPhone9,1": "iPhone 7",  # Global
        "iPhone9,2": "iPhone 7 Plus",  # Global
        "iPhone9,3": "iPhone 7",  # GSM
        "iPhone9,4": "iPhone 7 Plus",  # GSM
        "iPhone10,1": "iPhone 8",  # Global
        "iPhone10,2": "iPhone 8 Plus",  # Global
        "iPhone10,3": "iPhone X",  # Global
        "iPhone10,4": "iPhone 8",  # GSM
        "iPhone10,5": "iPhone 8 Plus",  # GSM
        "iPhone10,6": "iPhone X",  # GSM
        "iPhone11,8": "iPhone XR",
        "iPhone11,2": "iPhone XS",
        "iPhone11,4": "iPhone XS Max",
        "iPhone11,6": "iPhone XS Max",
        "iPhone12,1": "iPhone 11",
        "iPhone12,3": "iPhone 11 Pro",
        "iPhone12,5": "iPhone 11 Pro Max",
        "iPhone12,8": "iPhone SE 2nd",
        "iPhone13,1": "iPhone 12 mini",
        "iPhone13,2": "iPhone 12",
        "iPhone13,3": "iPhone 12 Pro",
        "iPhone13,4": "iPhone 12 Pro Max",
        "iPhone14,2": "iPhone 13 Pro",
        "iPhone14,3": "iPhone 13 Pro Max",        
        "iPhone14,4": "iPhone 13 mini",        
        "iPhone14,5": "iPhone 13",                
        # simulator
        "i386": "iPhone Simulator",
        "x86_64": "iPhone Simulator",
    }
    if not pt:
        pt = "i386"
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


class WDADevice(object):
    """
    Example usage:

    lock = locks.Lock() # xcodebuild test is not support parallel run
    
    async def callback(device: WDADevice, status, info=None):
        pass

    d = WDADevice("xxxxxx-udid-xxxxx", lock, callback)
    d.start()
    await d.stop()
    """

    status_preparing = "preparing"
    status_ready = "ready"
    status_fatal = "fatal"

    def __init__(self, udid: str, lock: locks.Lock, callback):
        """
        Args:
            callback: function (str, dict) -> None
        
        Example callback:
            callback("update", {"ip": "1.2.3.4"})
        """
        self.__udid = udid
        self.name = udid2name(udid)
        self.product = udid2product(udid)
        self.wda_directory = "./ATX-WebDriverAgent"
        self._procs = []
        self._wda_proxy_port = None
        self._wda_proxy_proc = None
        self._lock = lock  # only allow one xcodebuild test run
        self._finished = locks.Event()
        self._stop = locks.Event()
        self._callback = partial(callback, self) or nop_callback
        self.manually_start_wda = False
        self.use_tidevice = False
        self.wda_bundle_pattern = "*WebDriverAgent*"


    @property
    def udid(self) -> str:
        return self.__udid

    @property
    def public_port(self):
        return self._wda_proxy_port

    def __repr__(self):
        return "[{udid}:{name}-{product}]".format(udid=self.udid[:5] + ".." +
                                                  self.udid[-2:],
                                                  name=self.name,
                                                  product=self.product)

    def __str__(self):
        return repr(self)

    def start(self):
        """ start wda process and keep it running, until wda stopped too many times or stop() called """
        self._stop.clear()
        IOLoop.current().spawn_callback(self.run_wda_forever)

    async def stop(self):
        """ stop wda process """
        if self._stop.is_set():
            raise RuntimeError(self, "WDADevice is already stopped")
        self._stop.set()  # no need await
        logger.debug("%s waiting for wda stopped ...", self)
        await self._finished.wait()
        logger.debug("%s wda stopped!", self)
        self._finished.clear()

    async def run_wda_forever(self):
        """
        Args:
            callback
        """
        wda_fail_cnt = 0
        while not self._stop.is_set():
            await self._callback(self.status_preparing)
            start = time.time()
            ok = await self.run_webdriveragent()
            if not ok:
                self.destroy()

                wda_fail_cnt += 1
                if wda_fail_cnt > 3:
                    logger.error("%s Run WDA failed. -_-!", self)
                    break

                if time.time() - start < 3.0:
                    logger.error("%s WDA unable to start", self)
                    break
                logger.warning("%s wda started failed, retry after 10s", self)
                if not await self._sleep(10):
                    break
                continue

            wda_fail_cnt = 0
            logger.info("%s wda lanuched", self)

            # wda_status() result stored in __wda_info
            await self._callback(self.status_ready, self.__wda_info)
            await self.watch_wda_status()

        await self._callback(self.status_fatal)
        self.destroy()  # destroy twice to make sure no process left
        self._finished.set()  # no need await

    def destroy(self):
        logger.debug("terminate wda processes")
        for p in self._procs:
            p.terminate()
        self._procs = []

    async def _sleep(self, timeout: float):
        """ return false when sleep stopped by _stop(Event) """
        try:
            timeout_timestamp = IOLoop.current().time() + timeout
            await self._stop.wait(timeout_timestamp)  # wired usage
            return False
        except tornado.util.TimeoutError:
            return True

    async def watch_wda_status(self):
        """
        check WebDriverAgent all the time
        """
        # check wda_status every 3
        
        
        fail_cnt = 0
        last_ip = self.device_ip
        while not self._stop.is_set():
            if await self.wda_status():
                if fail_cnt != 0:
                    logger.info("wda ping recovered")
                    fail_cnt = 0
                if last_ip != self.device_ip:
                    last_ip = self.device_ip
                    await self._callback(self.status_ready, self.__wda_info)
                await self._sleep(60)
                logger.debug("%s is fine", self)
            else:
                fail_cnt += 1
                logger.warning("%s wda ping error: %d", self, fail_cnt)
                if fail_cnt > 3:
                    logger.warning("ping wda fail too many times, restart wda")
                    break
                await self._sleep(10)

        self.destroy()

    @property
    def device_ip(self):
        """ get current device ip """
        if not self.__wda_info:
            return None
        try:
            return self.__wda_info['value']['ios']['ip']
        except IndexError:
            return None

    async def run_webdriveragent(self) -> bool:
        """
        UDID=$(idevice_id -l)
        UDID=${UDID:?}
        xcodebuild -project WebDriverAgent.xcodeproj \
            -scheme WebDriverAgentRunner WebDriverAgentRunner id=$(idevice_id -l) test

        Raises:
            RuntimeError
        """
        if self._procs:
            self.destroy() # hotfix
            #raise RuntimeError("should call destroy before run_webdriveragent", self._procs)

        async with self._lock:
            # holding lock, because multi wda run will raise error
            # Testing failed:
            #    WebDriverAgentRunner-Runner.app encountered an error (Failed to install or launch the test
            #    runner. (Underlying error: Only directories may be uploaded. Please try again with a directory
            #    containing items to upload to the application_s sandbox.))
            self._wda_port = freeport.get()
            self._mjpeg_port = freeport.get()
            cmd = [
                'xcodebuild', '-project',
                os.path.join(self.wda_directory, 'WebDriverAgent.xcodeproj'),
                '-scheme', 'WebDriverAgentRunner', "-destination",
                'id=' + self.udid, 'test'
            ]
            if "Simulator" in self.product:  # 模拟器
                cmd.extend([
                    'USE_PORT=' + str(self._wda_port),
                    'MJPEG_SERVER_PORT=' + str(self._mjpeg_port),
                ])

            if os.getenv("TMQ") == "true":
                cmd = ['tins', '-u', self.udid, 'xctest']

            if self.manually_start_wda:
                logger.info("Got param --manually-start-wda , will not launch wda process")
            elif self.use_tidevice:
                # 明确使用 tidevice 命令启动 wda
                logger.info("Got param --use-tidevice , use tidevice to launch wda")
                tidevice_cmd = ['tidevice', '-u', self.udid, 'xctest', '-B', self.wda_bundle_pattern]
                self.run_background(tidevice_cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.STDOUT)
            else:
                self.run_background(
                    cmd, stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT)  # cwd='Appium-WebDriverAgent')
            if "Simulator" not in self.product:
                self.run_background(
                    ["tidevice", '-u', self.udid, 'relay',
                     str(self._wda_port), "8100"],
                    silent=True)
                self.run_background(
                    ["tidevice", '-u', self.udid, 'relay',
                     str(self._mjpeg_port), "9100"],
                    silent=True)

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
        logger.debug("restart wdaproxy with port: %d", self._wda_proxy_port)
        self._wda_proxy_proc = subprocess.Popen([
            sys.executable, "-u", "wdaproxy-script.py", 
            "-p", str(self._wda_proxy_port),
            "--wda-url", "http://localhost:{}".format(self._wda_port),
            "--mjpeg-url", "http://localhost:{}".format(self._mjpeg_port)],
            stdout=subprocess.DEVNULL)  # yapf: disable

    async def wait_until_ready(self, timeout: float = 60.0) -> bool:
        """
        Returns:
            bool
        """
        deadline = time.time() + timeout
        while time.time() < deadline and not self._stop.is_set():
            quited = any([p.poll() is not None for p in self._procs])
            if quited:
                logger.warning("%s process quit %s", self,
                               [(p.pid, p.poll()) for p in self._procs])
                return False
            if await self.wda_status():
                return True
            await self._sleep(1)
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
            dict or None
        """
        try:
            request = httpclient.HTTPRequest(self.wda_device_url + "/status",
                                             connect_timeout=3,
                                             request_timeout=15)
            client = httpclient.AsyncHTTPClient()
            resp = await client.fetch(request)
            info = json.loads(resp.body)
            self.__wda_info = info
            return info
        except httpclient.HTTPError as e:
            logger.debug("%s request wda/status error: %s", self, e)
            return None
        except (ConnectionResetError, ConnectionRefusedError):
            logger.debug("%s waiting for wda", self)
            return None
        except Exception as e:
            logger.warning("%s ping wda unknown error: %s %s", self, type(e),
                           e)
            return None

    async def wda_screenshot_ok(self):
        """
        Check if screenshot is working
        Returns:
            bool
        """
        try:
            request = httpclient.HTTPRequest(self.wda_device_url +
                                             "/screenshot",
                                             connect_timeout=3,
                                             request_timeout=15)
            client = httpclient.AsyncHTTPClient()
            resp = await client.fetch(request)
            data = json.loads(resp.body)
            raw_png_data = base64.b64decode(data['value'])
            png_header = b"\x89PNG\r\n\x1a\n"
            if not raw_png_data.startswith(png_header):
                return False
            return True
        except Exception as e:
            logger.warning("%s wda screenshot error: %s", self, e)
            return False

    async def wda_session_ok(self):
        """
        check if session create ok
        """
        info = await self.wda_status()
        if not info:
            return False
        #if not info.get("sessionId"): # the latest wda /status has no sessionId
        #    return False
        return True

    async def is_wda_alive(self):
        logger.debug("%s check /status", self)
        if not await self.wda_session_ok():
            return False

        logger.debug("%s check /screenshot", self)
        if not await self.wda_screenshot_ok():
            return False

        return True

    async def wda_healthcheck(self):
        client = httpclient.AsyncHTTPClient()

        if not await self.is_wda_alive():
            logger.warning("%s check failed -_-!", self)
            await self._callback(self.status_preparing)
            if not await self.restart_wda():
                logger.warning("%s wda recover in healthcheck failed", self)
                return
        else:
            logger.debug("%s all check passed ^_^", self)

        await client.fetch(self.wda_device_url + "/wda/healthcheck")


if __name__ == "__main__":
    # main()
    pass
