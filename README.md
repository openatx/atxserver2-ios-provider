# atxserver2-ios-provider
Apple device provider for atxserver2. iOS真机管理

## Requirements
- Python >= 3.6
- WebDriverAgent(appium)
- NodeJS 8

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
git clone https://github.com/openatx/atxserver2-ios-provider
cd atxserver2-ios-provider

# install dependencies
pip3 install -r requirements.txt
npm install # 如遇到错误,请检查是否是NodeJS 8
```
* 启动方式1：使用 xcode 工程自动启动 WebDriverAgent

WebDriverAgent的初始化。目前项目中已有的WebDriverAgent有点老了。推荐使用appium的Fork的版本。

```bash
brew install carthage

git clone https://github.com/appium/WebDriverAgent Appium-WebDriverAgent
cd Appium-WebDriverAgent && ./Scripts/bootstrap.sh
open WebDriverAgent.xcodeproj
```

然后找台手机接到苹果电脑上。
按照这个文档<https://testerhome.com/topics/7220> 对WebDriverAgent项目进行下设置。
有条件的话还是弄一个苹果的开发者证书比较方便。个人可以用免费的证书(需要修改BundleID)，另外隔几天证书就会过期。

每台设备都需要先用xcode，注册下，能跑起来WDA test，弄完之后接着往下看。

命令行
```bash
# export USER_PORT=8100 # WDA监听端口
# export MJPEG_SERVER_PORT=9100 # MJPEG-SERVER端口

# 避免命令行运行出错，运行一次即可
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer

# 解锁keychain，防止签名权限不足问题
security unlock-keychain ~/Library/Keychains/login.keychain
# security unlock-keychain -p $PASSWORD ~/Library/Keychains/login.keychain

# test if wda can run?
# xcodebuild -project WebDriverAgent.xcodeproj \
#            -scheme WebDriverAgentRunner \
#            -destination 'platform=iOS Simulator,name=iPhone 6' \
#            test

SERVER_URL="http://localhost:4000" # 这里修改成atxserver2的地址
WDA_DIRECTORY="./Appium-WebDriverAgent" # WDA项目地址
python3 main.py -s $SERVER_URL -W $WDA_DIRECTORY
```

* 启动方式2：手动通过外部程序启动

如果使用 tidevice 等别的方式手动启动 wda ，启动命令需加上 `--manually-start-wda` 阻止 atx 启动 wda。

* 启动方式3：自动通过 [tidevice](https://github.com/alibaba/taobao-iphone-device) 启动

好处：只要事先在手机上装好 wda ，电脑就可以不用再弄 wda 了。

```bash
pip3 install -U "tidevice[openssl]" # 安装 tidevice ，python 版本需要 > 3.6。详情参考 https://github.com/alibaba/taobao-iphone-device

# 确认 tidevice 可用
tidevice -v

# 启动应用
SERVER_URL="http://localhost:4000" # 这里修改成atxserver2的地址
WDA_BUNDLE_PATTERN="*WebDriverAgent*" # WDA bundle id 通配符
python3 main.py -s $SERVER_URL --use-tidevice --wda-bundle-pattern $WDA_BUNDLE_PATTERN
```

会自动通过 `tidevice -u <UUID> wdaproxy -B <WDA_BUNDLE_PATTERN> --port 0` 在连上设备后启动设备上的 wda 





## Developer 开发人员备注
appium-WebDriverAgent一些[API说明](WDA-API.md)

## 设备设置
参考: http://docs.quamotion.mobi/cloud/on-site/connecting-ios-devices/

2022-01-05：目前已支持模拟器，可以直接使用无需安装 wda 。感谢 [@Vancheung](https://github.com/Vancheung) 提供的 [PR](https://github.com/openatx/atxserver2-ios-provider/pull/29)

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

## References
- https://iphonedevwiki.net/index.php/SSH_Over_USB
- usbmux client

    - nodejs: https://github.com/DeMille/node-usbmux
    - python: https://github.com/nabla-c0d3/multcprelay

# LICENSE
[MIT](LICENSE)
