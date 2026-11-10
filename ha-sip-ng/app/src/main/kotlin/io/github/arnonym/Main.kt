package io.github.arnonym

import io.github.arnonym.command.CommandHandler
import io.github.arnonym.config.AnswerMode
import io.github.arnonym.config.AppConfig
import io.github.arnonym.config.GlobalOptions
import io.github.arnonym.config.SipOptions
import io.github.arnonym.config.convertToDouble
import io.github.arnonym.config.convertToInt
import io.github.arnonym.config.loadDotEnv
import io.github.arnonym.event.EventSender
import io.github.arnonym.ha.HaClient
import io.github.arnonym.ha.HaConfig
import io.github.arnonym.ha.TtsConfig
import io.github.arnonym.log.log
import io.github.arnonym.menu.IncomingCallConfig
import io.github.arnonym.mqtt.MqttClient
import io.github.arnonym.sensor.SensorConfig
import io.github.arnonym.sensor.SensorEventHandler
import io.github.arnonym.sensor.SensorUpdater
import io.github.arnonym.sip.Account
import io.github.arnonym.sip.Call
import io.github.arnonym.sip.CallDisposal
import io.github.arnonym.sip.EndpointConfig
import io.github.arnonym.sip.MyAccountConfig
import io.github.arnonym.sip.createEndpoint
import io.github.arnonym.sip.makeCall
import io.github.arnonym.sip.registerCurrentThread
import io.github.arnonym.state.CallRegistry
import io.github.arnonym.yaml.parseYamlToJsonElement
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import org.pjsip.pjsua2.Endpoint
import java.io.File
import java.net.URI
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread
import kotlin.system.exitProcess

private fun loadMenuFromFile(
    fileName: String?,
    sipAccountIndex: Int,
): IncomingCallConfig? {
    if (fileName.isNullOrEmpty()) {
        log(sipAccountIndex, "No file name for incoming call config specified.")
        return null
    }
    return try {
        val content = parseYamlToJsonElement(File(fileName).readText()) as? JsonObject
        log(sipAccountIndex, "Loaded menu for incoming call from \"$fileName\".")
        IncomingCallConfig.fromJson(content)
    } catch (e: Exception) {
        log(sipAccountIndex, "Error loading menu for incoming call: ${e.message}")
        null
    }
}

private fun getCacheDir(rawCacheDir: String): String? {
    if (rawCacheDir.isEmpty()) {
        log(null, "No cache directory configured.")
        return null
    }
    if (!File(rawCacheDir).isDirectory) {
        log(null, "Error: Cache directory not found.")
        return null
    }
    log(null, "Found cache directory '$rawCacheDir'")
    return rawCacheDir
}

private fun logHostnameResolution(
    label: String,
    url: String,
) {
    if (url.isEmpty()) return
    val host =
        try {
            URI(url).host
        } catch (e: Exception) {
            null
        }
    if (host == null) {
        log(null, "Error: could not extract hostname from $label: $url")
        return
    }
    try {
        val ip = java.net.InetAddress.getByName(host).hostAddress
        log(null, "$label hostname $host resolves to $ip")
    } catch (e: Exception) {
        log(null, "Error: could not resolve $label hostname $host: ${e.message}")
    }
}

/** The `SIP<n>_*` accounts that are switched on, in index order, keyed by index. */
private fun enabledAccountConfigs(
    config: AppConfig,
    globalOptions: GlobalOptions,
): Map<Int, MyAccountConfig> =
    config.sipAccounts.mapValues { (index, env) ->
        MyAccountConfig(
            enabled = env.enabled.equals("true", ignoreCase = true),
            index = index,
            idUri = env.idUri,
            registrarUri = env.registrarUri,
            realm = env.realm,
            userName = env.userName,
            password = env.password,
            mode = AnswerMode.getOrElse(env.answerMode, AnswerMode.LISTEN),
            settleTime = convertToDouble(env.settleTime, 1.0),
            incomingCallConfig = loadMenuFromFile(env.incomingCallFile, index),
            options = SipOptions.parse(env.options, index),
            globalOptions = globalOptions,
        )
    }.filterValues { it.enabled }

