# atxserver2-ios-provider
Apple device provider for atxserver2. iOS真机管理

## Requirements
- Python >= 3.6
- WebDriverAgent(appium)

[Appium 1.9.0](https://testerhome.com/topics/16235) 在WDA中新增了一个 mjpegServer，这个用来做屏幕同步感觉很方便。

所以这里的WebDriverAgent我们使用了appium修改的

## Install
安装libimobiledevice工具包

```bash
brew uninstall --ignore-dependencies libimobiledevice
brew uninstall --ignore-dependencies usbmuxd
brew install --HEAD usbmuxd
brew unlink usbmuxd
brew link usbmuxd
brew install --HEAD libimobiledevice
brew install ideviceinstaller
brew link --overwrite ideviceinstaller
```

下载安装atxserver2-ios-provider, 并初始化其中的ATX-WebDriverAgent

```bash
# clone code and init submodule(appium WebDriverAgent)
git clone https://github.com/openatx/atxserver2-ios-provider --recursive
cd atxserver2-ios-provider
# run the following commands if you forgot --recursive
# git submodule init
# git submodule update

# initialize atx WebDriverAgent (fork of appium webdriveragent)
cd ATX-WebDriverAgent
brew install carthage
./Scripts/bootstrap.sh
```

然后找台手机接到苹果电脑上。
按照这个文档<https://testerhome.com/topics/7220> 对WebDriverAgent项目进行下设置。
有条件的话还是弄一个苹果的开发者证书比较方便。个人可以用免费的证书(需要修改BundleID)，另外隔几天证书就会过期。

每台设备都需要先用xcode，注册下，能跑起来WDA test，弄完之后接着往下看。

命令行
```bash
# export USER_PORT=8100 # WDA监听端口
# export MJPEG_SERVER_PORT=9100 # MJPEG-SERVER端口

# 解锁keychain，防止签名权限不足问题
security unlock-keychain ~/Library/Keychains/login.keychain
# security unlock-keychain -p $PASSWORD ~/Library/Keychains/login.keychain

# test if wda can run?
# xcodebuild -project WebDriverAgent.xcodeproj \
#            -scheme WebDriverAgentRunner \
#            -destination 'platform=iOS Simulator,name=iPhone 6' \
#            test

SERVER_URL="http://localhost:4000" # 这里修改成atxserver2的地址
python3 main.py -s $SERVER_URL
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
