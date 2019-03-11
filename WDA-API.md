## WebDriverAgent HTTP接口部分文档
参考来源

- [FBSessionCommands.m](https://github.com/appium/webdriveragent/blob/master/WebDriverAgentLib/Commands/FBSessionCommands.m)
- [FBCustomCommands.m](https://github.com/appium/webdriveragent/blob/master/WebDriverAgentLib/Commands/FBCustomCommands.m)
- [FBOrientationCommands.m](https://github.com/appium/webdriveragent/blob/master/WebDriverAgentLib/Commands/FBOrientationCommands.m)

```bash
# 获取sessionId
$ http GET :8100/status # 获取sessionId
{
    "sessionId": "${sessionId} ...."
}

# 获取appium配置
$ http GET :8100/session/${sessionId}/appium/settings
{
    "sessionId": "89B7A864-2BC2-4A03-B0C9-FA03601980C0", 
    "status": 0, 
    "value": {
        "elementResponseAttributes": "type,label", 
        "mjpegScalingFactor": 100, 
        "mjpegServerFramerate": 15, 
        "mjpegServerScreenshotQuality": 25, 
        "screenshotQuality": 1, 
        "shouldUseCompactResponses": true
    }
}

# 更新appium设置
$ http POST :8100/session/89B7A864-2BC2-4A03-B0C9-FA03601980C0/appium/settings <<< '{"settings": {"mjpegServerFramerate": 15}}'
# 内容同 GET /appium/settings 一致，所以省略

# 模拟HOME
$ http POST :8100/wda/homescreen
{
    "sessionId": "89B7A864-2BC2-4A03-B0C9-FA03601980C0", 
    "status": 0
}

# 获取当前应用信息
$ http GET :8100/wda/activeAppInfo
{
    "sessionId": "565054D0-16F3-4600-B980-C28CF83F477E", 
    "status": 0, 
    "value": {
        "bundleId": "com.apple.mobilesafari", 
        "name": "", 
        "pid": 86098
    }
}

# 获取电池信息
$ http GET :8100/session/${sessionId}/wda/batteryInfo
# 这里level为什么是-1，我也不太清楚，可能是充满了的意思吧
{
    "sessionId": "565054D0-16F3-4600-B980-C28CF83F477E", 
    "status": 0, 
    "value": {
        "level": -1, 
        "state": 0
    }
}

# 获取剪贴板内容 setPasteboard
$ http POST :8100/session/${sessionId}/wda/getPasteboard
# 这里的输出是base64, 解析出来就是 https://cn.bing.com
{
    "sessionId": "565054D0-16F3-4600-B980-C28CF83F477E", 
    "status": 0, 
    "value": "aHR0cHM6Ly9jbi5iaW5nLmNvbQ=="
}

# 设置剪贴板内容 setPasteboard
$ http POST :8100/session/${sessionId}/wda/setPasteboard <<< '{"content": "aHR0cHM6Ly9naXRodWIuY29tCg=="}'
# 这里传过去的内容也必须是base64编码
{
    "sessionId": "565054D0-16F3-4600-B980-C28CF83F477E", 
    "status": 0
}

# 获取屏幕scale和statusbar的大小
$ http GET :8100/session/565054D0-16F3-4600-B980-C28CF83F477E/wda/screen
{
    "sessionId": "565054D0-16F3-4600-B980-C28CF83F477E", 
    "status": 0, 
    "value": {
        "scale": 2, 
        "statusBarSize": {
            "height": 20, 
            "width": 375
        }
    }
}

# 获取屏幕高度
$ http GET :8100/session/565054D0-16F3-4600-B980-C28CF83F477E/window/size
{
    "sessionId": "565054D0-16F3-4600-B980-C28CF83F477E", 
    "status": 0, 
    "value": {
        "height": 667, 
        "width": 375
    }
}

# 输入内容
$ http POST :8100/session/565054D0-16F3-4600-B980-C28CF83F477E/wda/keys <<< '{"value": ["abcdefg"]}'
# 其中value对应的是一个string list, ["abcdefg"] 其实是跟 ["abc", "defg"] 等价。\b是删除
{
    "status": 0,
}
# 删除3字符 （目前还不清楚全删除的命令是啥）
$ http POST :8100/session/565054D0-16F3-4600-B980-C28CF83F477E/wda/keys <<< '{"value": ["\b\b\b"]}'

# 拖动 时长0.1s
$ http POST :8100/session/565054D0-16F3-4600-B980-C28CF83F477E/wda/dragfromtoforduration <<< '{"fromX": 150, "fromY": 300, "toX": 150, "toY": 0, "duration": 0.1}'
{
    "status": 0,
}

# 点击
$ http POST :8100/session/565054D0-16F3-4600-B980-C28CF83F477E/wda/tap/0 <<< '{"x": 150, "y": 150}'
{
    "status": 0,
}
```