/** Registers each enabled account with pjsua. The lowest-numbered one becomes the default. */
private fun createAccounts(
    accountConfigs: Map<Int, MyAccountConfig>,
    commandHandler: CommandHandler<Call>,
    eventSender: EventSender,
    haConfig: HaConfig,
    haClient: HaClient,
    sensorUpdater: SensorUpdater,
): Map<Int, Account> =
    accountConfigs.entries.mapIndexed { position, (index, accountConfig) ->
        val account =
            Account(
                config = accountConfig,
                commandHandler = commandHandler,
                eventSender = eventSender,
                haConfig = haConfig,
                haClient = haClient,
                makeDefault = position == 0,
                onRegStateCallback = { accountIndex, code, reason ->
                    sensorUpdater.updateRegistrationStatus(accountIndex, code, reason)
                },
            )
        account.init()
        index to account
    }.toMap()

/** Reads newline-delimited JSON commands from stdin until the stream closes. */
private fun startStdinReader(
    endpoint: Endpoint,
    commandHandler: CommandHandler<Call>,
) {
    thread(isDaemon = true, name = "stdin-command-reader") {
        endpoint.registerCurrentThread()
        System.`in`.bufferedReader().forEachLine { line ->
            if (line.isBlank()) return@forEachLine
            val parsed =
                try {
                    Json.parseToJsonElement(line) as? JsonObject
                } catch (e: Exception) {
                    null
                }
            if (parsed == null) {
                println("Could not deserialize JSON: $line")
                return@forEachLine
            }
            try {
                commandHandler.handleCommand(parsed, null)
            } catch (e: Exception) {
                log(null, "Error handling command: ${e.message}")
            }
        }
    }
}

private fun startCallTicker(
    endpoint: Endpoint,
    callRegistry: CallRegistry<Call>,
): ScheduledExecutorService {
    val executor =
        Executors.newSingleThreadScheduledExecutor { runnable ->
            Thread({
                endpoint.registerCurrentThread()
                runnable.run()
            }, "call-events-ticker").apply { isDaemon = true }
        }
    executor.scheduleWithFixedDelay({
        // Before the calls themselves: destroying a finished call's pjsua2 object is only
        // safe while its id slot is idle, and servicing a live call can start a new one.
        CallDisposal.drain()
        callRegistry.currentCalls().forEach { call ->
            try {
                call.handleEvents()
            } catch (e: Exception) {
                log(null, "Error handling call events: ${e.message}")
            }
        }
    }, 0, 10, TimeUnit.MILLISECONDS)
    return executor
}

