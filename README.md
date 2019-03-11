# atxserver2-ios-provider
Apple device provider for atxserver2

Not implemented yet.

## Requirements
- Python >= 3.6
- WebDriverAgent(appium)

[Appium 1.9.0](https://testerhome.com/topics/16235) 在WDA中新增了一个 mjpegServer，这个用来做屏幕同步感觉很方便。

所以这里的WebDriverAgent我们使用了appium修改的

## Install
```bash
# clone code and init submodule(appium WebDriverAgent)
git clone https://github.com/openatx/atxserver2-ios-provider --recursive

# initialize appium WebDriverAgent
cd atxserver2-ios-provider/appium-wda
./Scripts/bootstrap.sh

export USER_PORT=8100 # WDA监听端口
export MJPEG_SERVER_PORT=9100 # MJPEG-SERVER端口

xcodebuild -project WebDriverAgent.xcodeproj \
           -scheme WebDriverAgentRunner \
           -destination 'platform=iOS Simulator,name=iPhone 6' \
           test
```

## Developer 开发人员备注
appium-WebDriverAgent一些[API说明](WDA-API.md)

## 设备设置
参考: http://docs.quamotion.mobi/cloud/on-site/connecting-ios-devices/

### 连接iOS设备
1. 确保设备已经解锁
2. 使用数据线将苹果手机连接到电脑上（Mac）
3. 当出现`是否信任该设备时`选择`是`

### 设备开启自动化
1. 按下HOME -> 设置(Settings) -> 开发者(Developer) -> `Enable UI Automation`
2. 回到 设置(Settings) -> Safari浏览器 -> 翻到最后 高级(Advanced) -> 打开 Web检查器(Web inspector)
3. 设置(Settings) -> 通用 -> 设备管理 -> 点击开发者应用中的栏目 

### 持续运行的设备设置
默认情况下设备会锁屏的，而当设备锁屏的时候，就自动化不了了。最简单的一个办法就是保持设备常亮

1. Home -> 设置(Settings) -> 显示与亮度(Settings & Brightness)
2. 亮度调到低（可以是最低）
3. 自动锁定(Auto-Lock) 设置为 永不（Never）


# LICENSE
[MIT](LICENSE)
