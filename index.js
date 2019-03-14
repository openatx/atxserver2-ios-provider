/*
Libs

- https://github.com/websockets/ws
- https://github.com/HenningM/express-ws
- https://www.npmjs.com/package/websocket-stream
- https://www.npmjs.com/package/mjpeg-consumer
- https://github.com/request/request
*/
const express = require("express")
const proxy = require("express-http-proxy")
const request = require("request")
const cors = require("cors")
const program = require("commander")

const MjpegConsumer = require('mjpeg-consumer')
const websocketStream = require('websocket-stream/stream');


function makeApp(wdaServerUrl, mjpegServerUrl) {
    const app = express()
    require('express-ws')(app, null, {
        perMessageDeflate: false,
    });
    app.use(cors())

    app.use((err, req, res, next) => {
        // log the error...
        res.sendStatus(err.httpStatusCode).json(err)
    })

    app.get("/error", (req, res) => {
        throw Error("hello")
    })

    app.get("/about", (req, res) => {
        res.send("Express WebDriverAgent")
    })

    let clientCount = 0
    let mjpegStream = null

    // mjpeg stream to websocket stream
    app.ws('/screen', function (ws, req) {
        const stream = websocketStream(ws, {
            binary: true
        })

        clientCount += 1
        if (clientCount === 1) {
            console.log(`http://10.240.173.218:${mjpegServerPort}`)
            let req = request(mjpegServerUrl)
                .on("error", () => {
                    console.log("request error")
                })

            const consumer = new MjpegConsumer()
            mjpegStream = req.pipe(consumer).on("close", () => {
                console.log("request finish")
            })
        }

        mjpegStream.pipe(stream)
            .on('error', (e) => {
                console.log(e)
            })

        ws.on('close', () => {
            clientCount -= 1
            mjpegStream.unpipe(stream)
            if (clientCount === 0) {
                mjpegStream.destroy()
            }
        })
    });

    app.use("/", proxy(wdaServerUrl))
    return app
}


program
    .version("0.1.0")
    .option("-p, --port <port>", "listen port", parseInt)
    .option("--wda-url <wdaUrl>", "wda server url")
    .option("--mjpeg-url <mjpegUrl>", "mjpeg server url")
    .parse(process.argv)

console.log(program.port)

const app = makeApp(program.wdaUrl, program.mjpegUrl)
app.listen(program.port, () => {
    console.log("Listen on port", program.port)
})