fun main(args: Array<String>) {
    if (args.contains("--help") || args.contains("-h")) {
        GlobalOptions.printHelp()
        println()
        SipOptions.printHelp()
        exitProcess(0)
    }
    val config = AppConfig.fromEnv(loadDotEnv())

    val globalOptions = GlobalOptions.parse(config.globalOptions)
    val nameServer = config.nameServer.split(",").map { it.trim() }.filter { it.isNotEmpty() }
    if (nameServer.isNotEmpty()) log(null, "Setting name server: $nameServer")
    val cacheDir = getCacheDir(config.cacheDir)

    val endpointConfig =
        EndpointConfig(
            port = convertToInt(config.port, 5060),
            logLevel = convertToInt(config.logLevel, 5),
            nameServer = nameServer,
            globalOptions = globalOptions,
        )

    val ttsConfig = TtsConfig.from(config.tts)
    logHostnameResolution("HA_BASE_URL", config.ha.baseUrl)
    logHostnameResolution("HA_WEBSOCKET_URL", config.ha.websocketUrl)
    val haConfig =
        HaConfig(
            baseUrl = config.ha.baseUrl,
            websocketUrl = config.ha.websocketUrl,
            token = config.ha.token,
            ttsConfig = ttsConfig,
            webhookId = config.ha.webhookId,
            cacheDir = cacheDir,
            audioSampleRate = globalOptions.audioSampleRate,
        )
    val callRegistry = CallRegistry<Call>()
    val endpoint = createEndpoint(endpointConfig)
    val shutdownLatch = CountDownLatch(1)
    val haClient = HaClient(haConfig)
    val eventSender = EventSender()
    if (haConfig.ttsConfig.debugPrint) {
        haClient.printTtsProviders()
    }
    val accounts = mutableMapOf<Int, Account>()

    // Declared before assignment (as `lateinit`) so the `dial` closure below can
    // capture a reference to it -- CommandHandler needs to be passed into every
    // `Call` it creates via `dial`, but a `Call` also needs a reference back to
    // the very `CommandHandler` that's still being constructed.
    lateinit var commandHandler: CommandHandler<Call>
    commandHandler =
        CommandHandler(
            callRegistry = callRegistry,
            haClient = haClient,
            defaultTtsLanguage = ttsConfig.language,
            dial = { sipAccountNumber, number, menu, ringTimeout, webhooks ->
                val account = accounts[sipAccountNumber] ?: accounts.values.firstOrNull()
                if (account == null) {
                    log(null, "Error: no SIP account available to place call")
                } else {
                    makeCall(account, number, menu, commandHandler, eventSender, haConfig, haClient, ringTimeout, webhooks)
                }
            },
            // Hands shutdown back to the main thread. This runs on the stdin or MQTT
            // thread, and `libDestroy()` should not be called from one of those.
            quit = { shutdownLatch.countDown() },
        )

    val enabledAccountConfigs = enabledAccountConfigs(config, globalOptions)

    val sensorConfig =
        SensorConfig(
            enabled = config.sensor.enabled.equals("true", ignoreCase = true),
            entityPrefix = config.sensor.entityPrefix.ifEmpty { "ha_sip" },
        )
    val sensorUpdater = SensorUpdater(haClient::updateSensorState, sensorConfig, enabledAccountConfigs.keys.toList())
    // Before the accounts exist, and so before anything can report a real registration
    // state: these writes are the placeholders a real update overwrites, and an account
    // that is already registering can produce that update at any moment.
    sensorUpdater.initializeSensors()

    accounts += createAccounts(enabledAccountConfigs, commandHandler, eventSender, haConfig, haClient, sensorUpdater)

    val mqttClient =
        if (globalOptions.enableMqtt) {
            MqttClient(
                globalOptions,
                onCommand = { command ->
                    endpoint.registerCurrentThread()
                    try {
                        commandHandler.handleCommand(command, null)
                    } catch (e: Exception) {
                        log(null, "Error handling command: ${e.message}")
                    }
                },
            ).also { it.connect() }
        } else {
            null
        }

    eventSender.registerSender { event, additionalWebhookId ->
        haClient.triggerWebhook(event)
        if (additionalWebhookId != null) haClient.triggerWebhook(event, additionalWebhookId)
    }
    eventSender.registerSender { event, _ -> mqttClient?.sendEvent(event) }
    val sensorEventHandler = SensorEventHandler(sensorUpdater)
    eventSender.registerSender { event, _ -> sensorEventHandler.handleEvent(event) }

    startStdinReader(endpoint, commandHandler)
    val eventsExecutor = startCallTicker(endpoint, callRegistry)

    log(null, "ha-sip started, listening on port ${endpointConfig.port}")

    shutdownLatch.await()

    log(null, "Shutting down.")
    eventsExecutor.shutdown()
    eventsExecutor.awaitTermination(5, TimeUnit.SECONDS)
    eventSender.close()
    sensorUpdater.close()
    mqttClient?.disconnect()
    endpoint.libDestroy()
    exitProcess(0)
}
